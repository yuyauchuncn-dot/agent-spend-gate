# Changelog

## 0.4.0 — 2026-11-22

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
