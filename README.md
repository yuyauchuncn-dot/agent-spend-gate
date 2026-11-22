# agent-spend-gate

**Your AI agent is about to spend money. This makes it ask you first.**

> **Adopting this in an existing repo?** [`skill/`](skill/) scans for paid API calls, asks once which vendors should stay behind a prompt, and wraps the call sites. One fingerprint for the whole policy. [Read the case study](docs/CASE-STUDY.md) — 215 apparent call sites turned out to be 3 real ones.

One line before the paid call. A dialog says who gets paid and how much. Then macOS asks for your fingerprint or password. If either step fails, the call never happens.

```
┌─ Spending approval ─────────────────────┐
│ openai/gpt-4o requests 2.00 CNY for:    │
│ summarise 10 documents                  │
│ Quantity: 10 calls                      │
│                                         │
│            [ Cancel ]  [ Approve ]      │
└─────────────────────────────────────────┘
              ↓ you click Approve
┌─ macOS ─────────────────────────────────┐
│  🔒 Touch ID                             │
│  Approve spending 2.00 CNY to openai    │
└─────────────────────────────────────────┘
              ↓ fingerprint accepted
        the API call runs
```

## Install

```bash
pip install agent-spend-gate
```

macOS only, Python 3.11+. On any other platform the gate **refuses** — it does not silently skip the check.

## The one thing you have to do

Put `require_approval` in front of every billable call.

```python
from spend_gate import require_approval

require_approval(amount=2.0, currency="CNY",
                 vendor="openai/gpt-4o",
                 purpose="summarise 10 documents",
                 quantity="10 calls")

# Only reached after a human approved. Now spend.
client.chat.completions.create(...)
```

If you do not wrap a call, that call is not protected. The gate is opt-in per call site — there is no interception layer, and nothing fails loudly when you miss one. **That is the single most important thing to understand about this library.**

## Three ways to spend, pick one

| Situation | Use | Prompts |
|---|---|---|
| You know the price | `require_approval(amount=...)` | one per call |
| A job whose total you don't know | `open_envelope(max_amount=...)` | one per job, then charges run inside it |
| Many calls, small amounts | auto-approve policy | none, until a ceiling is hit |

### Envelope: when the total isn't known upfront

```python
from spend_gate import open_envelope

with open_envelope(max_amount=10.0, vendor="openai",
                   purpose="nightly summarisation", ttl_hours=24) as env:
    for doc in docs:
        rid = env.reserve(0.50)     # hold capacity first
        cost = call_api(doc)        # actual cost, known only afterwards
        env.settle(rid, cost)       # charge what it really cost
```

One approval for "up to 10 CNY". Charges inside it do not prompt. It stops accepting charges when the cap or the 24 hours runs out. If you already know the price, `env.spend(0.05)` is the shortcut.

### Ceilings: what a day, week or month may cost

```bash
spend-gate policy set --daily-limit 20 --weekly-limit 80 --monthly-limit 200
```

These apply to **all** spending, regardless of envelopes. Opening ten envelopes does not get around them.

When a charge would cross one, the dialog changes and tells you by how much:

```
Budget limit reached
openai/gpt-4o requests 5.00 CNY for: batch job

This would exceed your daily limit:
daily: 18.00 + 5.00 = 23.00 > 20.00

[ Cancel ]  [ Just this once ]  [ Allow for this day ]
```

"Allow for this day" writes a waiver until the period ends, so a long job keeps running instead of prompting at every file.

### Per-vendor limits and whitelist

```bash
spend-gate policy set --vendor dashscope --vendor-daily-limit 5 --vendor-trusted
```

`--vendor` is a prefix; longest match wins, so `dashscope/wanx2.1-t2i` is covered by `dashscope`.

**Trusted** means: skip the dialog for this vendor *while it stays inside its own and the global ceilings*. It removes the interruption, not the limit. Exceed any ceiling and you are asked again.

## What it does and does not protect

**Protects:** an agent or script running as you deciding to spend on its own. Both gates need a human action, and every attempt is recorded.

**Does not protect:** anyone who can edit this library (including an agent that can edit its own code), set `SPEND_GATE_BYPASS=1`, or obtain root. A call site you forgot to wrap is unprotected too.

This is a seatbelt, not a safe. Read [SECURITY.md](SECURITY.md) before trusting it with real money.

## Every attempt is recorded

Two files under `~/.spend-gate/`:

- `audit.jsonl` — each approval decision: amount, vendor, purpose, method, result
- `ledger.jsonl` — each money movement, hash-chained. `spend-gate verify` detects edited or deleted rows and checks the head against a Keychain checkpoint.

```bash
spend-gate verify      # ledger chain + envelope reconciliation
spend-gate audit       # recent decisions
```

## Commands

```bash
spend-gate doctor                      # can this machine enforce approval?
spend-gate approve --amount 0.01 --vendor demo --purpose "smoke test"
spend-gate verify
spend-gate audit --tail 20
spend-gate policy show
spend-gate policy set --auto-under 0.05 --daily-limit 20
spend-gate policy set --vendor openai --vendor-daily-limit 20 --vendor-trusted
spend-gate policy load policy.json     # batch, one fingerprint for all
```

## Environment variables

| Variable | Purpose |
|---|---|
| `SPEND_GATE_HOME` | Override `~/.spend-gate` |
| `SPEND_GATE_LEDGER_PATH` | Override the ledger path |
| `SPEND_GATE_AUDIT_PATH` | Override the audit path |
| `SPEND_GATE_NO_KEYCHAIN=1` | Run without a Keychain; anchor checks report as skipped |
| `SPEND_GATE_BYPASS=1` | **Skips both gates.** Tests only. Every use is logged as `bypassed`. |

## Languages

Dialog, limit warning and Touch ID prompt follow the macOS UI language: English, Simplified Chinese, Traditional Chinese, Japanese, Korean, German, French, Spanish. Cantonese maps to Traditional Chinese; anything else falls back to English. Adding a language is a copy of `en.json` — a test fails if keys are missing.

## Wrapping an existing codebase

The skill lives in [`skill/`](skill/) and ships with this repository — no separate install.

```bash
python3 skill/scan_paid_calls.py /path/to/repo     # what actually costs money
```

Then point your agent at [`skill/SKILL.md`](skill/SKILL.md). It asks four questions, writes the policy, applies it in one authenticated call, and wraps the call sites. It also requires the agent to list what it did **not** wrap and why.

Why it is bundled rather than a separate repository: the skill depends on this CLI's flags, so the two must version together, and the files are small enough that a second repo would only add a way for them to drift.

## License

Apache-2.0.
