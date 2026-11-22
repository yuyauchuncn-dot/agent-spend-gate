# -*- coding: utf-8 -*-
"""预算信封与台账测试。全部无 UI、无网络。"""
import json
import multiprocessing as mp
import os
import time

import pytest

from spend_gate import budget
from spend_gate.ledger import Ledger


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEND_GATE_HOME", str(tmp_path))
    monkeypatch.setattr(budget.gate, "require_approval",
                        lambda **kw: gate_approval(kw))
    # 这些用例只测台账本身，锚点行为在 test_policy.py 里单独测。
    monkeypatch.setattr(budget.keychain, "available", lambda: False)
    return tmp_path


class gate_approval:
    def __init__(self, kw):
        self.kw = kw
        self.amount = kw.get("amount")
        self.id = "test"


def open_env(**kw):
    kw.setdefault("max_amount", 1.0)
    return budget.open_envelope(**kw)


def test_spend_decrements_and_ledger_chains(home):
    env = open_env(max_amount=1.0)
    env.spend(0.3)
    env.spend(0.2)
    assert abs(env.remaining - 0.5) < 1e-9
    ok, detail = budget.verify_ledger()
    assert ok, detail


def test_spend_over_cap_raises(home):
    env = open_env(max_amount=0.5)
    with pytest.raises(budget.BudgetExceeded):
        env.spend(0.6)
    assert env.spent == 0.0


def test_reserve_settle_returns_unused(home):
    env = open_env(max_amount=1.0)
    rid = env.reserve(0.5)
    assert abs(env.remaining - 0.5) < 1e-9
    env.settle(rid, 0.2)
    assert abs(env.spent - 0.2) < 1e-9
    assert abs(env.remaining - 0.8) < 1e-9


def test_reserve_release_frees_capacity(home):
    env = open_env(max_amount=0.5)
    rid = env.reserve(0.5)
    with pytest.raises(budget.BudgetExceeded):
        env.reserve(0.1)
    env.release(rid)
    env.reserve(0.5)


def test_reservation_context_settles_on_success(home):
    env = open_env(max_amount=1.0)
    with env.reservation(0.4) as r:
        r["actual"] = 0.15
    assert abs(env.spent - 0.15) < 1e-9


def test_reservation_context_charges_hold_on_failure(home):
    env = open_env(max_amount=1.0)
    with pytest.raises(RuntimeError):
        with env.reservation(0.4):
            raise RuntimeError("api exploded")
    assert abs(env.spent - 0.4) < 1e-9


def test_expired_envelope_refuses(home, monkeypatch):
    env = open_env(max_amount=1.0, ttl_hours=0)
    monkeypatch.setattr(time, "time", lambda: env.expires_at + 1)
    with pytest.raises(budget.BudgetExceeded):
        env.spend(0.1)


def test_ledger_detects_tampering(home):
    env = open_env(max_amount=1.0)
    env.spend(0.1)
    env.spend(0.2)
    p = os.path.join(str(home), "ledger.jsonl")
    rows = [json.loads(x) for x in open(p, encoding="utf-8").read().splitlines()]
    rows[1]["amount"] = 0.02
    open(p, "w", encoding="utf-8").write(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n")
    ok, detail = budget.verify_ledger()
    assert not ok and "hash mismatch" in detail


def test_ledger_detects_deletion(home):
    env = open_env(max_amount=1.0)
    env.spend(0.1)
    env.spend(0.2)
    p = os.path.join(str(home), "ledger.jsonl")
    rows = open(p, encoding="utf-8").read().splitlines()
    open(p, "w", encoding="utf-8").write("\n".join([rows[0], rows[2]]) + "\n")
    ok, detail = budget.verify_ledger()
    assert not ok and "seq mismatch" in detail


def _worker(args):
    home, env_id = args
    os.environ["SPEND_GATE_HOME"] = home
    env = budget._load(env_id)
    spent = 0
    for _ in range(50):
        try:
            env.spend(0.01)
            spent += 1
        except budget.BudgetExceeded:
            break
    return spent


def test_concurrent_spend_never_exceeds_cap(home):
    env = open_env(max_amount=0.30)
    with mp.Pool(4) as pool:
        counts = pool.map(_worker, [(str(home), env.id)] * 4)
    final = budget._load(env.id)
    assert final.spent <= 0.30 + 1e-9
    assert sum(counts) == pytest.approx(final.spent / 0.01, abs=1)


def test_period_totals_from_ledger(home):
    env = open_env(max_amount=1.0, vendor="openai")
    env.spend(0.2)
    env.spend(0.3)
    led = Ledger(os.path.join(str(home), "ledger.jsonl"))
    assert led.totals(vendor="openai") == pytest.approx(0.5)
    assert led.totals(vendor="other") == 0.0
