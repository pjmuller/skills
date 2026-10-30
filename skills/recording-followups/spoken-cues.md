# Spoken cues: "James, …"

One shared agent name for the whole team: **James** (Dutch and English calls). No per-person names:
who asked comes from speaker identity, not from the name. "James" addresses the assistant; it does
not pick the destination. Active for calls recorded from 2026-10-15 14:00 Europe/Brussels; older
recordings are never commands.

| Said in the call | Means |
| --- | --- |
| "James, please spawn/do/fix/research TASK" · "James, voer TASK uit / zoek TASK uit" · "James, can you look into TASK?" | Green light: start the thread for that bounded task now, no second approval round. |
| "James, please create a ClickUp ticket [for OWNER]: TASK" · "James, maak een ClickUp-ticket [voor OWNER]: TASK" | Create that ticket in OWNER's queue. Not execution of its content. |
| "James, remind me on DAY: TASK" · "James, put TASK on my list for DAY" · "James, herinner me DAG aan TASK" | Surface it to the speaker then: a reminder, not a ticket or a thread. |
| "James, prepare a prompt only" · "werk alleen een prompt uit" · "don’t execute yet" · "wacht op mijn akkoord" | Prepare the brief; do not launch or execute that action until selected. |
| No explicit mode | Follow the operator’s wrapper policy. Without one, deliver proposals. An auto-launch policy may launch clear, grounded operator-owned actions; tentative ideas stay proposals. |

A command needs direct address, a clear request to act (including polite “can you…” phrasing),
a concrete task, and a speaker you can [attribute](#who-said-it). ASR may write the name as
"Jaymes", "Jems" or "Djems" (unverified); accept those only in the same direct-address shape.
Read the intended outcome, not keywords: "my list" can also mean an existing list the speaker
keeps; the destination rules below pick the lightest home that fulfils it.

Never a command: the name alone, speculation ("should James…?", "maybe we could…"), quoted or demo examples,
talk about this cue system, negation, or a request withdrawn later in the call. Corrected → use the last version.

Explicit hold/prepare-only wording wins over an auto-launch default and applies to the scoped action,
not unrelated actions. A later direct user instruction may release the hold. Execution means the
requested outcome: “research” authorizes research, not its recommended build; “draft” never means send.

## Who said it

Vendor speaker labels (Fathom, Leexi, …) can be wrong: a voice credited to a colleague's tile, two
speakers inside one segment, a shared-device or company-named tile. A matched calendar email names
the account the vendor picked, not who spoke that sentence; a two-person call can still be swapped.

- **Check before acting** when the label decides an owner or an authorization (a command, a handoff,
  whose reminder): with a video, `speaker-frames` on that segment
  ([video-frames-for-vision](../video-frames-for-vision/SKILL.md#who-said-it-speaker-frames)) and
  look at the frames yourself. No screen share does not mean no useful video: the tiles show who spoke.
- Ordinary content whose speaker changes nothing needs no check. Never re-label the vendor
  transcript; record the verdict and its frames in the debrief.
- **Inconclusive or no video** → hold only that item, with one line on what would settle it; the
  rest of the call proceeds. Another model reading the same text is not a check.

## Destination: lightest that fulfils the intent

Decide scope, holds, speaker and authorization first, then the home:

| Intent | Home |
| --- | --- |
| Remember / surface later | A reminder for that person through their own reminder route (the wrapper names it). Resolve a weekday against the call date, keep the timezone; never schedule one in the past. |
| Bounded work an agent should run | A T3 thread, when authorized (command or wrapper policy). |
| Explicit ticket, or an authorized team deliverable that needs an owner and tracking | ClickUp, after checking for existing work. Needing tracking grants no permission to write a colleague's queue. |
| Already owned or acknowledged work, a tentative idea | Nothing beyond the debrief. |

A colleague's reminder never runs on this machine without an authorized route to theirs, and a
missing route is no reason to file a ticket instead: list it in the debrief.

## How the thread processing the call reacts

- OWNER = the [verified](#who-said-it) speaker unless "for/voor X". Same person as this machine's
  operator → spawn here (a standalone thread in the owning repo), schedule the reminder, or create the
  ticket. Another teammate's spawn or ticket command → a ClickUp handoff in their queue: their agent
  runs it on their machine. Ordinary conversation or an acknowledged commitment is not such a command.
- The brief/ticket carries the exact quote, speaker, call link and mm:ss, plus the scope as said;
  normal permission limits still apply (no deploys, external messages or spending beyond repo rules).
- One action per command per call; check the queue for an existing ticket first
  ([handoff rules](SKILL.md#colleague-handoffs)).
- Debrief lists "Spoken commands executed" (quote, mm:ss, thread/ticket/reminder link, speaker check
  if done) and any rejected or held ones with the reason; those stay proposals.
