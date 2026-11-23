# 推广素材草稿

发布前核对：每个社区的自推版规。r/LocalLLaMA 和 r/AI_Agents 对自推有明确限制，很多要求账号有历史参与记录。

---

## Show HN

**Title**

```
Show HN: A macOS gate that makes AI agents ask for Touch ID before spending
```

**Body**

```
I let an agent generate ten illustrations with a paid API. It did, looked at
the output, decided the composition was wrong, and generated ten more with a
different aspect ratio. Nobody asked me.

There was no rule to break. I had said "go ahead" once, and it treated that as
permission for the rest of the session.

So I put a gate in front of the paid calls. require_approval() shows a dialog
with the vendor, amount and purpose, then macOS asks for Touch ID or your
password. If either step fails the call never happens.

Three things mattered more than the gate itself:

1. Wrapping a call site is easy; finding them is not. My first scanner
   reported 215 call sites in a 40-file repo. Most were comments and branch
   conditions that mentioned a vendor by name. The real number was 3. A report
   saying "215 problems" gets closed; "three, here they are" gets fixed.

2. A prompt per call is unusable at scale. One episode of narration is fifty
   sentences, which would have been fifty fingerprints. Nobody leaves a gate
   switched on like that. Hence budget envelopes: approve a cap once, then
   charges run inside it.

3. Two bugs only showed up in real use. The envelope rounded down, so the 49th
   sentence was refused over 0.002 CNY. And a button rendered as "Allow for
   this daily" because I plugged "daily" into "Allow for this ___". Unit tests
   checked that every locale had the same keys, not that the sentence reads.

What it does not do: stop an agent that edits its own code, or protect a call
site nobody wrapped. A missed call site is silent. It is a seatbelt, not a
safe.

macOS only, because it uses LocalAuthentication. Apache-2.0.

https://github.com/yuyauchuncn-dot/agent-spend-gate
```

---

## r/LocalLLaMA（技术向）

**Title**

```
I put a Touch ID gate in front of paid API calls, and wrote down where the design broke
```

**Body**

```
Context: an agent spent money I hadn't approved, twice, because "go ahead"
was interpreted as standing permission. Built a small Python library that
forces a human action before any billable call.

Implementation notes that might interest this sub:

- Touch ID comes from LocalAuthentication via PyObjC, not from `osascript ...
  with administrator privileges`. That path goes through Authorization
  Services and only offers a password box — the pam_tid recipes floating
  around do not apply to it.

- Ledger is a hash chain, with its head anchored in the login Keychain
  whenever a human approves something. The chain alone can't see a
  truncation: rewrite the tail and you get a shorter self-consistent chain.
  Anchoring the row number and hash makes rollback visible.

- Concurrent appends needed a file lock across read-compute-write. Without
  it two workers take the same sequence number and `verify` reports tampering
  during normal use — worse than not checking at all, because it teaches
  people to ignore the warning.

- Budget envelopes do reserve / settle, so costs discovered after the call
  still get accounted. An exception charges the held amount rather than
  silently freeing it.

Honest limits: this stops an agent that spends on its own, not one that edits
the library or sets SPEND_GATE_BYPASS=1. A call site nobody wrapped is
unprotected and says nothing.

https://github.com/yuyauchuncn-dot/agent-spend-gate
```

---

## r/ClaudeAI（场景向）

**Title**

```
My agent spent my money twice before I put a fingerprint check in front of it
```

**Body**

```
Not a horror story, just a gap nobody had closed.

I asked for ten illustrations. Got ten. The agent looked at them, decided the
composition was off, and made ten more. Cost was small; the pattern is the
problem. "Yes, go ahead" had become "yes, keep going" without anyone deciding
that.

What I wanted wasn't a stricter instruction in the prompt. Prompts get
compacted, reinterpreted, or just ignored. I wanted the call to be physically
unable to proceed without me.

So there's now a library that sits in front of the paid call: a dialog states
who gets paid and how much, then macOS asks for Touch ID. Cancel either one
and the API call never happens. Every attempt is logged either way.

Two things I learned building it:

- One prompt per call doesn't survive contact with real work. Synthesising a
  fifty-sentence episode meant fifty fingerprints. The fix was approving a cap
  once and letting charges run inside it.

- Writing the gate is the easy half. Finding every place that spends money is
  the hard half, and missing one is silent.

It's macOS-only and opt-in per call site. If your agent never spends anything,
this is irrelevant to you.

https://github.com/yuyauchuncn-dot/agent-spend-gate
```

---

## r/AI_Agents（产品向）

**Title**

```
A spending gate for agents: approve a cap once, not every call
```

**Body**

```
Sharing a pattern that turned out to be more useful than I expected.

Problem: agents that touch paid APIs spend without a human in the loop. The
usual answer is a prompt instruction, which is not a control — it's a
suggestion that survives until the next compaction.

What I built: a Python library where each billable call goes through
require_approval(). A dialog shows vendor / amount / purpose, then macOS asks
for Touch ID. Fail either gate and the call doesn't happen.

Three modes, because the right one depends on what you know:

- Fixed price: one approval per call.
- Unknown total: open_envelope(max_amount=...), one approval for a cap, charges
  inside it. Costs discovered afterwards use reserve/settle.
- Many small charges: an auto-approve threshold with a daily ceiling behind
  it, off by default.

There are also daily/weekly/monthly ceilings across everything, and per-vendor
limits with a whitelist that skips the prompt while staying inside the limits.

The part I'd suggest copying even if you don't use the library: the setup
skill. It scans a repo for paid call sites and asks which vendors should stay
behind a prompt. On a 40-file repo it found 3 real call sites after the first
pass reported 215 — the difference between a number someone acts on and one
they scroll past.

macOS only for now. Apache-2.0.

https://github.com/yuyauchuncn-dot/agent-spend-gate
```

---

## 发布顺序

1. Show HN，工作日上午（美西 6–9 点，北京时间 21–24 点）
2. 隔一天再发 Reddit，别同日多投
3. 每个 Reddit 版之间至少隔几天
4. 评论要真回，尤其是「为什么不直接用 X」这类

## 不要做的

- 不要在标题里用「revolutionary」「game-changer」
- 不要跨版复制正文
- 不要在发布当天反复顶帖
- 不要承诺 roadmap 里没写的东西
