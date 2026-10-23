# Spoken cues: "James, …"

One shared agent name for the whole team: **James** (Dutch and English calls). No per-person names:
who asked comes from speaker identity, not from the name. Active for calls recorded from
2026-10-15 14:00 Europe/Brussels; older recordings are never commands.

| Said in the call | Means |
| --- | --- |
| "James, please spawn/do/fix/research TASK" · "James, voer TASK uit / zoek TASK uit" · "James, can you look into TASK?" | Green light: start the thread for that bounded task now, no second approval round. |
| "James, please create a ClickUp ticket [for OWNER]: TASK" · "James, maak een ClickUp-ticket [voor OWNER]: TASK" | Create that ticket in OWNER's queue. Not execution of its content. |
| "James, prepare a prompt only" · "werk alleen een prompt uit" · "don’t execute yet" · "wacht op mijn akkoord" | Prepare the brief; do not launch or execute that action until selected. |
| No explicit mode | Follow the operator’s wrapper policy. Without one, deliver proposals. An auto-launch policy may launch clear, grounded operator-owned actions; tentative ideas stay proposals. |

A command needs direct address, a clear request to act (including polite “can you…” phrasing),
a concrete task, and an attributable speaker (verified transcript label, or unambiguous context such
as a two-person call). ASR may write the name as "Jaymes", "Jems" or "Djems" (unverified); accept those
only in the same direct-address shape.

Never a command: the name alone, speculation ("should James…?", "maybe we could…"), quoted or demo examples,
talk about this cue system, negation, or a request withdrawn later in the call. Corrected → use the last version.

Explicit hold/prepare-only wording wins over an auto-launch default and applies to the scoped action,
not unrelated actions. A later direct user instruction may release the hold. Execution means the
requested outcome: “research” authorizes research, not its recommended build; “draft” never means send.

## How the thread processing the call reacts

- OWNER = the speaker unless "for/voor X". Same person as this machine's operator → spawn here
  (a standalone thread in the owning repo, per current t3-manage-thread guidance) or create the ticket. Another teammate → always
  a ClickUp handoff in their queue, even for "spawn": their agent runs it on their machine.
- The brief/ticket carries the exact quote, speaker, call link and mm:ss, plus the scope as said;
  normal permission limits still apply (no deploys, external messages or spending beyond repo rules).
- One action per command per call; check the queue for an existing ticket first.
- Debrief lists "Spoken commands executed" (quote, mm:ss, thread/ticket link) and any rejected ones with
  the reason; those stay proposals.
