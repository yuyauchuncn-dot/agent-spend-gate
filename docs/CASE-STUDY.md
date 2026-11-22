# Case study: putting a gate on a 215-call repository

This is a real account, including the parts that went wrong.

## The incident

I asked an agent to generate ten illustrations with a paid image API. It did. Then it looked at the output, decided the composition was wrong, and generated ten more — same parameters, different aspect ratio — without asking. The second batch cost money I had not approved.

No rule was broken. There was no rule. I had said "go ahead" once, and the agent treated that as permission for everything downstream of it.

What I wanted was not a better rule. I wanted a mechanism that makes spending impossible without a human action, and leaves a record either way.

## First attempt: scan the repo

The repository has 40 Python files across several video channels. Running the scanner:

```
$ python3 skill/scan_paid_calls.py ~/Documents/monorepo/monovideo
共 215 处调用，涉及 5 个供应商
  openai       93 处  41 个文件
  anthropic    91 处  39 个文件
  elevenlabs   22 处  12 个文件
```

215 call sites. That number is wrong, and wrong in a way that matters: nobody reads past it.

The scanner was matching vendor names anywhere in a file. `elif spec.engine == "elevenlabs":` is not a call. A comment mentioning Anthropic is not a call. A brand name in a string is not a call.

## Second attempt: only count real requests

The scanner now requires an actual request shape — `requests.post`, `urlopen`, `curl` in a subprocess, an SDK `create` — and looks for the vendor only in the surrounding lines.

```
共 32 处调用，涉及 3 个供应商
  unknown      28 处  16 个文件
  elevenlabs    3 处   2 个文件
  dashscope     1 处   1 个文件
```

**Three billable call sites.** Not 215. The other 28 hit HuggingFace, web scraping and an OAuth token exchange — free.

This is the part that decides whether a tool gets used. A report claiming 215 problems gets closed. A report saying "three places, here they are" gets fixed.

## Configuring, in one prompt

The skill asks four questions: which vendors should stay behind a prompt, what the daily/weekly/monthly ceilings are, whether trusted vendors get their own limits, and whether an over-limit charge should be blocked or asked about.

Answers become one JSON file, applied in one call:

```
$ spend-gate policy load monovideo-policy.json
```

One confirmation dialog, one fingerprint. Five vendors would previously have meant five prompts.

The result:

```json
{
  "daily_limit": 5, "weekly_limit": 20, "monthly_limit": 60,
  "hard_limit": false,
  "vendors": {"elevenlabs": {"trusted": false}, "dashscope": {"trusted": false}}
}
```

## The problem a single-call API has at scale

Wrapping the three call sites took minutes. Then I looked at what it would be like to use.

`lib/voice.py` synthesises one sentence per call. A fifty-sentence episode would have meant fifty dialogs and fifty fingerprints. Nobody would keep the gate on.

So the library grew a batch mode:

```python
approve_batch(texts, purpose="HSK1 episode 1 narration")
try:
    for t in texts:
        await synthesize(t, spec, path)
finally:
    clear_batch()
```

One approval for the whole episode, charges deducted inside an envelope. Fifty sentences, one fingerprint. Without `approve_batch`, every call prompts — both behaviours exist, and which one you get is explicit in the code.

## What it costs to run

A 15-character sentence is about 0.03 CNY at the default rate. Fifty sentences is roughly 1.5 CNY. The daily ceiling is 5, so two to three episodes fit before the gate asks again.

The unit price is a default, not a fact — `ELEVENLABS_CNY_PER_KCHAR` overrides it once you know your plan's actual rate.

## What this does and does not buy you

It buys: no paid call without a human action; a ledger of every movement; a hard stop at a daily number; and one approval covering a whole job.

It does not buy: protection from an agent that edits its own code, or from a call site nobody wrapped. **A missed call site is silent.** That is the one thing to remember when adopting this.

## Timeline

- Incident to working gate: one evening.
- Scanning 215 false positives down to 3 real sites: the bulk of the work, and the most useful part.
- Wrapping three call sites: minutes.
- Discovering the per-sentence prompt problem: only by imagining real use.
- Total: the library is small; the care is in the scan and in whether you would actually leave the gate switched on.
