# -*- coding: utf-8 -*-
"""预算信封：金额事先不知道时，批准「上限」而不是「金额」。

    from spend_gate import open_envelope

    with open_envelope(max_amount=10.0, currency="CNY", vendor="openai",
                       purpose="batch summarisation", ttl_hours=24) as env:
        for doc in docs:
            env.reserve(0.5)              # 先占住，避免并发超额
            cost = call_api(doc)          # 实际花了多少，事后才知道
            env.settle(res, cost)         # 按实际结算，把多占的吐回去

规则：

- 打开信封时弹一次窗，批准的是**上限**，不是某一笔。
- 之后每笔 `spend` / `settle` 在额度内直接记账，不再打扰。
- 累计达到上限、或过了有效期，抛 `BudgetExceeded`，要重新批。
- 每笔都进哈希链台账；删改台账会被 `verify()` 查出来。
- 失败/超时的调用按已花记账（保守），可以用 `release` 撤销预留。

并发：所有读改写都在信封文件上拿 flock，多进程不会各自以为还有余额。
"""
from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict

from . import gate
from .ledger import Ledger
from . import keychain

ROOT = "~/.spend-gate"
ENVELOPES = os.path.join(ROOT, "envelopes")
LEDGER = os.path.join(ROOT, "ledger.jsonl")


class BudgetExceeded(RuntimeError):
    """超出信封上限或有效期。调用方必须停止花钱。"""


def _root() -> str:
    return os.path.expanduser(os.environ.get("SPEND_GATE_HOME") or ROOT)


def _path(env_id: str) -> str:
    return os.path.join(_root(), "envelopes", f"{env_id}.json")


def _ledger() -> Ledger:
    p = os.environ.get("SPEND_GATE_LEDGER_PATH") or os.path.join(_root(), "ledger.jsonl")
    return Ledger(p)


@dataclass
class Envelope:
    id: str
    max_amount: float
    currency: str
    vendor: str
    purpose: str
    expires_at: float
    spent: float = 0.0
    reserved: dict = field(default_factory=dict)

    # ---- 账务 ----
    @property
    def committed(self) -> float:
        return self.spent + sum(self.reserved.values())

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_amount - self.committed)

    def _check_open(self):
        if time.time() > self.expires_at:
            raise BudgetExceeded(f"envelope {self.id} expired")
        if self.committed >= self.max_amount - 1e-9:
            raise BudgetExceeded(f"envelope {self.id} exhausted")

    # ---- 写操作（调用方负责持锁）----
    def _spend_locked(self, amount: float, note: str = "") -> None:
        self._check_open()
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if amount > self.remaining + 1e-9:
            raise BudgetExceeded(
                f"requested {amount:.4f} but only {self.remaining:.4f} left")
        self.spent += amount
        _ledger().append({"event": "spend", "envelope": self.id, "vendor": self.vendor,
                          "currency": self.currency, "amount": amount, "note": note})
        _save(self)

    def _reserve_locked(self, amount: float, note: str = "") -> str:
        self._check_open()
        if amount > self.remaining + 1e-9:
            raise BudgetExceeded(
                f"requested {amount:.4f} but only {self.remaining:.4f} left")
        rid = uuid.uuid4().hex[:12]
        self.reserved[rid] = amount
        _ledger().append({"event": "reserve", "envelope": self.id, "vendor": self.vendor,
                          "currency": self.currency, "amount": amount,
                          "reservation": rid, "note": note})
        _save(self)
        return rid

    def _settle_locked(self, rid: str, actual: float, note: str = "") -> None:
        if rid not in self.reserved:
            raise KeyError(f"unknown reservation {rid}")
        held = self.reserved.pop(rid)
        if actual < 0:
            raise ValueError("actual must be non-negative")
        if actual > held + 1e-9:
            # 实际超过预留：只有在信封总额还够时才允许，否则拒绝。
            if actual > self.remaining + held + 1e-9:
                raise BudgetExceeded(
                    f"settle {actual:.4f} exceeds envelope capacity")
        self.spent += actual
        _ledger().append({"event": "settle", "envelope": self.id, "vendor": self.vendor,
                          "currency": self.currency, "amount": actual,
                          "reservation": rid, "held": held, "note": note})
        _save(self)

    def _release_locked(self, rid: str, note: str = "") -> None:
        held = self.reserved.pop(rid, None)
        if held is None:
            return
        _ledger().append({"event": "release", "envelope": self.id, "vendor": self.vendor,
                          "currency": self.currency, "amount": 0.0,
                          "reservation": rid, "held": held, "note": note})
        _save(self)

    # ---- 公共 API（自己拿锁）----
    def spend(self, amount: float, note: str = "") -> None:
        with _locked(self.id) as cur:
            cur._spend_locked(amount, note)
            _copy_into(self, cur)

    def reserve(self, amount: float, note: str = "") -> str:
        with _locked(self.id) as cur:
            rid = cur._reserve_locked(amount, note)
            _copy_into(self, cur)
            return rid

    def settle(self, reservation: str, actual: float, note: str = "") -> None:
        with _locked(self.id) as cur:
            cur._settle_locked(reservation, actual, note)
            _copy_into(self, cur)

    def release(self, reservation: str, note: str = "") -> None:
        with _locked(self.id) as cur:
            cur._release_locked(reservation, note)
            _copy_into(self, cur)

    @contextmanager
    def reservation(self, amount: float, note: str = ""):
        """with env.reservation(0.5) as r: ...; 正常退出按 r.actual 结算，
        异常退出按预留额保守记账。"""
        rid = self.reserve(amount, note)
        box = {"actual": amount}
        try:
            yield box
        except Exception:
            self.settle(rid, amount, note + " [failed, charged hold]")
            raise
        else:
            self.settle(rid, box["actual"], note)


