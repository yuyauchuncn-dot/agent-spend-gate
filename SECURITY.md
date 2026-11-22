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
- **Ledger integrity is local.** The hash chain detects edits and deletions of existing rows. It cannot detect a rewrite of everything after the last trusted anchor, because there is no trusted local time source. A Keychain-anchored head is planned for 0.3.
- **Envelope policy files are writable by the same user.** `~/.spend-gate/envelopes/*.json` uses mode-independent JSON. An agent with the same privileges can edit them; the ledger will show an inconsistency only when the edit diverges from recorded events. Treat the envelope as an accounting mechanism, not a cryptographic lock.
- **macOS only.** Notebooks without a biometric sensor fall back to the account password; machines without either fail closed.

## Reporting a vulnerability

Open a private security advisory on GitHub, or email the maintainer listed in `pyproject.toml`. Please do not open a public issue for anything that weakens the gates.
