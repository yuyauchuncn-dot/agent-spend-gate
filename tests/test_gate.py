# -*- coding: utf-8 -*-
"""闸门逻辑测试。全部 mock 系统调用，不弹任何窗。"""
import json
import os

import pytest

from spend_gate import gate
from spend_gate.auth import AuthResult


@pytest.fixture(autouse=True)
def tmp_audit(tmp_path, monkeypatch):
    p = tmp_path / "audit.jsonl"
    monkeypatch.setenv("SPEND_GATE_AUDIT_PATH", str(p))
    monkeypatch.delenv("SPEND_GATE_BYPASS", raising=False)
    return p


def read_audit(p):
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_both_gates_pass(tmp_audit, monkeypatch):
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: True)
    monkeypatch.setattr(gate.auth, "authenticate", lambda *a, **k: AuthResult(True, "unknown"))
    approval = gate.require_approval(1.5, vendor="openai/gpt-4o", purpose="test",
                                     quantity="1 call")
    assert approval.amount == 1.5
    assert approval.vendor == "openai/gpt-4o"
    rows = read_audit(tmp_audit)
    assert len(rows) == 1 and rows[0]["result"] == "approved"


def test_dialog_cancel_denies(tmp_audit, monkeypatch):
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: False)
    with pytest.raises(gate.SpendNotApproved) as e:
        gate.require_approval(1.0)
    assert e.value.reason == "cancelled"
    assert read_audit(tmp_audit)[0]["result"] == "denied"


def test_auth_cancel_denies(tmp_audit, monkeypatch):
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: True)
    monkeypatch.setattr(gate.auth, "authenticate",
                        lambda *a, **k: AuthResult(False, "unknown", "cancelled"))
    with pytest.raises(gate.SpendNotApproved):
        gate.require_approval(1.0)
    assert read_audit(tmp_audit)[0]["detail"] == "cancelled"


def test_auth_unavailable_denies(tmp_audit, monkeypatch):
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: True)
    monkeypatch.setattr(gate.auth, "authenticate",
                        lambda *a, **k: AuthResult(False, "unknown", "unavailable"))
    with pytest.raises(gate.SpendNotApproved):
        gate.require_approval(1.0)


def test_non_macos_denies(tmp_audit, monkeypatch):
    monkeypatch.setattr(gate.sys, "platform", "linux")
    with pytest.raises(gate.SpendNotApproved) as e:
        gate.require_approval(1.0)
    assert e.value.reason == "unavailable"
    assert read_audit(tmp_audit)[0]["detail"] == "not macOS"


def test_bypass_only_literal_one(tmp_audit, monkeypatch):
    monkeypatch.setenv("SPEND_GATE_BYPASS", "true")
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: False)
    with pytest.raises(gate.SpendNotApproved):
        gate.require_approval(1.0)
    monkeypatch.setenv("SPEND_GATE_BYPASS", "1")
    a = gate.require_approval(1.0)
    assert a.method == "bypass"
    assert read_audit(tmp_audit)[-1]["result"] == "bypassed"


def test_audit_write_failure_blocks_approval(tmp_audit, monkeypatch):
    monkeypatch.setattr(gate, "_confirm_dialog", lambda *a, **k: True)
    monkeypatch.setattr(gate.auth, "authenticate", lambda *a, **k: AuthResult(True, "unknown"))

    def boom(*a, **k):
        raise gate.audit.AuditWriteError("disk full")

    monkeypatch.setattr(gate.audit, "record", boom)
    with pytest.raises(gate.audit.AuditWriteError):
        gate.require_approval(1.0)


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "2"])
def test_invalid_amount_rejected(bad):
    with pytest.raises(ValueError):
        gate.require_approval(bad)


def test_applescript_escaping():
    s = gate._applescript_string('a "quoted" \\ path')
    assert '\\"' in s and "\\\\" in s
