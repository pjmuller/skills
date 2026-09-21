# Dispatching worker threads (project-agnostic)

Handing a ticket, finding or meeting item to its own T3 thread is the normal way to get
work done; project wrappers (DentAI `standup-dispatch`, Redcell `transcript-orchestrator`)
add their sources and policies on top of these rules, not instead of them.

## Title

`<emoji> <3–6 words the user recognises>`, in the user's language. The emoji is the only
routing signal: `🏓` round-trip (hidden, pings back, parent settles it) or `📤` standalone
(visible, never hidden/settled by helpers). No ticket IDs, repo names or phase words in the
title: they mean nothing at sidebar width; the ID belongs in the brief. Good:
`📤 Annulatiepolicy toepassen`. Bad: `🎫 869f4kx78 annulatiepolicy: numeric fields, conditional
profile, playbook, dashboard tile`. Invented emojis (🎫, 🔧…) are not routing and confuse the
fleet views; use the two above.

## Who runs the thread

Spawn a **thinker**, not an implementer: Fable (Claude) or Astra (Codex) at medium, chosen by
subscription capacity ([limits.md](limits.md)). The thread reads, plans, decides, delegates
coding to Opus sub-agents / Sol High workers per the operator's global rules, and verifies.
Size (S/M/L) goes in the brief as context and never picks the model. Exception: security
work is routed per the project's own rules (Redcell: never Fable).

## Brief

A file on disk, path in the spawn argument (`"Read and execute /abs/path/brief.md"`), never a long
inline string. Shape it to how settled the topic is:

- **brainstorm-only**: the question, the options seen so far, a word cap, "no code, stop and wait";
- **investigate-first, then build**: phase A measures and names causes, phase B holds the intended
  design as a hypothesis the code may overturn;
- **build-ready**: numbered decisions as the spec.

Always: the ticket/URL and "fetch its comments first"; the project skill files to read; what the
source (meeting, review, scan) adds beyond the ticket, as 5–15 concrete bullets with timestamps or
quotes where wording carries intent; primary repo and why, other repos touched; explicit out of
scope; what "done" and verification mean (tests, live check, handoff); autonomy expectation
("ping only when it moves the needle"). Attach raw evidence as an appendix rather than summarising
it away: a 10–30 KB brief is fine, a one-line "meeting adds" is not.

## Bookkeeping

`--project` = the primary repo (add `--allow-cross-project-source` when spawning from another
project). One worker per ticket. Record `item | thread-id | route | spawned-at` in a git-ignored
run file so a rerun skips already-dispatched items. Standalone threads finish under the project's
own auto-settle rule if it has one; round-trip threads are verified and settled by the parent.
