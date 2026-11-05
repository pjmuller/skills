---
name: settle-8020
description: "Only when the user explicitly invokes /settle-8020 or $settle-8020 (alone, or after answering pending decisions, e.g. \"D1A /settle-8020\"), ends a decision reply with a separate S (\"D1A S\", \"D1A D2B S\"), or asks to settle this thread at 80/20; never from an agent's own suggestion or a quote. Audits the current T3 thread's goal, finishes the small remaining work that still moves the needle, verifies it, then settles this thread. Never on your own initiative, never for another thread."
argument-hint: "[goal; default = this thread's goal]"
---

# Settle at 80/20

The user invoked this to close the loop on **this** thread: finish what still matters, then settle it so it
never needs them again. It covers this invocation only: no standing permission to settle later turns or
other threads, and no authorization beyond what the user or the brief already gave.

**Goal** = the text accompanying the invocation if it names one; else the thread's goal as the user
stated it, plus their later corrections. Other text in the same message (decision answers such as `D1A`,
extra instructions) is part of the request: carry it out first, then audit.

**`S` shorthand**: a decision reply ending in a separate `S` invokes this for the whole reply, however many
decisions it answers: `D1A S`, `D1A D2B S`, `d1: a, d2: b s.` (case, colons, commas, final punctuation don't
matter). Apply every answer, then audit. Not an invocation: a bare `S`, `D1AS`, `S` quoted or inside other
text. Decisions the reply left unanswered keep the thread open (ask them again).

1. **Audit against the goal, not the work log.** Delivered and verified where it lives (pushed, deployed,
   published, filed)? Anything half-done, unverified, unpushed, or still running (background shells,
   monitors, sub-agents, delegated workers whose result you still need)?
2. **Remaining 80/20**: at most 3 things that still clearly move the needle.
   - Authorized, reversible, small → do it now, verify, re-run step 1.
   - Needs the user (decision, approval, money, irreversible or outward action, login, their hands) →
     ask it and keep the thread open.
   - Needs time to pass (a reply, a deploy, live traffic) → arm a one-shot follow-up that posts back into
     this thread (T3 `schedule_task` with `{"schedule":{"type":"once","runAt":…}}`). An armed follow-up
     never keeps the thread open, nor does it stand in for undone delivery.
3. **Bigger options** you deliberately didn't build: one line each, what it would add. Don't build them.
4. **Settle** only when nothing from step 2 is pending, no background work runs, no explicit keep-open
   instruction stands, and your last message isn't itself the deliverable (an answer or value the user
   still has to read: settling hides the thread, so put it somewhere durable or stay open). Then a terse
   wrap-up (done + where, follow-ups with date, step-3 options), `t3_thread_organize {"action":"settle"}`
   with no threadId as the **last** tool call, then a one-line final answer.
   - Not settling → one line why, plus what the user must do.
   - No T3 tools (not running in T3 Code) → do steps 1–3, say settling isn't available; never claim it settled.

A personal settlement policy in the user's global prompt refines this; the user's explicit words win.
Settle mechanics (it stops the session and in-session sub-agents, not `delegate_task` children):
[t3-manage-thread settle](../t3-manage-thread/settle-thread.md).

Model invocation stays enabled on purpose: a plain-text or dictated `D1A /settle-8020` mid-message reaches
the skill only through the model; the description limits it to explicit requests.
