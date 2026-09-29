---
name: recording-followups
description: Turn a call or meeting transcript (Fathom, Leexi, ClickUp SyncUp, local recording) into a short debrief note plus standalone, self-contained T3 thread prompts, one temp file per prompt, spawnable by path. Use after any recording is transcribed and the user wants "follow-up prompts", "what should we do about this call", or threads to delegate the agreed work.
---

# Recording → follow-up prompts

Speech layer comes from [video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md)
(Fathom/SyncUp/local) or [leexi](../leexi/SKILL.md). This skill owns what happens after the
transcript is on disk. Project skills (rootcause `fathom-interviews`, redcell's Fathom wrapper) own
where the note lives and its frontmatter; they link here for the prompt step.

## Deliverables

1. **Debrief note** in the project's notes location (else `~/Downloads`). Per topic: what was said,
   what was decided, what stays open, timestamps. Personal to-dos and "for a colleague" items in
   their own list, never mixed into the delegable prompts.
2. **`~/Downloads/<date>-<who>-followup-prompts.md`**: the overview the user reads. Top: a spawn
   recipe (below). Then one `## N. <title>` section per delegable item.
3. **One temp file per prompt** beside it: `~/Downloads/<date>-<who>-prompt-N.md` (title line +
   body). Spawn by path so extra instructions are a quick edit, not a retype:
   `t3-spawn-thread --model fable --thinking medium --title "<title>" < ~/Downloads/<date>-<who>-prompt-N.md`
   (no brief argument = stdin). Keep the section in the overview identical to the file.

## Prompt shape (each one stands alone)

Repo path + the two or three skill files to read first. Context: the decision, the evidence with
**verified** identifiers only (run ids, ticket ids, URLs; a Gemini pass invents small on-screen
text, take them from source frames or the API). Target behaviour as a numbered list. Verify: which
tests, which live run or browser check. Ship: commit, push, promote when the repo deploys. Report
tersely. Add the house rules the thread needs (opposite-model review over 100 loc, no per-project
code paths) instead of assuming the worker knows them.

## Light research before proposing

Spend a few minutes per candidate in the code before writing it: does the feature already exist,
which package owns it, which decision the worker will hit first. That check kills a prompt ("buttons
render, the note was trimmed") or turns it into a decision-ready brief ("Intercom notes cannot hold
buttons: link to the confirm page or inline text"). Stay shallow; the deep dive belongs in the
thread. Never let this step cost more than the prompts themselves.

## Routing

Default a thread to the thinker model at medium effort. Plain execute tasks with a clear spec
(add a link, a page, a lookup) go to a coding model (Opus/Sol). Investigations stay on the
thinker. Spawn only when the user says so; until then the files are the deliverable.

## When the user adds instructions at spawn time

Verbatim: spawn the file. Small additions: append a `Additions from <user>:` paragraph to the temp
file, then spawn. A changed intent: rewrite the file, keep the overview in sync.
