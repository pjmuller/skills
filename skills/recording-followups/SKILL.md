---
name: recording-followups
description: Turn a call or meeting transcript (Fathom, Loom, Leexi, ClickUp SyncUp, local recording) into a short debrief note plus standalone, self-contained T3 thread prompts, one temp file per prompt, spawnable by path. Also owns the shared spoken cue ("James, please spawn…", "James, create a ClickUp ticket…"). Use after any recording is transcribed and the user wants "follow-up prompts", "what should we do about this call", or threads to delegate the agreed work.
---

# Recording → follow-up prompts

Speech layer comes from [video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md)
(Fathom/Loom/SyncUp/local) or [leexi](../leexi/SKILL.md). This skill owns what happens after the
transcript is on disk. Project skills (ReplyPen `fathom-interviews`, redcell's Fathom wrapper) own
where the note lives and its frontmatter; they link here for the prompt step.

**Spoken cues** ("James, please spawn…" / "James, create a ClickUp ticket…") are commands, not
proposals: [spoken-cues.md](spoken-cues.md). Automatic per-call entry point (one teammate machine per
call): [recording-watcher](../recording-watcher/SKILL.md).

## Deliverables

1. **Debrief note** in the project's notes location (else `~/Downloads`). Per topic: what was said,
   what was decided, what stays open, timestamps. Personal to-dos and "for a colleague" items in
   their own list, never mixed into the delegable prompts.
2. **`~/Downloads/<date>-<who>-followup-prompts.md`**: the overview the user reads. Top: a spawn
   recipe (below) and one current status line, updated when items start. Then one `## N. <title>`
   section per delegable item.
3. **One temp file per prompt** beside it: `~/Downloads/<date>-<who>-prompt-N.md` (title line +
   body). Launch by path so extra instructions are a quick edit, not a retype: `t3_thread_launch`
   with `message: "Read and execute ~/Downloads/<date>-<who>-prompt-N.md"` (absolute path) and
   explicit `modelSelection` from `t3-pick-instance opus` with effort `high` (unless the user
   explicitly selects another model/effort). Keep the overview section identical to the file.

## Prompt shape (each one stands alone)

Two readers: first the user, who was in the call and reads this about an hour later, then the
worker. Write for the user first, in this order ([examples](prompt-shape.md)):

1. **Title** in the user's words: what is wrong or wanted.
2. **The moment in the call** (mm:ss), 1–3 sentences: who showed or asked what, and the concrete
   case behind it. A bug: what came in → what we answered → why that is wrong, with one short
   verified quote. A feature, research question or mail: who asked for what and why, or which
   claim to test, or what was promised. Mark paraphrases. The user must recognise the item without
   opening a link.
3. **Broader**, 1–2 sentences: the general rule or question this case stands for; already known facts.
4. **Next steps**, 2–4 terse bullets, including the limit that changes what happens (proposal only,
   nothing sent).
5. After a `---` line, **for the agent**: everything below.

Agent block: repo path + the two or three skill files to read first. Evidence with
**verified** identifiers only (run ids, ticket ids, URLs; a Gemini pass invents small on-screen
text, take them from source frames or the API). Point at the **verified transcript**
(`*.transcript.md`, provenance header) when one exists beside the raw vendor ASR, and say so: the
worker works from that text and never re-runs the video pass; only when no verified transcript
exists does the prompt name the raw file and the media path. Detailed target behaviour only where
the next steps are not enough. Verify: which tests, which live run or browser check. Authorized
implementation ships (commit, push, promote when the repo deploys); research delivers findings and
open decisions, no implementation. Report tersely. Add the house rules the thread needs
(opposite-model review over 100 loc, no per-project code paths) instead of assuming the worker
knows them. Source (call link, mm:ss, transcript path, ASR caveat) on one line, not a paragraph.

## Light research before proposing

Spend a few minutes per candidate in the code before writing it: does the feature already exist,
which package owns it, which decision the worker will hit first. That check kills a prompt ("buttons
render, the note was trimmed") or turns it into a decision-ready brief ("Intercom notes cannot hold
buttons: link to the confirm page or inline text"). Stay shallow; the deep dive belongs in the
thread. Never let this step cost more than the prompts themselves.

## Routing

Default every standalone follow-up thread to **Opus High**, including research, documentation
and guided review. An explicit user model/effort choice for that follow-up overrides the default;
a model chosen only to interpret or synthesize the recording does not. Never inherit the intake
thread's model as the launch default. Resolve the account with `t3-pick-instance opus`, pass its
provider/model explicitly and set `modelSelection.options.effort` to `high`; verify the returned
selection. This default does not constrain scoped research/review children inside a task.
Apply the operator’s wrapper launch policy and [spoken cues](spoken-cues.md).
An explicit prepare-only / do-not-execute instruction holds that action. Otherwise a wrapper may
authorize immediate standalone launch of clear, grounded actions; absent that policy or a direct
execution request, the files are the deliverable. Always deduplicate existing work before launch.
A selected prompt always becomes a **standalone** thread in the owning repo (`t3_thread_launch`), never a
`delegate_task` child of this intake thread: each call topic is followed on its own and runs its own
children. Research before proposing may use `delegate_task` children ([which one](../t3-manage-thread/workers.md#which-one)).

## When the user adds instructions at spawn time

Verbatim: spawn the file. Small additions: append a `Additions from <user>:` paragraph to the temp
file, then spawn. A changed intent: rewrite the file. Either way, keep the overview in sync.
