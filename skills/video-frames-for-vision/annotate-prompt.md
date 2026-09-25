# Annotate a meeting recording from selected frames + transcript

Fill the `{{…}}` fields, paste into a vision-capable coding agent (Codex, Claude Code) started
in the run directory. The agent must be able to open image files itself (Codex: `view_image`
tool; Claude Code: Read). Keep every rule block.

---

Run directory: `{{RUN_DIR}}` (absolute). Meeting: {{TITLE}} · {{DATE_TIME_LOCAL}} · {{DURATION}} · spoken language {{LANGUAGE}}.
Speakers: {{SPEAKERS}} (uncertain → Unknown). Context: {{SITUATION_ONE_LINE}}.
Write the result to `{{RUN_DIR}}/analysis.md`; write nothing else outside the run directory.

## Inputs (read in this order)

1. `transcript.md` — the speech layer: `MM:SS Speaker: text` paragraphs from the vendor's ASR.
   It is the reference for what was said; you cannot hear audio, so never "correct" spoken words
   from imagination. A word that contradicts something visible on screen may be flagged as
   `[transcript says X; screen shows Y]`.
2. `manifest.md` — one row per kept frame: id (page number + view letter), the second it shows,
   the view span, the page span, file path. Read the summary line: how much of the meeting was
   people-only (no screen share) and how many frames exist.
3. `sheets/sheet-NN.jpg` — contact sheets in time order, for orientation only (small text is
   not legible there).
4. `frames/*.jpg` — the evidence. Open them **in manifest order, in batches of 12–24**, together
   with the transcript paragraphs of each frame's span. After every batch append your
   observations to `{{RUN_DIR}}/screen-notes.md` (frame id, time, app/page, exact text/IDs you can
   read, what changed vs the previous frame) before opening the next batch, so nothing is lost
   when your context is compacted.
5. `sheets/audit-NN.jpg` — demoted frames, isolated transients and periodic sentinels of the
   people-only stretches. Scan them once: if a sentinel shows a screen that the selector
   classified as people-only, say so under Coverage and, if it matters, extract that second
   yourself (`ffmpeg -ss SECONDS -i source.webm -frames:v 1 crop.jpg`).

## Rules

- Frames are samples: they prove what was on screen at that second, not what happened between
  samples. Never invent clicks, typing, navigation or hidden state.
- Quote on-screen text exactly. IDs, URLs, ticket numbers, amounts: read character by character;
  one uncertain character → `UNREADABLE` for the whole ID, plus the frame id so a human can crop
  it. When a candidate list is supplied below, a match from it is `candidate-assisted`, never
  "read".
- Small text: crop and enlarge yourself only after the first full pass, and only for IDs that
  matter for an action item.
- Keep the original language in quotes; write the analysis in {{OUTPUT_LANGUAGE}}.
- Tentative ideas stay `idea`; do not turn them into action items.

## Output: `analysis.md`

1. **Coverage** — frames read (count), people-only spans, gaps and anything the audit sheets
   revealed; transcript passages you could not align with any frame.
2. **Screen events** — `[SCREEN @ h:mm:ss] app / page — what is shown` in time order, one per
   frame or page, with exact visible text that matters (titles, counts, names, IDs, URLs).
   Mark `(scrolled)` views of the same page as sub-bullets.
3. **Topics** in order: time range; what was discussed (2–5 lines, concrete); decisions and
   their conditions ("only if…", reversals); owner (per speaker / both / none); screen evidence
   (frame ids); **clarifications** — details spoken here that a reader of the resulting task
   would not know (priority, scope cuts, examples, acceptance wording), quoted with timestamps.
4. **Action items** — one line each: owner, verb-first summary, topic ref, evidence frame id.
   Separate lists: needs a new ticket · existing ticket (`candidate-assisted` id) · just do.
5. **Prompts to paste into a new session** — for every action item owned by the reader: a
   self-contained prompt block (goal, what was decided and why in the meeting, quotes with
   timestamps, on-screen facts with frame ids, out of scope, how to verify). Someone with no
   access to this run directory must be able to act on it.
6. **Meta** — remarks about how the participants work (process, tooling), separately.

{{OPTIONAL_CANDIDATE_LIST_OR_CONTEXT_FILES}}
