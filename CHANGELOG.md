# Changelog

## 0.1.0 — 2026-11-22

First public release.

- Two gates: an AppleScript confirmation dialog (default button is *Cancel*) followed by macOS `LocalAuthentication` (`deviceOwnerAuthentication`, Touch ID with password fallback).
- Fail-closed on every path: non-macOS, missing biometrics, timeout, user cancel, and audit-write failure all raise `SpendNotApproved`.
- Append-only audit log at `~/.spend-gate/audit.jsonl`, overridable with `SPEND_GATE_AUDIT_PATH`.
- Localized dialog and prompt text for English, Simplified Chinese, Traditional Chinese and Japanese, following the macOS UI language.
- CLI: `spend-gate doctor | approve | audit`.
