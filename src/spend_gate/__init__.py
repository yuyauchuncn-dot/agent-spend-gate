# -*- coding: utf-8 -*-
"""agent-spend-gate —— macOS 上给 AI agent 花钱加一道人肉闸门。

    from spend_gate import require_approval

    require_approval(amount=2.0, currency="CNY",
                     vendor="openai/gpt-4o", purpose="summarise 10 files")

没有 Touch ID 或密码，这行代码不会返回。
"""
from .gate import Approval, SpendNotApproved, require_approval
from .budget import BudgetExceeded, Envelope, open_envelope, verify_ledger
from . import auth, budget, i18n

__all__ = ["require_approval", "Approval", "SpendNotApproved", "BudgetExceeded",
           "Envelope", "open_envelope", "verify_ledger", "auth", "budget", "i18n"]
__version__ = "0.6.0"
