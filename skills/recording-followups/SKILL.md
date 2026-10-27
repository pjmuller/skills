---
name: recording-followups
description: "Use when a transcribed call or meeting (Fathom, Loom, Leexi, ClickUp SyncUp, local recording) should become a debrief plus spawnable T3 thread prompts (\"follow-up prompts\", \"spawn threads for what we agreed\"), a narrated product-feedback walkthrough should be implemented, or a recording-watcher thread starts. Owns the spoken cue (\"James, please spawn…\")."
---

# Recording → follow-up prompts

Speech layer comes from [video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md) or
[leexi](../leexi/SKILL.md); this skill owns what happens after the transcript is on disk. Project
skills (e.g. a team's Fathom wrapper) own where the note lives and its frontmatter, and link here
for the prompt step. Automatic per-call entry: [recording-watcher](../recording-watcher/SKILL.md).

- Product feedback walkthrough to **implement here** (not prompts) → [feedback-round.md](feedback-round.md).
- **Spoken cues** ("James, …") are commands, not proposals → [spoken-cues.md](spoken-cues.md).

## Deliverables

1. **Debrief note** in the project's notes location (else `~/Downloads`). Per topic: said,
   decided, open, timestamps. Personal to-dos and items for a colleague in their own list, never
   mixed into the delegable prompts. Its status splits **decisions waiting on the user** from
   **follow-ups already running** (thread/ticket link, what each waits on). A decision another
   thread owns is linked there, never requeued.
2. **`~/Downloads/<date>-<who>-followup-prompts.md`**: what the user **still has to trigger**,
   nothing else: prompts held for manual launch or explicit approval. Top: the spawn recipe and
   one status line. Then one `## N. <title>` per pending item, identical to its prompt file. An
   item leaves once its launch, handoff (ticket, other thread) or completion is verified, even
   while the worker runs; a worker's awaited output is not a new trigger. Nothing pending → no
   overview, or an existing one becomes the single line "No follow-ups left to trigger" (no
   catalogue of finished work).
3. **One file per prompt**: `~/Downloads/<date>-<who>-prompt-N.md` (title line + body). Launch by
   path so extra instructions are a quick edit, not a retype: `t3_thread_launch` with `message:
   "Read and execute <absolute path>"`. Files stay after launch (a worker may still read them);
   thread ids and links go in the debrief or a manifest so a retry cannot launch twice.

## Prompt shape (each one stands alone)

Two readers: first the user, who was in the call and reads this an hour later, then the worker.
Order ([examples](prompt-shape.md)):

1. **Title** in the user's words: what is wrong or wanted.
2. **The moment in the call** (mm:ss), 1–3 sentences: who showed or asked what, and the concrete
   case. A bug: what came in → what we answered → why that is wrong, with one short verified
   quote. A request: who asked for what and why, which claim to test, or what was promised. Mark
   paraphrases. The user must recognise the item without opening a link.
3. **Broader**, 1–2 sentences: the general rule or question this case stands for; known facts.
4. **Next steps**, 2–4 terse bullets, including the limit that changes what happens (proposal
   only, nothing sent).
5. After a `---` line, **for the agent**:
   - repo path + the two or three skill files to read first;
   - **verified** identifiers only (run/ticket ids, URLs from the API or source frames: a Gemini
     pass invents small screen text);
   - the **verified transcript** (`*.transcript.md`, provenance header) when one exists, stating
     the worker works from it and never re-runs the video pass; raw ASR + media path only when none;
   - target behaviour only where next steps are not enough; how to verify (tests, live run, browser);
   - authorized implementation ships (commit, push, promote when the repo deploys); research
     delivers findings and open decisions, no implementation;
   - house rules the thread needs (opposite-model review over 100 loc, no per-project code paths);
   - source (call link, mm:ss, transcript path, ASR caveat) on one line.

## Colleague handoffs

A ticket in a colleague's queue is the delivery for their work, never execution on this machine.

- A topic is not a task: ticket only an explicit request or an unambiguous committed action.
- Separate speaker words from inference; uncertain names or negations never become requirements.
- Keep sequence and phase owner: "X prepares, Y fine-tunes" means X owns the prerequisite and Y
  reviews later.
- Check the queue first. A ticket the user deleted or rejected stays deleted; extend existing work
  only on a material change.

## Light research before proposing

A few minutes per candidate in the code: does it already exist, which package owns it, which
decision will the worker hit first. That kills a prompt ("buttons render, the note was trimmed") or
makes it decision-ready ("Intercom notes cannot hold buttons: link to the confirm page or inline
text"). Stay shallow; never let this cost more than the prompts. `delegate_task` children are fine
here ([which one](../t3-manage-thread/workers.md#which-one)).

## Launch

- **Model**: every follow-up thread (research, docs and review included) defaults to **Opus High**:
  `t3-pick-instance opus`, explicit `modelSelection` with `options.effort: high`, verify the returned
  selection. Only an explicit user choice for that follow-up overrides it; never inherit the intake
  thread's model or one chosen to interpret the recording. Scoped children inside a task are exempt.
- **Standalone** (`t3_thread_launch` in the owning repo), never a `delegate_task` child of this
  intake thread: each topic is followed on its own.
- **When**: prepare-only / do-not-execute wording holds that action. Else the operator's wrapper
  policy or [spoken cues](spoken-cues.md) may authorize immediate launch of clear, grounded actions.
  Without such a policy or a direct execution request, the files are the deliverable. Deduplicate
  existing work before launching.
- **Additions at spawn time**: verbatim → spawn the file; small additions → append an `Additions
  from <user>:` paragraph; changed intent → rewrite the file. A pending item's overview section
  stays identical to its file; on launch it leaves the overview (Deliverables 2).
