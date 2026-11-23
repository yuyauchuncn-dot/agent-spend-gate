# Changelog

## 0.7.2 — 2026-11-23

- Fix the period button reading "Allow for this daily" (and the Chinese
  "本每日都放行"). Each period now has its own full phrase in all eight
  locales. Caught in a real dialog, not by tests — key-parity checks do not
  know that "daily" does not belong inside "Allow for this ___".

## 0.7.1 — 2026-11-23

- **[Case study](docs/CASE-STUDY.md)**: a real adoption on a 40-file repository, from the incident that started it to the batch-approval problem that only showed up when imagining daily use. Includes the wrong numbers (215 call sites reported, 3 real) because that is the part worth reading.
- The setup skill is now linked from the top of the README, with its own `skill/README.md`. It stays in this repository rather than a separate one: it calls this CLI, so the two must version together.

## 0.7.0 — 2026-11-22

- `spend-gate policy load policy.json` — apply a whole policy in one call, so a whitelist for five vendors costs one fingerprint instead of five.
- New skill in `skill/`: scans a repository for paid API calls, asks which vendors should stay behind a prompt, writes the policy, and wraps the call sites. Tested against a real 215-call repository.
- README rewritten around the three spending modes and the one thing that actually matters: an unwrapped call is unprotected and nothing tells you.

## 0.6.0 — 2026-11-22

- **Korean, German, French and Spanish** locales, alongside the existing English, Simplified Chinese, Traditional Chinese and Japanese. Cantonese maps to Traditional Chinese.
- **No UI string is hardcoded any more.** The policy-change prompt, the envelope cap wording and the `day/week/month` labels inside the limit dialog all go through the locale files.
- Limit amounts in the dialog are formatted consistently (`18.00 + 5.00 = 23.00 > 20.00`) instead of mixing `0.9` and `0.90`.
- 69 tests, including key parity across all eight locales.

## 0.5.0 — 2026-11-22

- **Per-vendor limits**: `--vendor dashscope --vendor-daily-limit 5`, prefix-matched with longest match winning.
- **Vendor whitelist**: `--vendor-trusted` skips the dialog for that vendor while it stays inside its own and the global ceilings. It removes the interruption, not the limit.
- **Period waiver**: the limit dialog gains "Allow for this day/week/month", so an approved long job keeps running instead of prompting at every charge. Waivers expire with the period.
- 64 tests.

## 0.4.1 — 2026-11-22

Fixes from a second review.

- Auto-approved charges no longer skip the global ceilings: a stream of tiny auto-approved calls could previously spend past a hard limit.
- Manually approved charges are written to the ledger. Without this the ceilings were blind to the largest spends.
- `AuditWriteError` is wrapped in `SpendNotApproved`, so callers that only catch that exception do not crash on an unwritable audit log.
- Opening an envelope no longer double-counts its cap as a spend.
- 0.4.0

- **Daily, weekly and monthly ceilings** across all spending, independent of envelopes. Previously an agent could open any number of envelopes and never hit a total limit.
- Crossing a ceiling opens a distinct dialog that shows what was already spent, the pending charge, and the resulting total. Approving it is recorded with an `over_limit` field rather than silently allowed.
- `hard_limit` refuses instead of asking, for unattended services.
- `spend-gate policy set --daily-limit --weekly-limit --monthly-limit --hard-limit`.
- 56 tests.

## 0.3.1 — 2026-11-22

Security and correctness fixes from an external review.

**The gate could be opened without a human.** `policy.save()` and
`spend-gate policy set` raised the auto-approve threshold with no
authentication, which defeats the entire point. Both now require Touch ID
or the account password.

- Auto-approved charges are written to the ledger. Without this the daily
  cap was always computed from an empty ledger and never fired.
- `Ledger.append` holds a file lock across read-compute-write; two workers
  appending concurrently used to produce the same `seq` and a chain that
  failed verification during normal use.
- `Envelope` is a context manager, as the README always claimed.
- `settle()` refuses to run on an expired envelope; `_save` fsyncs before
  the atomic replace.
- `verify` reconciles every envelope's `spent` against the ledger, so a
  hand-edited envelope file shows up as a mismatch.
- Keychain reads distinguish "not found" from "denied"; a locked keychain
  no longer causes the policy key to be silently regenerated.
- `canEvaluatePolicy` failures are converted to a denied result instead of
  escaping as a raw PyObjC exception.
- Tests isolate `SPEND_GATE_HOME` and mock authentication; previously they
  read the real `~/.spend-gate` and would have hung on a fingerprint prompt.

## 0.3.0 — 2026-11-22

- **Keychain anchor**: the ledger head is written to the login Keychain whenever a human approves something. `spend-gate verify` now fails if the tail no longer matches the anchor, catching silent truncation and rollback that a pure hash chain cannot see.
- **Auto-approve policy** for tiny charges, off by default. `spend-gate policy set --auto-under 0.05 --daily-cap 1.00`. The policy file is HMAC-signed with a Keychain-held key; an invalid signature disables auto-approval rather than falling back to permissive behaviour.
- `spend-gate policy show|set`, `SPEND_GATE_NO_KEYCHAIN=1` to run without a Keychain (anchor checks reported as skipped).
- 46 tests, all without UI, network, or a real Keychain.

## 0.2.0 — 2026-11-22

- **Budget envelopes** for spending where the total isn't known upfront: `open_envelope(max_amount=..., ttl_hours=...)` asks for one approval covering a cap, then charges inside it proceed without prompting.
- `Envelope.spend()` for known prices; `reserve()` / `settle()` / `release()` and a `reservation()` context manager for costs discovered after the call. Exceptions charge the held amount rather than silently freeing it.
- **Hash-chained ledger** at `~/.spend-gate/ledger.jsonl`; `spend-gate verify` detects edited or deleted rows. Truncation and rollback detection need the Keychain anchor planned for 0.3.
- `flock` serialises every read-modify-write, so concurrent workers cannot each believe they still have headroom.
- CLI: `spend-gate envelope open|status`, `spend-gate verify`.
- 36 tests, all without UI or network.

## 0.1.0 — 2026-11-22

First public release.

- Two gates: an AppleScript confirmation dialog (default button is *Cancel*) followed by macOS `LocalAuthentication` (`deviceOwnerAuthentication`, Touch ID with password fallback).
- Fail-closed on every path: non-macOS, missing biometrics, timeout, user cancel, and audit-write failure all raise `SpendNotApproved`.
- Append-only audit log at `~/.spend-gate/audit.jsonl`, overridable with `SPEND_GATE_AUDIT_PATH`.
- Localized dialog and prompt text for English, Simplified Chinese, Traditional Chinese and Japanese, following the macOS UI language.
- CLI: `spend-gate doctor | approve | audit`.
