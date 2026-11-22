# -*- coding: utf-8 -*-
"""主逻辑：两道闸 + 审计 + 失败即拒绝。

用法：

    from spend_gate import require_approval

    require_approval(
        amount=2.0,
        currency="CNY",
        vendor="dashscope/wanx2.1-t2i-turbo",
        purpose="生成 10 张样张",
        quantity="10 张",
    )
    # 拿到返回值才继续；抛 SpendNotApproved 必须停止

设计上只做一件事：把「agent 自己决定花钱」变成「人按了指纹才能花」。
它防不住有 root 或能改这份代码的人——README 和 SECURITY 里写明了边界。
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from . import audit, auth, i18n, policy
from .ledger import default_ledger

BYPASS_ENV = "SPEND_GATE_BYPASS"


class SpendNotApproved(RuntimeError):
    """没有拿到人类批准。调用方不得继续花钱。"""

    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Approval:
    id: str
    ts: str
    amount: float
    currency: str
    vendor: str
    purpose: str
    quantity: str
    method: str      # touchid | password | unknown | bypass

    def as_dict(self) -> dict:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _validate_amount(amount) -> float:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("amount must be a number")
    a = float(amount)
    if not math.isfinite(a) or a < 0:
        raise ValueError("amount must be finite and non-negative")
    return a


def _applescript_string(s: str) -> str:
    """转义成 AppleScript 字面量。反斜杠先转，引号后转。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _confirm_dialog(t: i18n.Translator, amount: float, currency: str,
                    vendor: str, purpose: str, quantity: str,
                    breaches: list | None = None,
                    hard: bool = False) -> str:
    """返回 once / period / cancel。超限时多给一个「本周期都放行」按钮。"""
    """第一道闸：认知确认。默认按钮是取消，防止盲按回车。

    breaches 非空时换成「超限」文案：把人已经花了多少、限额多少、
    这一笔加上去会变成多少，一次性摆出来。
    """
    if breaches:
        b = breaches[0]   # 只显示最先击穿的那个周期，多个时用最紧的
        pd = t(f"period_{b.period}")
        key = "hard_limit" if hard else "over_limit"
        body = t(f"{key}_body", vendor=vendor, amount=amount, currency=currency,
                 purpose=purpose, period=pd,
                 detail="; ".join(x.describe() for x in breaches))
        title = t(f"{key}_title")
    else:
        body = t("dialog_body", vendor=vendor, amount=amount, currency=currency,
                 purpose=purpose, quantity=quantity)
        title = t("dialog_title")
    ok_label = t("dialog_approve")
    no_label = t("dialog_cancel")
    once_label = t("approve_once")
    period_label = t("approve_period", period=t(f"period_{breaches[0].period}")) if breaches else ""
    if breaches:
        buttons = [no_label, once_label, period_label]
        default = no_label
    else:
        buttons = [no_label, ok_label]
        default = no_label
    btn_src = ", ".join(f'"{_applescript_string(b)}"' for b in buttons)
    script = (
        f'display dialog "{_applescript_string(body)}" '
        f'buttons {{{btn_src}}} default button "{_applescript_string(default)}" '
        f'with title "{_applescript_string(title)}" with icon caution'
    )
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=600)
    except Exception:
        return "cancel"
    out = r.stdout or ""
    if breaches and period_label in out:
        return "period"
    if (once_label if breaches else ok_label) in out:
        return "once"
    return "cancel"


