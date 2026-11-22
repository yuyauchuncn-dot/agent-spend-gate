# -*- coding: utf-8 -*-
"""命令行入口：spend-gate {doctor,approve,audit}"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import audit, auth, budget, i18n
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
    ok, detail = budget.verify_ledger()
    print(("ok  " if ok else "BROKEN  ") + detail)
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

    au = sub.add_parser("audit", help="print recent audit entries")
    au.add_argument("--tail", type=int, default=20)
    au.set_defaults(func=cmd_audit)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
