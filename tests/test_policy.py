# -*- coding: utf-8 -*-
"""0.3：小额免批策略 + Keychain 锚点。全部 mock Keychain。"""
import json
import os
import time

import pytest

from spend_gate import budget, keychain, policy

KEY = b"\x01" * 32


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEND_GATE_HOME", str(tmp_path))
    monkeypatch.setattr(keychain, "available", lambda: True)
    monkeypatch.setattr(keychain, "get_or_create_policy_key", lambda: KEY)
    store = {}
    monkeypatch.setattr(keychain, "set_anchor", lambda v: store.__setitem__("a", v))
    monkeypatch.setattr(keychain, "get_anchor", lambda: store.get("a"))
    monkeypatch.setattr(budget.gate, "require_approval",
                        lambda **kw: type("A", (), {"amount": kw.get("amount"), "id": "t"})())
    return store


# ---- policy ----

def test_policy_defaults_off():
    p, ok = policy.load()
    assert ok and not p.enabled
    assert policy.can_auto_approve(0.01) is False


def test_policy_signed_roundtrip():
    policy.save(policy.Policy(auto_approve_under=0.05, daily_cap=1.0))
    p, ok = policy.load()
    assert ok and p.auto_approve_under == 0.05


def test_policy_detects_tampering(tmp_path):
    policy.save(policy.Policy(auto_approve_under=0.05, daily_cap=1.0))
    path = policy.policy_path()
    data = json.load(open(path))
    data["policy"]["auto_approve_under"] = 500.0
    json.dump(data, open(path, "w"))
    p, ok = policy.load()
    assert not ok
    assert policy.can_auto_approve(1.0) is False   # 签名坏了就不免批


def test_tiny_amount_auto_approved():
    policy.save(policy.Policy(auto_approve_under=0.05, daily_cap=1.0))
    assert policy.can_auto_approve(0.03) is True
    assert policy.can_auto_approve(0.06) is False


def test_daily_cap_stops_auto_approval():
    policy.save(policy.Policy(auto_approve_under=0.05, daily_cap=0.08))
    env = budget.open_envelope(max_amount=1.0)
    env.spend(0.05)
    assert policy.can_auto_approve(0.05) is False
    assert policy.can_auto_approve(0.01) is True


def test_currency_mismatch_blocks_auto():
    policy.save(policy.Policy(auto_approve_under=0.05, daily_cap=1.0, currency="CNY"))
    assert policy.can_auto_approve(0.01, currency="USD") is False


# ---- anchor ----

def test_open_envelope_sets_anchor(env):
    budget.open_envelope(max_amount=1.0)
    rows = budget._ledger()._rows()
    assert env.get("a") == f"{rows[-1]['seq']}:{rows[-1]['hash']}"


def test_verify_ok_when_anchor_matches(env):
    budget.open_envelope(max_amount=1.0)
    ok, detail = budget.verify_ledger()
    assert ok and "anchor row 1 ok" in detail


def test_normal_growth_after_anchor_still_ok(env):
    """锚点之后正常追加花费，不应被误判成篡改。"""
    env_obj = budget.open_envelope(max_amount=1.0)
    env_obj.spend(0.1)
    env_obj.spend(0.1)
    ok, detail = budget.verify_ledger()
    assert ok, detail


def test_verify_detects_truncation(env):
    env_obj = budget.open_envelope(max_amount=1.0)
    env_obj.spend(0.1)
    anchor_row = int(env["a"].split(":")[0])
    # 把台账截到锚点之前，再补一条自洽的旧行：链本身没问题，但锚点那行没了。
    p = os.path.join(os.environ["SPEND_GATE_HOME"], "ledger.jsonl")
    keep = budget._ledger()._rows()[: anchor_row - 1]
    with open(p, "w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    ok, detail = budget.verify_ledger()
    assert not ok and "truncated" in detail


def test_verify_without_keychain_says_so(env, monkeypatch):
    budget.open_envelope(max_amount=1.0)
    monkeypatch.setattr(keychain, "available", lambda: False)
    ok, detail = budget.verify_ledger()
    assert ok and "anchor not checked" in detail
