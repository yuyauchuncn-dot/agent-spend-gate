# agent-spend-gate

A human-in-the-loop spending gate for AI agents on macOS — **no Touch ID or password approval, no paid API call.**

Your agent is about to call a paid API. This library makes it ask you first: a dialog spells out who gets paid, how much, and for what; then macOS asks for your fingerprint or password. If either step fails, the call never happens.

```
┌─ Approval ──────────────────────────────┐
│ openai/gpt-4o requests 2.00 CNY for:    │
│ summarise 10 documents                  │
│ Quantity: 10 calls                      │
│                                         │
│            [ Cancel ]  [ Approve ]      │
└─────────────────────────────────────────┘
              ↓ approved
┌─ macOS ─────────────────────────────────┐
│  🔒 Touch ID to approve spending        │
│  2.00 CNY to openai/gpt-4o              │
└─────────────────────────────────────────┘
```

## Install

```bash
pip install agent-spend-gate
```

macOS only for now. On any other platform the gate fails closed — it will refuse to let a call through rather than silently skip the check.

## Use it

```python
from spend_gate import require_approval, SpendNotApproved

try:
    require_approval(
        amount=2.0,                 # compute this as quantity x unit price
        currency="CNY",
        vendor="openai/gpt-4o",
        purpose="summarise 10 documents",
        quantity="10 calls",
    )
except SpendNotApproved:
    raise SystemExit("not approved, nothing was spent")

# Only reached after a human passed both gates.
client.chat.completions.create(...)
```

Wrap it around **every** billable call. If you batch, call it once for the batch and pass the batch total.

### When the total isn't known upfront

Approve a **cap**, not an amount. Open an envelope: one Touch ID prompt for "up to 10 CNY", then every call inside it is accounted for without interrupting you.

```python
from spend_gate import open_envelope

with open_envelope(max_amount=10.0, currency="CNY", vendor="openai",
                   purpose="nightly summarisation", ttl_hours=24) as env:
    for doc in docs:
        rid = env.reserve(0.50)        # hold capacity before the call
        cost = call_api(doc)           # actual cost, known only afterwards
        env.settle(rid, cost)          # charge what it really cost

# The envelope stops accepting charges when the cap or TTL is reached.
# Call open_envelope again to ask a human for more.
```

`env.spend(x)` is the shortcut when you know the price. `env.reserve` / `env.settle` is for when you don't. An exception inside `reservation()` charges the held amount (conservative). Every event goes into a hash-chained ledger; `spend-gate verify` tells you if it has been edited.

## How it works

1. **Cognitive gate** — an AppleScript dialog shows vendor, amount, purpose and quantity. The default button is *Cancel*, so hitting Return does not approve.
2. **Identity gate** — `LocalAuthentication` (`LAPolicyDeviceOwnerAuthentication`) asks for Touch ID, falling back to the account password. This is a different path from `sudo`/PAM, which is why the usual `pam_tid` recipes do not produce a fingerprint prompt here.
3. **Audit** — every attempt is appended to `~/.spend-gate/audit.jsonl` (approved, denied, or bypassed), including timestamp, amount, vendor, purpose and method. If the log cannot be written on the approval path, approval is refused: a spend must never happen without a record.

## The boundary — read this before trusting it

This is a **seatbelt, not a safe.**

- **What it defends**: an agent or script running as *you* deciding to spend money on its own. Both gates require a human action, and every attempt leaves a record.
- **What it does not defend**: anyone who can edit this library's code, set environment variables, or obtain root. They can remove the gate entirely. It also does not defend against a compromised dependency or a user under physical duress.

The value is forcing human-in-the-loop and leaving a trail, not resisting a determined local attacker. See [SECURITY.md](SECURITY.md).

### Tiny charges you don't want to approve one by one

Off by default. Turn it on deliberately:

```bash
spend-gate policy set --auto-under 0.05 --daily-cap 1.00
```

Now single charges at or below `0.05` pass without a prompt, as long as today's total spend stays under `1.00`.

### Ceilings you cannot quietly exceed

```bash
spend-gate policy set --daily-limit 20 --weekly-limit 80 --monthly-limit 200
```

These are period ceilings across **everything**, independent of envelopes — opening ten envelopes does not get around them. When a charge would cross one, the dialog changes:

```
Budget limit reached
openai/gpt-4o requests 5.00 CNY for: batch job

This would exceed your daily limit:
day: 18.00 + 5.00 = 23.00 > 20.00

Approve anyway?
```

Approving is recorded in the audit log with an `over_limit` field, so you get both the override and the trail.

The limit dialog has three buttons: **Just this once**, **Allow for this day**, or **Cancel**. Choosing "allow for this period" writes a waiver that lasts until the period ends, so a long job keeps running instead of stopping at every file.

### Per-vendor limits and a whitelist

```bash
spend-gate policy set --vendor dashscope --vendor-daily-limit 5 --vendor-trusted
spend-gate policy set --vendor openai --vendor-daily-limit 20
```

`--vendor` takes a prefix, longest match wins, so `dashscope/wanx2.1-t2i` is covered by `dashscope`. A **trusted** vendor skips the dialog while it stays inside both its own limit and the global ones — it removes the interruption, not the ceiling. Everything else still prompts. Each one is written to the ledger, so the daily cap is enforced from the same numbers you can audit. Changing the policy requires Touch ID or your password — an agent cannot raise its own limit. The policy file is HMAC-signed with a key held in your login Keychain — editing the JSON by hand invalidates the signature, and an invalid signature means **nothing** is auto-approved.

## Environment variables

| Variable | Purpose |
|---|---|
| `SPEND_GATE_AUDIT_PATH` | Override the audit log path (tests, enterprise deployments). |
| `SPEND_GATE_BYPASS=1` | **Skips both gates.** Only for automated tests. Setting this in production removes the gate; each use is recorded as `bypassed`. Any other value (e.g. `true`) is ignored. |
| `SPEND_GATE_HOME` | Override `~/.spend-gate` (envelopes, policy, ledger). |
| `SPEND_GATE_LEDGER_PATH` | Override the ledger path specifically. |
| `SPEND_GATE_NO_KEYCHAIN=1` | Run without a Keychain: anchor checks are skipped and reported as such. Policy changes still require authentication. |

## Languages

Dialog and Touch ID prompt follow the macOS UI language. Currently shipped: English, Simplified Chinese, Traditional Chinese, Japanese. Missing languages fall back to English. Add a file under `src/spend_gate/locales/` to contribute one — a test checks every locale has the same keys.

## CLI

```bash
spend-gate doctor          # can this machine enforce approval?
spend-gate approve --amount 0.01 --vendor demo --purpose "smoke test"
spend-gate audit --tail 20
spend-gate verify                    # hash chain + Keychain anchor
spend-gate policy show|set --auto-under 0.05 --daily-cap 1.00
```

## Roadmap

- v0.1 — two gates, audit trail, i18n
- v0.2 — budget envelopes for batch spending, reserve/settle, hash-chained ledger (`spend-gate verify`)
- v0.3 — Keychain-anchored ledger head, per-call auto-approve threshold
- v0.4 — global daily/weekly/monthly ceilings with an override dialog, hard-limit mode (this release)
- Next — per-vendor budgets, export to OpenTelemetry
- Homebrew tap once the CLI needs one

## License

Apache-2.0. See [LICENSE](LICENSE).
