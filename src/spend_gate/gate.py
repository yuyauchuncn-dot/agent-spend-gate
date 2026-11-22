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
                    breaches: list | None = None) -> bool:
    """第一道闸：认知确认。默认按钮是取消，防止盲按回车。

    breaches 非空时换成「超限」文案：把人已经花了多少、限额多少、
    这一笔加上去会变成多少，一次性摆出来。
    """
    if breaches:
        b = breaches[0]   # 只显示最先击穿的那个周期，多个时用最紧的
        pd = t(f"period_{b.period}")
        body = t("over_limit_body", vendor=vendor, amount=amount, currency=currency,
                 purpose=purpose, period=pd,
                 detail="; ".join(x.describe() for x in breaches))
        title = t("over_limit_title")
    else:
        body = t("dialog_body", vendor=vendor, amount=amount, currency=currency,
                 purpose=purpose, quantity=quantity)
        title = t("dialog_title")
    ok_label = t("dialog_approve")
    no_label = t("dialog_cancel")
    script = (
        f'display dialog "{_applescript_string(body)}" '
        f'buttons {{"{_applescript_string(no_label)}", "{_applescript_string(ok_label)}"}} '
        f'default button "{_applescript_string(no_label)}" '
        f'with title "{_applescript_string(title)}" with icon caution'
    )
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=600)
    except Exception:
        return False
    return ok_label in (r.stdout or "")


def require_approval(amount, currency: str = "CNY", vendor: str = "",
                     purpose: str = "", quantity: str = "",
                     timeout: float = 300.0) -> Approval:
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
    if policy.can_auto_approve(amount, currency):
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

    # 周期限额。超了就换个弹窗文案让人决定；开了 hard_limit 就直接拒。
    breaches = policy.check_limits(amount, currency)
    if breaches and policy.hard_limit_enabled():
        audit.record({**base, "result": "denied", "method": "unknown",
                      "detail": f"hard limit: {breaches[0].describe()}"}, strict=False)
        raise SpendNotApproved(
            t("limit_blocked", period=t(f"period_{breaches[0].period}")), "limit")

    if not _confirm_dialog(t, amount, currency, vendor, purpose, quantity, breaches):
        audit.record({**base, "result": "denied", "method": "unknown",
                      "detail": "dialog cancelled"}, strict=False)
        raise SpendNotApproved(t("denied_cancelled"), "cancelled")

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
    audit.record({**base, "result": "approved", "method": res.method}, strict=True)
    return Approval(id=aid, ts=_now_iso(), amount=amount, currency=currency, vendor=vendor,
                    purpose=purpose, quantity=quantity, method=res.method)
