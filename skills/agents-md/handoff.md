# Handoffs between people, agents and roles

A handoff moves work to someone who did not watch it happen. Write for the
receiver's job, not your own trail. Three shapes; pick by who receives.

## Agent → a colleague or another harness (a prompt to relay)
Return **one copy-pasteable ```md block**, nothing around it:
1. Goal, one sentence.
2. What to open first: exact file/skill path(s); knowledge lives there, the prompt only points.
3. Steps/commands, env values inline (the owner archives threads).
4. Expected outcome: what "works" looks like.
5. Verification handshake: the receiver runs the checks and pastes back one bullet
   summary, what worked / what failed, tangible (versions, URLs, counts).

Key insights and decisions already made go in (2)/(3) so nobody re-derives them.
Bullets, no filler. Name the receiver's harness/model when it was given.

## Technical → non-technical (product owner, support, customer)
They act on outcomes, not on code. Lead with what they must do or check, then
what changed *as they will see it* (screen, email, report, timing). ≤ 5 short
lines in their language and vocabulary. No file, function, column, commit or
component names. Shipped facts only: a pending decision or open question is
settled in the chat thread first, then written as one line. In limbo → write
nothing. One native mention of the one person who must act. (Same rule as a
ClickUp handoff comment: skill `clickup-core`, "Comment discipline".)

## Non-technical → technical (bug report, feature ask)
- **North star first.** What should be true when this is done, and for whom?
  A request without a clear intent is not ready: ask the one or two questions
  that pin it down *before* handing off, not after a build starts.
- **Symptoms over conclusions.** You saw the surface; the developer must
  reconstruct the cause. Report what happened, not what you think broke.
  A hunch is welcome, labelled as a hunch, at the end.
- **More data points beat prose.** Each one narrows the search:
  - exact URL / screen / record (ticket, order, customer, ID) and account used;
  - date + time (with timezone) of each occurrence; once or every time; since when;
  - steps taken, in order, and what you expected at each step;
  - the exact text of any error, verbatim; screenshots or a screen recording;
  - environment: browser/app + version, device, network (office, home, mobile);
  - app version / build / commit if visible (about page, footer, release note);
  - what you already tried (refresh, other browser, other account) and the result;
  - who else is affected, and whether it blocks work today.
- **Severity by impact, not by feeling.** Who cannot do what, since when.

## Any direction
Goal + key insights/decisions + current state + next steps. Nothing the receiver
cannot act on. Read it once as the receiver: can they start without asking?
