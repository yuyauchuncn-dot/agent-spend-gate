# Changelog

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
