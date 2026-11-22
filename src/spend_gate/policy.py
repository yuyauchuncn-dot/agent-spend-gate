# -*- coding: utf-8 -*-
"""小额免打扰策略：单笔低于阈值、且当日累计没超上限时，不弹窗。

策略文件 ~/.spend-gate/policy.json，权限 600，带 HMAC 签名。
签名密钥在 Keychain（见 keychain.py）。改动策略必须能重签，
也就是必须能读到那个密钥——这让「悄悄放宽阈值」多一道门槛。

默认关闭（auto_approve_under = 0）：零配置时每一笔都要人批。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, asdict

from . import auth, keychain
from .ledger import Ledger

ROOT = "~/.spend-gate"


def _home() -> str:
    return os.path.expanduser(os.environ.get("SPEND_GATE_HOME") or ROOT)


def policy_path() -> str:
    return os.path.join(_home(), "policy.json")


class PolicyNotApproved(RuntimeError):
    """改策略需要人类认证。没通过就不改。"""


@dataclass
class Policy:
    auto_approve_under: float = 0.0   # 0 = 关闭；>0 表示单笔不超过它就走免批
    daily_cap: float = 0.0            # 0 = 不限制；>0 表示**免批部分**的当日总额
    daily_limit: float = 0.0          # 0 = 不限制；全部花费的当日上限
    weekly_limit: float = 0.0         # 0 = 不限制；周一起算
    monthly_limit: float = 0.0        # 0 = 不限制；1 号起算
    hard_limit: bool = False          # True = 超限直接拒绝，不给人批的机会
    currency: str = "CNY"

    @property
    def enabled(self) -> bool:
        return self.auto_approve_under > 0


def _canonical(p: Policy) -> bytes:
    return json.dumps(asdict(p), sort_keys=True, separators=(",", ":")).encode()


def _mac(p: Policy, key: bytes) -> str:
    return hmac.new(key, _canonical(p), hashlib.sha256).hexdigest()


def save(p: Policy, *, require_auth: bool = True) -> None:
    """写策略。默认必须先过系统认证——否则 agent 可以自己把阈值调到无限大，
    这个闸门就形同虚设。测试里显式传 require_auth=False。"""
    if require_auth:
        res = auth.authenticate("Change the auto-approve spending policy", timeout=300)
        if not res.ok:
            raise PolicyNotApproved(f"policy change not approved: {res.reason}")
    key = keychain.get_or_create_policy_key()
    data = {"policy": asdict(p), "hmac": _mac(p, key)}
    path = policy_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(path, 0o600)


def load() -> tuple[Policy, bool]:
    """返回 (策略, 签名是否有效)。文件不存在时返回默认策略且视为有效。"""
    path = policy_path()
    if not os.path.exists(path):
        return Policy(), True
    try:
        data = json.load(open(path, encoding="utf-8"))
        p = Policy(**data["policy"])
        key = keychain.get_or_create_policy_key()
        ok = hmac.compare_digest(data.get("hmac", ""), _mac(p, key))
        return p, ok
    except Exception:
        return Policy(), False


def _today_start() -> float:
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def _week_start() -> float:
    t = time.localtime()
    monday = t.tm_mday - (t.tm_wday % 7)          # tm_wday: 周一=0
    return time.mktime((t.tm_year, t.tm_mon, monday, 0, 0, 0, 0, 0, -1))


def _month_start() -> float:
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))


@dataclass(frozen=True)
class LimitBreach:
    """某笔花费会让哪个周期超限。spent 是花之前的累计。"""
    period: str      # day | week | month
    spent: float
    limit: float
    pending: float   # 本笔金额

    @property
    def total_after(self) -> float:
        return self.spent + self.pending

    def describe(self) -> str:
        return (f"{self.period}: {self.spent:.2f} + {self.pending:.2f} = "
                f"{self.total_after:.2f} > {self.limit:.2f}")


def check_limits(amount: float, currency: str = "CNY") -> list[LimitBreach]:
    """返回这笔花费会击穿的周期限额（可能多个）。空列表表示没超。"""
    p, signed = load()
    if not signed or p.currency != currency:
        return []
    from .ledger import default_ledger
    led = default_ledger()
    out = []
    for period, start, limit in (
        ("day", _today_start(), p.daily_limit),
        ("week", _week_start(), p.weekly_limit),
        ("month", _month_start(), p.monthly_limit),
    ):
        if limit <= 0:
            continue
        spent = led.totals(since=start, currency=currency)
        if spent + amount > limit + 1e-9:
            out.append(LimitBreach(period, spent, limit, amount))
    return out


def hard_limit_enabled() -> bool:
    p, signed = load()
    return signed and p.hard_limit


def can_auto_approve(amount: float, currency: str = "CNY") -> bool:
    """免批判定：单笔低于阈值，且今日免批累计 + 本笔不超日上限。

    签名无效时一律不免批（fail-closed）——策略被改过就不认。
    """
    p, sig_ok = load()
    if not sig_ok or not p.enabled:
        return False
    if p.currency != currency:
        return False
    if amount > p.auto_approve_under + 1e-12:
        return False
    if p.daily_cap > 0:
        from .ledger import default_ledger
        used = default_ledger().totals(since=_today_start(), currency=currency)
        if used + amount > p.daily_cap + 1e-12:
            return False
    return True
