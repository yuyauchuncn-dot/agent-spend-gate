# Setup skill

Two files, no install:

- `scan_paid_calls.py` — finds call sites that actually make a network request to a paid API
- `SKILL.md` — the procedure an agent follows: scan, ask, configure, wrap, report

```bash
python3 skill/scan_paid_calls.py /path/to/repo
```

It deliberately reports **real calls only**. Vendor names in comments, branch conditions and brand strings are not calls; counting them produces a number nobody acts on. On one 40-file repo the difference was 215 versus 3.

This lives in the main repository rather than its own because it calls the `spend-gate` CLI, and the two have to version together.
