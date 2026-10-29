# Dispatching worker threads (project-agnostic)

A ticket, finding or meeting item normally gets its own 📤 standalone thread
([launch](workers.md#-t3_thread_launch), [title and brief file](workers.md#briefs-and-titles)).
Project wrappers (a standup or transcript dispatcher) add their sources and policies on top.

## Who runs the thread

An orchestrating **lead**, not an implementer: the operator's default lead model ([routing](routing.md)).
It reads, plans, decides, delegates coding per the operator's global rules, and verifies. Size (S/M/L)
is brief context, never picks the model. Security work routes per the project's own rules.

## Brief

Shape it to how settled the topic is:

- **brainstorm-only**: the question, options seen so far, a word cap, "no code, stop and wait";
- **investigate-first, then build**: phase A measures and names causes, phase B holds the intended
  design as a hypothesis the code may overturn;
- **build-ready**: numbered decisions as the spec.

Always: the ticket/URL and "fetch its comments first"; project skill files to read; what the source
(meeting, review, scan) adds beyond the ticket, as 5–15 concrete bullets with timestamps or quotes where
wording carries intent; primary repo and why, other repos touched; explicit out of scope; what "done"
and verification mean (tests, live check, handoff); autonomy ("ping only when it moves the needle").
Attach raw evidence as an appendix rather than summarising it away: a 10–30 KB brief is fine, a
one-line "meeting adds" is not.

## Bookkeeping

`projectId` = the primary repo; one worker per ticket. Record `item | thread-id | route | launched-at`
in a git-ignored run file so a rerun skips dispatched items; also pass `clientRequestId` = `<run>-<item>` so a retried launch
returns the same thread (T3 ≥ 0.1.4).
Threads finish under the project's own auto-settle rule if it has one.
