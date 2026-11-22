# -*- coding: utf-8 -*-
"""0.5：按供应商分类限额 + 白名单。"""
import json

import pytest

from spend_gate import auth, budget, gate, keychain, policy

KEY = b"\x03" * 32


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEND_GATE_HOME", str(tmp_path))
    monkeypatch.setenv("SPEND_GATE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("SPEND_GATE_BYPASS", raising=False)
    monkeypatch.setattr(keychain, "available", lambda: False)
    monkeypatch.setattr(keychain, "get_or_create_policy_key", lambda: KEY)
    monkeypatch.setattr(auth, "authenticate", lambda *a, **k: auth.AuthResult(True, "unknown"))
    return tmp_path


def save(**kw):
    policy.save(policy.Policy(**kw), require_auth=False)


def test_prefix_match_longest_wins():
    save(vendors={"dashscope": {"daily_limit": 5},
                  "dashscope/wanx": {"daily_limit": 1}})
    p, _ = policy.load()
    key, _cfg = policy._vendor_entry(p, "dashscope/wanx2.1-t2i")
    assert key == "dashscope/wanx"


def test_vendor_limit_breached():
    save(vendors={"dashscope": {"daily_limit": 5}})
    b = policy.check_vendor_limits(6, "dashscope/wanx2.1")
    assert len(b) == 1 and b[0].limit == 5


def test_vendor_limit_one_ledger_per_vendor():
    save(vendors={"openai": {"daily_limit": 1}, "dashscope": {"daily_limit": 1}})
    from spend_gate.ledger import default_ledger
    default_ledger().append({"event": "spend", "vendor": "openai", "currency": "CNY",
                             "amount": 0.9})
    assert policy.check_vendor_limits(0.2, "openai/gpt-4o") != []
    assert policy.check_vendor_limits(0.2, "dashscope/wanx") == []


def test_trusted_skips_prompt_within_limits(monkeypatch, tmp_path):
    save(vendors={"dashscope": {"trusted": True, "daily_limit": 5}})
    called = {"dialog": False}

    def no_dialog(*a, **k):
        called["dialog"] = True
        return "cancel"

    monkeypatch.setattr(gate, "_confirm_dialog", no_dialog)
    ap = gate.require_approval(0.5, vendor="dashscope/wanx")
    assert ap.method == "auto" and called["dialog"] is False


def test_trusted_still_blocked_by_global_limit(monkeypatch):
    save(daily_limit=1.0, vendors={"dashscope": {"trusted": True}})
    from spend_gate.ledger import default_ledger
    default_ledger().append({"event": "spend", "vendor": "other", "currency": "CNY",
                             "amount": 0.9})
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: "cancel")
    with pytest.raises(gate.SpendNotApproved):
        gate.require_approval(0.5, vendor="dashscope/wanx")


def test_untrusted_vendor_still_prompts(monkeypatch):
    save(vendors={"dashscope": {"daily_limit": 5}})
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: "once")
    ap = gate.require_approval(0.5, vendor="dashscope/wanx")
    assert ap.method != "auto"


def test_vendor_config_survives_roundtrip():
    save(vendors={"dashscope": {"daily_limit": 5, "trusted": True}})
    p, ok = policy.load()
    assert ok and p.vendors["dashscope"]["trusted"] is True
