# -*- coding: utf-8 -*-
"""哈希链台账：每条记录带前一条的哈希，删改中间任意一条都会断链。

它防什么、不防什么，照实说：

- 能检测：删行、改行、插入、顺序调换、把文件截断到旧版本（配合锚点）。
- 不能检测：把锚点之后的整段重写（本地没有可信时间源），以及能改代码的人。
  这是安全带，不是保险箱。

文件格式：每行一个 JSON，字段固定。
"""
from __future__ import annotations

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
        rows = self._rows()
        prev = rows[-1]["hash"] if rows else GENESIS
        payload = {"seq": len(rows) + 1, "ts": time.time(), **entry}
        rec = {**payload, "prev": prev, "hash": _digest(prev, payload)}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return rec

    def verify(self) -> tuple[bool, str]:
        """从头验证整条链。返回 (ok, 说明)。"""
        prev = GENESIS
        for i, rec in enumerate(self._rows(), 1):
            if rec.get("seq") != i:
                return False, f"seq mismatch at row {i}: {rec.get('seq')}"
            if rec.get("prev") != prev:
                return False, f"broken link at row {i}"
            payload = {k: v for k, v in rec.items() if k not in ("prev", "hash")}
            if _digest(prev, payload) != rec.get("hash"):
                return False, f"hash mismatch at row {i}"
            prev = rec["hash"]
        return True, f"{prev[:12]}… ok ({len(self._rows())} rows)"

    def totals(self, since: float = 0.0, vendor: str | None = None,
               currency: str | None = None) -> float:
        """按条件汇总已结算金额。用于周期额度。"""
        total = 0.0
        for rec in self._rows():
            if rec.get("ts", 0) < since:
                continue
            if vendor and rec.get("vendor") != vendor:
                continue
            if currency and rec.get("currency") != currency:
                continue
            # spend 是已知金额直接记账，settle 是预留后按实际结算，两者都算真花了。
            if rec.get("event") in ("spend", "settle"):
                total += float(rec.get("amount", 0))
        return total