def require_approval(amount, currency: str = "CNY", vendor: str = "",
                     purpose: str = "", quantity: str = "",
                     timeout: float = 300.0, record_ledger: bool = True) -> Approval:
    """record_ledger=False 用于「这次批准本身不是花费」的场景（开信封时批上限）。"""
    """没拿到批准就抛 SpendNotApproved。"""
    amount = _validate_amount(amount)
    t = i18n.Translator()
    aid = uuid.uuid4().hex
    base = {"id": aid, "amount": amount, "currency": currency,
            "vendor": vendor, "purpose": purpose, "quantity": quantity}

    if os.environ.get(BYPASS_ENV) == "1":
        audit.record({**base, "result": "bypassed", "method": "bypass"}, strict=False)
        print("WARNING: spend gate bypassed (SPEND_GATE_BYPASS=1); "
              "this must never be set in production.", file=sys.stderr)
        return Approval(id=aid, ts="", amount=amount, currency=currency, vendor=vendor,
                        purpose=purpose, quantity=quantity, method="bypass")

    # 小额免打扰：单笔低于阈值且当日免批额度没超，直接放行，但仍记账。
    # 必须先查全局限额，否则小额连发可以把日/周/月上限架空（已复现）。
    trusted_ok = policy.is_trusted(vendor)
    if (policy.can_auto_approve(amount, currency) or trusted_ok) and \
            not policy.check_limits(amount, currency) and \
            not policy.check_vendor_limits(amount, vendor, currency):
        # 免批不等于不记账：daily_cap 就是从这条台账算出来的。
        # 审计和台账任一个写不进去都不放行，和人工批准路径同一条规矩。
        audit.record({**base, "result": "approved", "method": "auto"}, strict=True)
        default_ledger().append({"event": "spend", "vendor": vendor, "currency": currency,
                                 "amount": amount, "note": "auto-approved",
                                 "purpose": purpose})
        return Approval(id=aid, ts=_now_iso(), amount=amount, currency=currency,
                        vendor=vendor, purpose=purpose, quantity=quantity, method="auto")

    if sys.platform != "darwin":
        audit.record({**base, "result": "denied", "method": "unknown",
                      "detail": "not macOS"}, strict=False)
        raise SpendNotApproved(t("denied_unavailable"), "unavailable")

    # 周期限额。超了换弹窗文案让人决定。
    # hard_limit 不是「不给批」，而是「批准要留一条例外记录」——
    # 无人值守的任务卡在这里需要一条恢复路径，静默抛异常只会让人翻日志。
    breaches = policy.check_limits(amount, currency) + \
        policy.check_vendor_limits(amount, vendor, currency)
    hard = bool(breaches) and policy.hard_limit_enabled()

    decision = _confirm_dialog(t, amount, currency, vendor, purpose, quantity, breaches, hard)
    if decision == "cancel":
        denied = {**base, "result": "denied", "method": "unknown",
                  "detail": "dialog cancelled"}
        if breaches:
            denied["over_limit"] = [b.describe() for b in breaches]
            denied["hard"] = hard
        audit.record(denied, strict=False)
        raise SpendNotApproved(t("denied_cancelled"), "cancelled")
    waived_now = []
    if decision == "period" and breaches:
        # 人明确选了「本周期都放行」：记下豁免，后续同周期不再弹窗。
        try:
            policy.grant_waiver([b.period for b in breaches])
            waived_now = [b.period for b in breaches]
        except Exception:
            pass

    reason = t("auth_reason", amount=amount, currency=currency, vendor=vendor)
    res = auth.authenticate(reason, timeout=timeout)
    if not res.ok:
        audit.record({**base, "result": "denied", "method": res.method,
                      "detail": res.reason}, strict=False)
        key = {"cancelled": "denied_cancelled", "unavailable": "denied_unavailable",
               "timeout": "denied_timeout"}.get(res.reason, "denied_error")
        raise SpendNotApproved(t(key), res.reason)

    # 批准路径：审计写不进去就不放行，杜绝「花了钱没记录」。
    if breaches:
        base["over_limit"] = [b.describe() for b in breaches]
        if hard:
            base["hard_override"] = True
        if waived_now:
            base["waived_periods"] = waived_now
    try:
        audit.record({**base, "result": "approved", "method": res.method}, strict=True)
    except audit.AuditWriteError as e:
        # README 承诺「审计写不进去就不放行」，那它必须是调用方认得的异常类型。
        raise SpendNotApproved(str(e), "audit_failed") from e
    if record_ledger:
        # 人工批准的花费也要进台账，否则全局限额对它永远是瞎的。
        default_ledger().append({"event": "spend", "vendor": vendor, "currency": currency,
                                 "amount": amount, "note": "approved",
                                 "purpose": purpose, "approval": aid})
    return Approval(id=aid, ts=_now_iso(), amount=amount, currency=currency, vendor=vendor,
                    purpose=purpose, quantity=quantity, method=res.method)
