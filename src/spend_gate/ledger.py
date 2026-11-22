# -*- coding: utf-8 -*-
"""哈希链台账：每条记录带前一条的哈希，删改中间任意一条都会断链。

它防什么、不防什么，照实说：

- 能检测：删行、改行、插入、顺序调换、把文件截断到锚点之前（配合 Keychain 检查点）。
- 不能检测：锚点之后整段重写（本地没有可信时间源），以及能改代码的人。
  这是安全带，不是保险箱。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time

GENESIS = "0" * 64


def _digest(prev: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((prev + "|" + body).encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def _rows(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def tail_hash(self) -> str:
        rows = self._rows()
        return rows[-1]["hash"] if rows else GENESIS

    def append(self, entry: dict) -> dict:
        """追加一条。

        整个「读链尾 → 计算 → 写」必须持文件锁。否则两个进程并发追加会
        拿到同一个 seq，链立刻对不上，verify 会把正常使用报成篡改。
        """
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        lock = self.path + ".lock"
        with open(lock, "a+") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                rows = self._rows()
                prev = rows[-1]["hash"] if rows else GENESIS
                payload = {"seq": len(rows) + 1, "ts": time.time(), **entry}
                rec = {**payload, "prev": prev, "hash": _digest(prev, payload)}
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                return rec
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def verify(self) -> tuple[bool, str]:
        """从头验证整条链。返回 (ok, 说明)。"""
        prev = GENESIS
        rows = self._rows()
        for i, rec in enumerate(rows, 1):
            if rec.get("seq") != i:
                return False, f"seq mismatch at row {i}: {rec.get('seq')}"
            if rec.get("prev") != prev:
                return False, f"broken link at row {i}"
            payload = {k: v for k, v in rec.items() if k not in ("prev", "hash")}
            if _digest(prev, payload) != rec.get("hash"):
                return False, f"hash mismatch at row {i}"
            prev = rec["hash"]
        return True, f"{prev[:12]}… ok ({len(rows)} rows)"

    def totals(self, since: float = 0.0, vendor: str | None = None,
               currency: str | None = None) -> float:
        """按条件汇总已花费金额。spend 与 settle 都算真花了。"""
        total = 0.0
        for rec in self._rows():
            if rec.get("ts", 0) < since:
                continue
            if vendor and rec.get("vendor") != vendor:
                continue
            if currency and rec.get("currency") != currency:
                continue
            if rec.get("event") in ("spend", "settle"):
                total += float(rec.get("amount", 0))
        return total


def default_ledger() -> Ledger:
    root = os.path.expanduser(os.environ.get("SPEND_GATE_HOME") or "~/.spend-gate")
    return Ledger(os.environ.get("SPEND_GATE_LEDGER_PATH")
                  or os.path.join(root, "ledger.jsonl"))
