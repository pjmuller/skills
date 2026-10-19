# Spoken cues: "James, …"

One shared agent name for the whole team: **James** (Dutch and English calls). No per-person names:
who asked comes from speaker identity, not from the name. Active for calls recorded from
2026-10-15 14:00 Europe/Brussels; older recordings are never commands.

| Said in the call | Means |
| --- | --- |
| "James, please spawn [for OWNER] TASK" · "James, start een agent [voor OWNER] om TASK" | Green light: start the thread for that bounded task now, no second approval round. |
| "James, please create a ClickUp ticket [for OWNER]: TASK" · "James, maak een ClickUp-ticket [voor OWNER]: TASK" | Create that ticket in OWNER's queue. Not execution of its content. |
| "James, …" anything else, or no cue | Default: a proposal in the follow-up thread. |

A command needs all of: direct address at the start of the request, an imperative spawn/ticket verb,
a concrete task, and an attributable speaker (verified transcript label, or unambiguous context such
as a two-person call). ASR may write the name as "Jaymes", "Jems" or "Djems" (unverified); accept those
only in the same direct-address shape.

Never a command: the name alone, questions ("should James…?"), maybe/could, quoted or demo examples,
talk about this cue system, negation, or a request withdrawn later in the call. Corrected → use the last version.

## How the thread processing the call reacts

- OWNER = the speaker unless "for/voor X". Same person as this machine's operator → spawn here
  (a standalone thread in the owning repo, per current t3-manage-thread guidance) or create the ticket. Another teammate → always
  a ClickUp handoff in their queue, even for "spawn": their agent runs it on their machine.
- The brief/ticket carries the exact quote, speaker, call link and mm:ss, plus the scope as said;
  normal permission limits still apply (no deploys, external messages or spending beyond repo rules).
- One action per command per call; check the queue for an existing ticket first.
- Debrief lists "Spoken commands executed" (quote, mm:ss, thread/ticket link) and any rejected ones with
  the reason; those stay proposals.
