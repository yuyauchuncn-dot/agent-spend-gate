# -*- coding: utf-8 -*-
"""命令行入口：spend-gate {doctor,approve,audit}"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import audit, auth, i18n
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

    au = sub.add_parser("audit", help="print recent audit entries")
    au.add_argument("--tail", type=int, default=20)
    au.set_defaults(func=cmd_audit)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
