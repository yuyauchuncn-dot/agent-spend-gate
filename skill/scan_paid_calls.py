#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描仓库里的付费 API 调用点。

用法: python3 scan_paid_calls.py <repo-root> [--json]

只看代码文本，不执行、不联网。结果按 vendor 汇总，供 skill 询问用户。
"""
import json
import os
import re
import sys

# vendor → (SDK 导入/引用模式, 端点模式)
# 只在「真调用」行周围 ±8 行里找 vendor，避免把注释里的品牌名算进来。
VENDORS = {
    "openai":     (r"\bopenai\b|from\s+openai|require\(['\"]openai", r"api\.openai\.com"),
    "anthropic":  (r"\banthropic\b|from\s+anthropic", r"api\.anthropic\.com"),
    "dashscope":  (r"\bdashscope\b", r"dashscope(-[a-z]+)?\.aliyuncs\.com"),
    "elevenlabs": (r"\belevenlabs\b|eleven_multilingual", r"api\.elevenlabs\.io"),
    "replicate":  (r"\breplicate\b", r"api\.replicate\.com"),
    "fal":        (r"\bfal_client\b|\bfal\.run\b", r"fal\.run|queue\.fal\.ai"),
    "stripe":     (r"\bstripe\b", r"api\.stripe\.com"),
    "gemini":     (r"google\.generativelanguage|genai\b", r"generativelanguage\.googleapis\.com"),
}

EXTS = (".py", ".js", ".ts", ".mjs", ".cjs", ".go", ".rb", ".sh")

# 真正发起网络请求的形状。只有这些才算「调用点」——光提到 vendor 名字
# （注释、分支判断、品牌字符串）不算，否则一个 40 文件的仓库会报出 215 处，
# 全是噪声，人就不看了。
CALL_PATTERNS = [
    r"requests\.(post|get|put|patch|delete)\(",
    r"httpx\.(post|get|put|patch|delete)\(",
    r"urlopen\(",
    r"\.chat\.completions\.create\(",
    r"\.messages\.create\(",
    r"\.images\.generate\(",
    r"\.audio\.speech\(",
    r"subprocess\.run\(\[.*curl",
    r"fetch\(",
    r"axios\.(post|get)\(",
]
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "__pycache__", ".next"}


def scan(root):
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(EXTS):
                continue
            path = os.path.join(dirpath, fn)
            try:
                lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if s.startswith("#") or s.startswith("//"):
                    continue
                if not any(re.search(pat, s) for pat in CALL_PATTERNS):
                    continue
                blob = "\n".join(lines[max(0, i - 8):i + 4]).lower()
                vendor = "unknown"
                for v, (sdk_pat, url_pat) in VENDORS.items():
                    if re.search(url_pat, blob, re.I) or re.search(sdk_pat, blob, re.I):
                        vendor = v
                        break
                hits.append({
                    "file": os.path.relpath(path, root),
                    "line": i,
                    "vendor": vendor,
                    "kind": "call",
                    "snippet": s[:160],
                })
    return hits


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    hits = scan(root)
    summary = {}
    for h in hits:
        summary.setdefault(h["vendor"], {"count": 0, "files": set()})
        summary[h["vendor"]]["count"] += 1
        summary[h["vendor"]]["files"].add(h["file"])

    if "--json" in sys.argv:
        print(json.dumps({"hits": hits,
                          "summary": {k: {"count": v["count"], "files": sorted(v["files"])}
                                      for k, v in summary.items()}},
                         ensure_ascii=False, indent=1))
        return

    if not hits:
        print("没有找到付费 API 调用。如果确实是付费项目，检查是否用了别名导入。")
        return
    print(f"共 {len(hits)} 处调用，涉及 {len(summary)} 个供应商：\n")
    for vendor, v in sorted(summary.items(), key=lambda x: -x[1]["count"]):
        print(f"  {vendor:11} {v['count']:3} 处  {len(v['files'])} 个文件")
        for f in sorted(v["files"])[:5]:
            print(f"      {f}")
        if len(v["files"]) > 5:
            print(f"      … 另有 {len(v['files']) - 5} 个文件")


if __name__ == "__main__":
    main()
