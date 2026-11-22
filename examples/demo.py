# -*- coding: utf-8 -*-
"""人工验证专用：会弹窗、会要求指纹，别放进 CI。

    python -m spend_gate.cli doctor
    python -m spend_gate.cli approve --amount 0.01 --vendor demo --purpose "smoke test"
"""
from spend_gate import require_approval

if __name__ == "__main__":
    a = require_approval(amount=0.01, currency="CNY", vendor="demo/demo",
                         purpose="smoke test", quantity="1")
    print("approved:", a.id, a.method)
