# -*- coding: utf-8 -*-
"""审计日志：每次审批尝试都留一条，append-only。

路径默认 ~/.spend-gate/audit.jsonl，可用 SPEND_GATE_AUDIT_PATH 覆盖。
写不进去不能在「已批准」路径上静默——那会出现花了钱却没记录。
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone

ENV_PATH = "SPEND_GATE_AUDIT_PATH"
DEFAULT = "~/.spend-gate/audit.jsonl"


class AuditWriteError(RuntimeError):
    pass


def audit_path() -> str:
    return os.path.expanduser(os.environ.get(ENV_PATH) or DEFAULT)


def record(entry: dict, strict: bool = True) -> None:
    """追加一条。strict=True 时写失败抛异常（批准路径必须用）。"""
    entry = dict(entry)
    entry.setdefault("ts", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    entry.setdefault("host", socket.gethostname())
    path = audit_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        if strict:
            raise AuditWriteError(f"cannot write audit log: {e}") from e
