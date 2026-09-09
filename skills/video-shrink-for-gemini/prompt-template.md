# Recording brief

You get {{COUNT}} recording(s), {{DURATIONS}}, showing {{SITUATION}}.
Mode: {{MODE}}. Spoken language: {{LANGUAGE}}; do not translate.
Speakers: {{SPEAKERS}}; uncertain identity → Unknown.
Deliver one markdown document per recording, following the applicable blocks below.
Mixed mode requires both sections, aligned by timestamps.

## Visual-first rules (visual-first and mixed)

Write sequential visual narration a text-only coding agent can act on.
One numbered step per visible action, with `[hh:mm:ss]`: “User opened page X
(URL/title visible), saw Y, clicked Z, then …”. Quote exact on-screen text.
List the visible state: headings, table rows, error banners and values relevant
to that action; distinguish before/after states. Note anything that looks like a
bug or unexpected state using the visible evidence, without diagnosing causes.
No interpretation beyond what is visible. Mark unreadable text and gaps in sampled
frames; never invent clicks, hidden state or URLs. Include meaningful unchanged
states once rather than repeating them. Preserve action order.

## Transcript-first rules (transcript-first and mixed)

Use `[hh:mm:ss] Speaker: …` blocks, close to the spoken words: no summaries,
interpretation or conclusions. Keep tangents, numbers, names and hesitations;
do not fix grammar. Use `[inaudible]` and `(?)` after uncertain names.
In transcript-first mode, add brief `[screen: app / page / record]` context only
when it clarifies speech. Mixed mode also gets the full visual section above.
Spell names/product terms as in the context; do not replace visible wording.

## Skips

Condense these to `[skipped hh:mm:ss–hh:mm:ss: reason]`:
{{SKIPS}}

## Context
{{CONTEXT_INTRO}}
