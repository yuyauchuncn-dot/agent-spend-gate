# Security policy

## Threat model

**Defends against:** an AI agent or automated script running under the same user account deciding to spend money without a human present. Both gates require a deliberate human action (a click that defaults to *Cancel*, then Touch ID or the account password). Every attempt — approved, denied, or bypassed — is appended to the audit log.

**Does not defend against:**

- Anyone who can edit this library's source or install a modified version.
- Anyone who can set environment variables (`SPEND_GATE_BYPASS=1` removes both gates).
- Root, or a process with `sudo` access.
- A compromised dependency or supply-chain attack.
- Physical coercion of the person approving.

This module raises the cost of an agent acting on its own and leaves an audit trail. It is not a defense against a malicious local attacker.

## Known limitations

- **Authentication method is not observable.** `LocalAuthentication` does not reveal whether the user used Touch ID or typed a password, so audit entries record `method: "unknown"`.
- **Two logs, different guarantees.** `audit.jsonl` records approval decisions and is append-only by convention only. `ledger.jsonl` records money movements and is hash-chained, so edits and deletions of existing rows are detectable. Neither resists a same-user attacker who rewrites the tail.
- **Ledger integrity.** The hash chain detects edits and deletions of existing rows. The head is anchored in your login Keychain and refreshed only when a human approves something, so a silent truncation or rollback shows up as a tail that no longer matches the anchor.
- **The anchor is not hardware-backed.** Once your login Keychain is unlocked, a process running as you can still read and replace the anchor item. It raises the cost of tampering; it is not a TPM.
- **Envelope files are writable by the same user.** `~/.spend-gate/envelopes/*.json` is accounting state, not a cryptographic lock. `spend-gate verify` reconciles each envelope's recorded `spent` against the ledger and reports a mismatch, so edits are detectable after the fact — not prevented.
- **Auto-approve policy.** `policy.json` carries an HMAC keyed from the Keychain; tampering invalidates it and disables auto-approval entirely. Changing the policy through the API or CLI requires Touch ID or your password. It does not stop someone who can read the Keychain key and re-sign, but that is no longer a one-line call.
- **macOS only.** Notebooks without a biometric sensor fall back to the account password; machines without either fail closed.

## Reporting a vulnerability

Open a private security advisory on GitHub, or email the maintainer listed in `pyproject.toml`. Please do not open a public issue for anything that weakens the gates.
