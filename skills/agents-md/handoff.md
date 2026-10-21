# Handoffs between people, agents and roles

The receiver didn't watch the work: write for their job, not your trail.

## Agent → a colleague or another harness (a prompt to relay)
Return **one copy-pasteable ```md block**, nothing around it:
1. Goal, one sentence.
2. What to open first: exact file/skill path(s); knowledge lives there, the prompt only points.
3. Steps/commands, env values inline.
4. Expected outcome: what "works" looks like.
5. Verification handshake: receiver runs the checks, pastes back one bullet summary, worked/failed, tangible (versions, URLs, counts).

Decisions and key insights in (2)/(3), so nobody re-derives them. Bullets, no filler. Name the receiver's harness/model if given.

## Technical → non-technical (product owner, support, customer)
Lead with what they must do or check, then what changed *as they see it* (screen, email, report, timing). ≤ 5 short lines in their language and vocabulary; no file, function, column, commit or component names. Shipped facts only: settle open decisions in the chat thread first, then one line; in limbo → write nothing. One native mention of the one person who must act. (= ClickUp handoff comments: skill `clickup-core`, "Comment discipline".)

## Technical → a non-technical reader who works through a coding agent
Their agent runs the steps: **one copy-pasteable ```md block for their agent**, English: goal, what to open/install, exact commands/paths, what "done" looks like. Above it at most one line in the reader's language ("Plak dit in Codex."). Machine facts (OS, WSL, repo location) from the workspace's notes on that person, never assumed. Secrets via another channel.

## Non-technical → technical (bug report, feature ask)
First apply skill `clickup-core` → `triage.md` when available.
- **North star first:** what should be true when done, for whom? Unclear → ask one or two pinning questions *before* handing off.
- **Symptoms over conclusions:** what happened, not what you think broke; hunches last, labelled.
- **Data points beat prose:** exact URL / screen / record (ticket, order, customer ID) and account; date + time (timezone) per occurrence, once or always, since when; steps in order with the expected result; verbatim error, screenshots or a recording; browser/app + version, device, network; app version/build if visible; what you tried and its result; who else is affected, does it block work today.
- **Severity by impact:** who cannot do what, since when.

## Any direction
Goal + key decisions + current state + next steps, only actionable. Reread as the receiver: can they start without asking?
