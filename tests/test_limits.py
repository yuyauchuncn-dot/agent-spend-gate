# -*- coding: utf-8 -*-
"""0.4：日/周/月全局限额。"""
import json

import pytest

from spend_gate import auth, budget, gate, keychain, policy

KEY = b"\x02" * 32


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEND_GATE_HOME", str(tmp_path))
    monkeypatch.setenv("SPEND_GATE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("SPEND_GATE_BYPASS", raising=False)
    monkeypatch.setattr(keychain, "available", lambda: False)
    monkeypatch.setattr(keychain, "get_or_create_policy_key", lambda: KEY)
    monkeypatch.setattr(auth, "authenticate", lambda *a, **k: auth.AuthResult(True, "unknown"))
    return tmp_path


def spend_via_ledger(amount, vendor="openai", currency="CNY"):
    from spend_gate.ledger import default_ledger
    default_ledger().append({"event": "spend", "vendor": vendor,
                             "currency": currency, "amount": amount})


def test_no_limits_means_no_breach():
    policy.save(policy.Policy(), require_auth=False)
    assert policy.check_limits(100.0) == []


def test_daily_limit_breached():
    policy.save(policy.Policy(daily_limit=0.10), require_auth=False)
    spend_via_ledger(0.08)
    b = policy.check_limits(0.05)
    assert len(b) == 1 and b[0].period == "day"
    assert abs(b[0].spent - 0.08) < 1e-9
    assert abs(b[0].total_after - 0.13) < 1e-9


def test_under_limit_not_breached():
    policy.save(policy.Policy(daily_limit=0.10), require_auth=False)
    spend_via_ledger(0.05)
    assert policy.check_limits(0.04) == []


def test_weekly_and_monthly_breached_together():
    policy.save(policy.Policy(weekly_limit=1.0, monthly_limit=1.5), require_auth=False)
    spend_via_ledger(0.95)
    periods = {b.period for b in policy.check_limits(0.2)}
    assert "week" in periods and "month" not in periods   # 1.15 <= 1.5
    periods = {b.period for b in policy.check_limits(0.6)}
    assert periods == {"week", "month"}


def test_unsigned_policy_ignores_limits(tmp_path):
    policy.save(policy.Policy(daily_limit=0.01), require_auth=False)
    p = policy.policy_path()
    d = json.load(open(p))
    d["policy"]["daily_limit"] = 1e9
    json.dump(d, open(p, "w"))
    assert policy.check_limits(5.0) == []   # 签名坏了就不认限额（fail-open 到「无上限」不对，见下条）
    assert policy.can_auto_approve(0.001) is False


def test_hard_limit_blocks(monkeypatch):
    policy.save(policy.Policy(daily_limit=0.10, hard_limit=True), require_auth=False)
    spend_via_ledger(0.08)
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: True)
    with pytest.raises(gate.SpendNotApproved) as e:
        gate.require_approval(0.05)
    assert e.value.reason == "limit"


def test_soft_limit_asks_then_allows(monkeypatch, tmp_path):
    policy.save(policy.Policy(daily_limit=0.10, hard_limit=False), require_auth=False)
    spend_via_ledger(0.08)
    seen = {}

    def fake_dialog(t, amount, currency, vendor, purpose, quantity, breaches=None):
        seen["breaches"] = breaches
        return True

    monkeypatch.setattr(gate, "_confirm_dialog", fake_dialog)
    ap = gate.require_approval(0.05, vendor="openai", purpose="test")
    assert ap.amount == 0.05
    assert seen["breaches"] and seen["breaches"][0].period == "day"
    rows = [json.loads(x) for x in
            open(tmp_path / "audit.jsonl", encoding="utf-8").read().splitlines()]
    assert rows[-1]["result"] == "approved"
    assert rows[-1]["over_limit"]


def test_soft_limit_cancel_denies(monkeypatch, tmp_path):
    policy.save(policy.Policy(daily_limit=0.10), require_auth=False)
    spend_via_ledger(0.08)
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: False)
    with pytest.raises(gate.SpendNotApproved):
        gate.require_approval(0.05)
    rows = [json.loads(x) for x in
            open(tmp_path / "audit.jsonl", encoding="utf-8").read().splitlines()]
    assert rows[-1]["result"] == "denied"


def test_limit_breach_describe_is_readable():
    b = policy.LimitBreach("day", 8.0, 10.0, 5.0)
    assert "8.00 + 5.00 = 13.00 > 10.00" in b.describe()