def _save(env: Envelope) -> None:
    p = _path(env.id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(env), f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _copy_into(dst: Envelope, src: Envelope) -> None:
    dst.spent = src.spent
    dst.reserved = dict(src.reserved)
    dst.expires_at = src.expires_at


@contextmanager
def _locked(env_id: str):
    """读-改-写全程持 flock，避免两个进程同时看到同一份余额。"""
    p = _path(env_id)
    lock = p + ".lock"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(lock, "a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            cur = _load(env_id)
            yield cur
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _load(env_id: str) -> Envelope:
    with open(_path(env_id), encoding="utf-8") as f:
        d = json.load(f)
    return Envelope(**d)


def open_envelope(max_amount: float, currency: str = "CNY", vendor: str = "",
                  purpose: str = "", ttl_hours: float = 24.0,
                  timeout: float = 300.0) -> Envelope:
    """弹一次窗，批准一个上限。返回已落盘的信封。

    金额事先不知道时用这个：批准的是「最多这么多」，不是某一笔。
    """
    if max_amount <= 0:
        raise ValueError("max_amount must be positive")
    gate.require_approval(
        amount=max_amount, currency=currency, vendor=vendor,
        purpose=f"{purpose} (cap, actual total may be lower)".strip(),
        quantity="up to this amount", timeout=timeout,
    )
    env = Envelope(
        id=uuid.uuid4().hex[:16],
        max_amount=float(max_amount),
        currency=currency,
        vendor=vendor,
        purpose=purpose,
        expires_at=time.time() + ttl_hours * 3600,
    )
    _save(env)
    _ledger().append({"event": "open", "envelope": env.id, "vendor": vendor,
                      "currency": currency, "amount": max_amount,
                      "expires_at": env.expires_at, "purpose": purpose})
    # 人工刚刚批准过，此刻把链头锚进 Keychain——这是唯一可信的参照点。
    anchor_ledger()
    return env


def anchor_ledger() -> str | None:
    """把当前链头写入 Keychain。只在人类刚批准过的时刻调用。"""
    if not keychain.available():
        return None
    tail = _ledger().tail_hash()
    try:
        keychain.set_anchor(tail)
        return tail
    except keychain.KeychainError:
        return None


def verify_ledger() -> tuple[bool, str]:
    """校验哈希链，并与 Keychain 锚点比对。

    链能自洽但尾部比锚点短 → 有人把记录截断了（回滚），判失败。
    Keychain 不可用时退回纯链校验，并在说明里标明「未比对锚点」。
    """
    ok, detail = _ledger().verify()
    if not ok:
        return ok, detail
    if not keychain.available():
        return True, detail + " [no keychain, anchor not checked]"
    anchor = keychain.get_anchor()
    tail = _ledger().tail_hash()
    if anchor is None:
        return True, detail + " [no anchor yet]"
    if anchor == tail:
        return True, detail + " [anchor ok]"
    return False, f"tail {tail[:12]}… does not match anchored {anchor[:12]}… (truncated or rewritten)"
