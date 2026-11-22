# -*- coding: utf-8 -*-
"""命令行入口：spend-gate {doctor,approve,audit}"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import audit, auth, budget, i18n, keychain, policy
from .gate import SpendNotApproved, require_approval


def cmd_doctor(_):
    ok, detail = auth.backend_available()
    print(f"platform      : {sys.platform}")
    print(f"auth backend  : {'ok' if ok else 'unavailable'}")
    print(f"  detail      : {detail}")
    print(f"ui language   : {i18n.resolve()}")
    print(f"system langs  : {', '.join(i18n.detect_languages()[:3])}")
    print(f"audit path    : {audit.audit_path()}")
    print(f"bypass env    : {'SET' if os.environ.get('SPEND_GATE_BYPASS') == '1' else 'off'}")
    return 0 if ok else 1


def cmd_approve(a):
    try:
        ap = require_approval(amount=a.amount, currency=a.currency, vendor=a.vendor,
                              purpose=a.purpose, quantity=a.quantity, timeout=a.timeout)
    except SpendNotApproved as e:
        print(f"not approved: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(ap.as_dict(), ensure_ascii=False, indent=1))
    return 0


def cmd_verify(_):
    ok1, d1 = budget.verify_ledger()
    ok2, d2 = budget.verify_envelopes()
    ok = ok1 and ok2
    print(f"ledger   : {'ok' if ok1 else 'BROKEN'}  {d1}")
    print(f"envelopes: {'ok' if ok2 else 'BROKEN'}  {d2}")
    return 0 if ok else 1


def cmd_envelope(a):
    if a.action == "open":
        env = budget.open_envelope(max_amount=a.max, currency=a.currency,
                                   vendor=a.vendor, purpose=a.purpose,
                                   ttl_hours=a.ttl)
        print(json.dumps({"id": env.id, "max_amount": env.max_amount,
                          "expires_at": env.expires_at}, ensure_ascii=False, indent=1))
        return 0
    env = budget._load(a.id)
    print(json.dumps({"id": env.id, "max": env.max_amount, "spent": env.spent,
                      "reserved": sum(env.reserved.values()),
                      "remaining": env.remaining, "currency": env.currency,
                      "vendor": env.vendor}, ensure_ascii=False, indent=1))
    return 0


def cmd_policy(a):
    if a.action == "show":
        p, ok = policy.load()
        print(json.dumps({"policy": p.__dict__, "signature_valid": ok,
                          "keychain": keychain.available()},
                         ensure_ascii=False, indent=1))
        return 0 if ok else 1
    p, _ = policy.load()
    if a.auto_under is not None:
        p.auto_approve_under = a.auto_under
    if a.daily_cap is not None:
        p.daily_cap = a.daily_cap
    if a.daily_limit is not None:
        p.daily_limit = a.daily_limit
    if a.weekly_limit is not None:
        p.weekly_limit = a.weekly_limit
    if a.monthly_limit is not None:
        p.monthly_limit = a.monthly_limit
    if a.hard_limit is not None:
        p.hard_limit = a.hard_limit
    if a.vendor:
        cfg = dict(p.vendors.get(a.vendor) or {})
        if a.vendor_daily_limit is not None:
            cfg["daily_limit"] = a.vendor_daily_limit
        if a.vendor_weekly_limit is not None:
            cfg["weekly_limit"] = a.vendor_weekly_limit
        if a.vendor_monthly_limit is not None:
            cfg["monthly_limit"] = a.vendor_monthly_limit
        if a.vendor_trusted is not None:
            cfg["trusted"] = a.vendor_trusted
        p.vendors[a.vendor] = cfg
    if a.currency:
        p.currency = a.currency
    try:
        policy.save(p)          # 会弹系统认证
    except policy.PolicyNotApproved as e:
        print(f"not changed: {e}", file=sys.stderr)
        return 1
    print(json.dumps(p.__dict__, ensure_ascii=False, indent=1))
    return 0


def cmd_audit(a):
    path = audit.audit_path()
    if not os.path.exists(path):
        print("no audit log yet")
        return 0
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(x) for x in f if x.strip()]
    for r in rows[-a.tail:]:
        print(json.dumps(r, ensure_ascii=False))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="spend-gate",
                                description="Human-in-the-loop spending gate for AI agents on macOS.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="check whether this machine can enforce approval")
    d.set_defaults(func=cmd_doctor)

    ap = sub.add_parser("approve", help="request one approval and print the result")
    ap.add_argument("--amount", type=float, required=True)
    ap.add_argument("--currency", default="CNY")
    ap.add_argument("--vendor", default="unknown")
    ap.add_argument("--purpose", default="")
    ap.add_argument("--quantity", default="")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.set_defaults(func=cmd_approve)

    v = sub.add_parser("verify", help="verify the hash chain of the spend ledger")
    v.set_defaults(func=cmd_verify)

    en = sub.add_parser("envelope", help="open or inspect a budget envelope")
    en.add_argument("action", choices=["open", "status"])
    en.add_argument("--max", type=float, default=10.0)
    en.add_argument("--currency", default="CNY")
    en.add_argument("--vendor", default="")
    en.add_argument("--purpose", default="")
    en.add_argument("--ttl", type=float, default=24.0, help="hours")
    en.add_argument("--id", default="")
    en.set_defaults(func=cmd_envelope)

    po = sub.add_parser("policy", help="show or set the auto-approve policy")
    po.add_argument("action", choices=["show", "set"])
    po.add_argument("--auto-under", type=float, default=None,
                    help="auto-approve single charges at or below this amount (0 disables)")
    po.add_argument("--daily-cap", type=float, default=None,
                    help="max total auto-approved spend per day (0 = unlimited)")
    po.add_argument("--daily-limit", type=float, default=None,
                    help="hard ceiling for all spend per day (0 = no limit)")
    po.add_argument("--weekly-limit", type=float, default=None)
    po.add_argument("--monthly-limit", type=float, default=None)
    po.add_argument("--hard-limit", type=lambda v: v.lower() in ("1", "true", "yes"),
                    default=None,
                    help="block instead of asking when a period limit is exceeded")
    po.add_argument("--vendor", default=None,
                    help="configure limits for one vendor prefix (e.g. dashscope)")
    po.add_argument("--vendor-daily-limit", type=float, default=None)
    po.add_argument("--vendor-weekly-limit", type=float, default=None)
    po.add_argument("--vendor-monthly-limit", type=float, default=None)
    po.add_argument("--vendor-trusted", type=lambda v: v.lower() in ("1", "true", "yes"),
                    default=None, help="skip prompts for this vendor while within limits")
    po.add_argument("--currency", default=None)
    po.set_defaults(func=cmd_policy)

    au = sub.add_parser("audit", help="print recent audit entries")
    au.add_argument("--tail", type=int, default=20)
    au.set_defaults(func=cmd_audit)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
