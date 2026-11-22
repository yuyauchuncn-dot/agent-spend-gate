# -*- coding: utf-8 -*-
"""Keychain 锚点：把「可信的链头」和「策略签名密钥」存在用户的登录钥匙串里。

为什么不是普通文件：
台账本身是哈希链，改中间某行会被发现。但如果攻击者（同用户的 agent）
把最后几十行整个重写，本地没有任何可信参照物能发现——除非链头另有存放处。

Keychain 的 `security` 项至少要为用户会话解锁，改它比改普通文件多一道门槛；
配合每次人工批准时更新锚点，可以把「静默截断」变成「需要一次人类动作」。

诚实的边界：同一用户会话解锁后，agent 仍能读/改这个 Keychain 项。
这不是硬件密钥。它抬高的是成本，不是绝对防线。SECURITY.md 里写明了。
"""
from __future__ import annotations

import os
import secrets
import subprocess

SERVICE = "agent-spend-gate"
ACCOUNT = "ledger-anchor"
POLICY_ACCOUNT = "policy-key"
ENV_DISABLE = "SPEND_GATE_NO_KEYCHAIN"


class KeychainError(RuntimeError):
    pass


def available() -> bool:
    if os.environ.get(ENV_DISABLE) == "1":
        return False
    return subprocess.run(["which", "security"], capture_output=True).returncode == 0


def _read(account: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-a", account,
                        "-s", SERVICE, "-w"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def _write(account: str, value: str) -> None:
    r = subprocess.run(["security", "add-generic-password", "-a", account,
                        "-s", SERVICE, "-w", value, "-U"], capture_output=True, text=True)
    if r.returncode != 0:
        raise KeychainError(r.stderr.strip() or "security add-generic-password failed")


def get_anchor() -> str | None:
    return _read(ACCOUNT)


def set_anchor(value: str) -> None:
    _write(ACCOUNT, value)


def get_or_create_policy_key() -> bytes:
    """策略签名密钥。首次生成时写入 Keychain，之后每次读回来。"""
    existing = _read(POLICY_ACCOUNT)
    if existing:
        return bytes.fromhex(existing)
    key = secrets.token_bytes(32)
    _write(POLICY_ACCOUNT, key.hex())
    return key
