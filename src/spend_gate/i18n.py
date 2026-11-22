# -*- coding: utf-8 -*-
"""界面文案的本地化。

不引 NSLocalizedString / .lproj：那套要求 app bundle，我们是库不是 app。
直接读系统首选语言，加载同目录 locales/*.json。缺语言时按顺序回落。
"""
from __future__ import annotations

import json
import os
import plistlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCALES = os.path.join(HERE, "locales")
FALLBACK = "en"
SUPPORTED = ("en", "zh-Hans", "zh-Hant", "ja", "ko", "de", "fr", "es")

# 系统语言标签常带地区（en-JP、zh-Hans-CN、zh-Hant-HK）。
# 先按完整标签找，再退到语言+文字，再退到语言本身。
def _candidates(tag: str) -> list[str]:
    tag = tag.replace("_", "-")
    parts = tag.split("-")
    out = [tag]
    if len(parts) >= 2 and len(parts[1]) == 4:      # zh-Hans-CN -> zh-Hans
        out.append("-".join(parts[:2]))
    if parts[0] == "yue":          # 粤语用户读繁体
        out.append("zh-Hant")
    if parts[0] == "zh":
        # 中文必须区分简繁；没有文字标签时按地区猜，猜不到用简体。
        if any(p in ("TW", "HK", "MO") for p in parts[1:]):
            out.append("zh-Hant")
        else:
            out.append("zh-Hans")
    out.append(parts[0])
    return out


def detect_languages() -> list[str]:
    """返回系统偏好语言列表，第一个是首选。读不到就返回 [en]。"""
    if sys.platform != "darwin":
        return [FALLBACK]
    try:
        with open(os.path.expanduser("~/Library/Preferences/.GlobalPreferences.plist"), "rb") as f:
            langs = plistlib.load(f).get("AppleLanguages") or []
            if langs:
                return list(langs)
    except Exception:
        pass
    try:
        import subprocess
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"],
                             capture_output=True, text=True, timeout=5).stdout
        langs = [x.strip().strip('",') for x in out.splitlines() if x.strip().startswith('"')]
        if langs:
            return langs
    except Exception:
        pass
    return [FALLBACK]


_CACHE: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang in _CACHE:
        return _CACHE[lang]
    path = os.path.join(LOCALES, f"{lang}.json")
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    _CACHE[lang] = data
    return data


def resolve() -> str:
    """选出第一个有文案表的系统语言。"""
    for tag in detect_languages():
        for cand in _candidates(tag):
            if cand in SUPPORTED and os.path.exists(os.path.join(LOCALES, f"{cand}.json")):
                return cand
    return FALLBACK


class Translator:
    def __init__(self, lang: str | None = None):
        self.lang = lang or resolve()
        self._table = _load(self.lang)
        self._fallback = _load(FALLBACK)

    def __call__(self, key: str, **fmt) -> str:
        s = self._table.get(key) or self._fallback.get(key) or key
        try:
            return s.format(**fmt)
        except Exception:
            return s
