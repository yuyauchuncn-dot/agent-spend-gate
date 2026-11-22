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
- **Audit log integrity.** Entries are append-only by convention, not by enforcement. The log is a plain file writable by the same user the agent runs as. Future releases add a hash chain and a Keychain anchor so deletion or rollback can be detected — but a suffix rewrite after the most recent anchor cannot be prevented locally.
- **No spend caps yet.** v0.1 gates every call. Per-call and per-period budgets are on the roadmap.
- **macOS only.** Notebooks without a biometric sensor fall back to the account password; machines without either fail closed.

## Reporting a vulnerability

Open a private security advisory on GitHub, or email the maintainer listed in `pyproject.toml`. Please do not open a public issue for anything that weakens the gates.
