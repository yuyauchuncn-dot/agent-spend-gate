#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""录屏辅助：倒数 5 秒后弹窗，给你时间开始录制。

用法：
  1. Cmd+Shift+5 → 录制所选部分 → 录制
  2. 跑这个脚本，按指纹
  3. 停录，裁到 10 秒
"""
import time

for i in (5, 4, 3, 2, 1):
    print(f"{i}… 现在开始录制")
    time.sleep(1)

from spend_gate import require_approval, SpendNotApproved

try:
    ap = require_approval(
        amount=0.02,
        currency="CNY",
        vendor="openai/gpt-4o",
        purpose="summarise 10 documents",
        quantity="10 calls",
    )
    print(f"✓ approved  {ap.id[:8]}  {ap.method}")
except SpendNotApproved as e:
    print(f"✗ denied: {e.reason}")
