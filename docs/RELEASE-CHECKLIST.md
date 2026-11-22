# Release checklist

Before `twine upload`, work down this list. Items marked ✅ were verified on 2026-11-23 for 0.7.1.

## A. Build artifact

```bash
rm -rf dist build && .venv/bin/python -m build
.venv/bin/twine check dist/*
unzip -l dist/*.whl | grep locales      # every locale must be inside
```

✅ 9 locale files present, `entry_points.txt` present, `twine check` passes for both wheel and sdist.

The failure this catches: `force-include` colliding with the default package contents, which silently drops files or refuses to build at all. It happened once already.

## B. Clean-environment install

```bash
python3 -m venv /tmp/sg-clean
/tmp/sg-clean/bin/pip install dist/*.whl
/tmp/sg-clean/bin/spend-gate doctor
```

✅ `auth backend: ok`, 8 locales resolve, policy reads back with a valid signature.

Then a real dialog, from the installed package rather than the source tree:

```bash
/tmp/sg-clean/bin/spend-gate approve --amount 0.01 --vendor "test/smoke" --purpose "smoke"
```

✅ Dialog appeared, fingerprint accepted, audit entry written with `result: approved`.

**Why from the wheel:** running from `src/` proves the source works. Only the installed package proves the package works — entry point, package data, import paths.

## C. TestPyPI round trip

Needs a TestPyPI account and token (`~/.pypirc`).

```bash
.venv/bin/twine upload --repository testpypi dist/*

python3 -m venv /tmp/sg-test && /tmp/sg-test/bin/pip install \
  -i https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  agent-spend-gate==0.7.1
/tmp/sg-test/bin/spend-gate doctor
```

`--extra-index-url` is required: `pyobjc-framework-LocalAuthentication` is not on TestPyPI, and without the fallback pip fails resolving it.

✅ 0.7.1 uploaded to TestPyPI and installed back from it:
<https://test.pypi.org/project/agent-spend-gate/0.7.1/>

- ✅ Upload succeeds
- ✅ Install from TestPyPI succeeds
- ✅ `doctor` reports `auth backend: ok`
- ✅ One real dialog from the TestPyPI build (fingerprint accepted, audit written)

## D. Real workload

Not a synthetic test — the repository this was built for.

✅ 2026-11-23, HSK1 "我的家", 49 sentences through ElevenLabs:

- ✅ Call sites wrapped (`lib/voice.py`, 2 sites, batch mode)
- ✅ `approve_batch` → one dialog for the whole episode
- ✅ 49 files, 126.2 s of audio, none shorter than 0.3 s
- ✅ `spend-gate audit`: one approval of 1.23 CNY plus the envelope charges
- ✅ `spend-gate verify`: 53 ledger rows, anchor row 52 ok, 2 envelopes reconciled

Actual cost 1.25 CNY. One bug found: `round()` down made the envelope 1.23
while per-sentence charges summed to 1.232, so the last sentence was
refused. `approve_batch` now rounds up to the cent.

## E. Failure paths

Each of these must **refuse**, never proceed:

```bash
SPEND_GATE_BYPASS=1 spend-gate approve --amount 1        # bypassed, and logged as such
SPEND_GATE_BYPASS=true spend-gate approve --amount 1     # NOT bypassed (only literal "1" works)
```

- [ ] Cancel the confirmation dialog → `SpendNotApproved`, exit 1
- [ ] Cancel the fingerprint prompt → same
- ✅ `--amount -5`, `nan`, `inf`, `True`, `"2"` → `ValueError`
- ✅ `SPEND_GATE_BYPASS=true` is not treated as bypass (only literal `"1"` is)
- ✅ Over a limit with `hard_limit` off → three-button dialog appeared.
  Choosing **Allow for this day** wrote the waiver `{'day'}`, the audit entry
  carried `over_limit` and `waived_periods`, and the next charge no longer
  reported an overrun (plain two-button dialog, no `over_limit` in the audit).
  The *Just this once* and *Cancel* branches are covered by unit tests only —
  each costs another fingerprint to test by hand.
- [ ] Over a limit with `hard_limit` on → same dialog, `hard_override` in the audit
- [ ] Lock the Keychain, then `spend-gate verify` → reports the anchor as unchecked rather than passing silently
- ✅ `verify` passes on a real ledger after live approvals
- [ ] Tamper with one row in `ledger.jsonl` → `verify` fails with `hash mismatch`
- [ ] Truncate the ledger below the anchor row → `verify` fails with `truncated`
- [ ] Change your macOS UI language to German or Korean → dialog text follows

## F. Upgrade path

- [ ] Install 0.7.1 over an earlier version; existing `policy.json`, envelopes and ledger still load
- [ ] `spend-gate verify` on the old ledger passes (legacy anchors report `re-approve to enable truncation checks`, not a failure)

## G. After publishing

- [ ] `pip install agent-spend-gate` from real PyPI in a fresh venv
- [ ] Tag the release: `git tag v0.7.1 && git push --tags`
- [ ] GitHub release with the CHANGELOG section

## Things this checklist cannot test

- A Mac without Touch ID (Intel MacBook without Touch Bar). Password fallback should work; nobody has verified it. Worth one manual run if you have the hardware.
- An Arabic or other RTL locale — not shipped, and `display dialog` RTL mixing is unverified.
- Windows and Linux — refused by design, and that refusal is covered by unit tests rather than a manual run.
