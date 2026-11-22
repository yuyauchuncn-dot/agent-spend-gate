# -*- coding: utf-8 -*-
"""语言匹配测试：系统标签带地区时也要选对文案表。"""
import pytest

from spend_gate import i18n


@pytest.mark.parametrize("tag,want", [
    ("en-JP", "en"),
    ("en-GB", "en"),
    ("zh-Hans-CN", "zh-Hans"),
    ("zh-Hant-TW", "zh-Hant"),
    ("zh-TW", "zh-Hant"),
    ("zh-CN", "zh-Hans"),
    ("zh", "zh-Hans"),
    ("ja-JP", "ja"),
    ("ko-KR", "ko"),
    ("de-AT", "de"),
    ("fr-CA", "fr"),
    ("es-419", "es"),
    ("yue-Hant-HK", "zh-Hant"),
])
def test_candidates_hit_supported(tag, want):
    cands = i18n._candidates(tag)
    assert want in cands


def test_resolve_picks_first_supported(monkeypatch):
    monkeypatch.setattr(i18n, "detect_languages", lambda: ["xx-YY", "en-US"])
    assert i18n.resolve() == "en"


def test_resolve_prefers_system_order(monkeypatch):
    monkeypatch.setattr(i18n, "detect_languages", lambda: ["ja-JP", "en-US"])
    assert i18n.resolve() == "ja"


def test_translator_falls_back_to_key_for_missing():
    t = i18n.Translator("en")
    assert t("no_such_key") == "no_such_key"


def test_all_locales_have_same_keys():
    import json, os
    base = os.path.join(i18n.LOCALES, "en.json")
    keys = set(json.load(open(base, encoding="utf-8")))
    for lang in i18n.SUPPORTED:
        p = os.path.join(i18n.LOCALES, f"{lang}.json")
        assert os.path.exists(p), p
        assert set(json.load(open(p, encoding="utf-8"))) == keys, lang
