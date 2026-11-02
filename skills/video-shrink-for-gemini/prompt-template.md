# Recording brief

{{COUNT}} recording(s), {{DURATIONS}}: {{SITUATION}}
Who reads this: {{PURPOSE}} They will not watch the video, so record exactly what is said and visible: no causes,
diagnoses, suggestions or quality judgments.
Mode: {{MODE}}. Language: {{LANGUAGE}}; do not translate. Speakers: {{SPEAKERS}}; unsure → Unknown.

## Screen (visual-first and mixed)

Numbered steps, one per visible action, `[hh:mm:ss]`: page (URL/title as visible), what was clicked or typed, the
resulting state, before → after. At 00:00:00 and whenever a new screen appears, list once what a reader needs from it:
headings, labels, tags, buttons, rows, values and banners, quoted exactly. Look closely at: {{LOOK_FOR}}
- Quote screen text from the pixels, never from the word list or context; unsure → UNREADABLE. Copy URLs and IDs
  character for character, any uncertain character → UNREADABLE; never construct one.
- Frames are sampled about once per second: a state missing from them is "not seen", never "blank". Write an action
  only when you saw it happen; never invent clicks, typing, links or tabs to explain a change: content that changes
  or vanishes with no visible action gets `(action not visible)`, e.g. `[00:04:12] the list is empty again (action not
  visible)`. A page or content that appears at once, with no visible action or loading, is a likely cut: `[cut?
  hh:mm:ss] home page → privacy page; how it got there not seen`. Speech about a state is not a visual event.
- Count chips, rows, list items and removals one by one and name each: `removed 2 chips: "a", "b"`. Every tick,
  untick, toggle and removal is its own step, also right after a screen appears. Timestamps only go forward.
- When someone says something vanished, was not saved, is strange, wrong or a bug, write the on-screen state second
  by second from 3 s before the remark's subject to 3 s after (`[00:04:11] …`, `[00:04:12] …`), including the
  browser's reload/stop button and the cursor.
- Never copy tokens, meeting codes or personal fields (national number, birth date, address, phone, patient name):
  write `[redacted: kind]`.

## Speech (transcript-first and mixed)

`[hh:mm:ss] Speaker: …` close to verbatim: keep hesitations, tangents, numbers and names; no grammar fixes or
summaries. `[inaudible]`; `(?)` after an uncertain name. Transcript-first adds `[screen: …]` only where it clarifies
speech. Mixed: both sections, aligned by timestamps.

## Feedback items (only when someone narrates feedback on a product)

Recording started {{WALLCLOCK}}. End with `## Feedback items`: one entry per complaint, bug, wish, praise or "leave
it like this" (`leave alone`): timestamp + absolute time, screen/URL, element, the speaker's words, and the raw
on-screen values, including the element's own explanation or subline (a claim stays in the speech, never becomes
something you saw; name what the speaker reacts to, not your reading of it). Then `unnarrated`: visible defects
nobody mentioned (wrapped or truncated text, contradicting counts, error banners), described literally.

## Key frames ({{KEYFRAMES}})

When requested, the last section is `## Key frames` (after any feedback items): 1–4 lines `- [hh:mm:ss] what the still shows (item N)`, for
moments a reader must see rather than read (small icons, layout anomalies, error or loading states, dense tables), at
a second when that state is fully rendered.

## Words to listen for (spell them like this when heard)

{{VOCABULARY}}

## Skips

Condense to `[skipped hh:mm:ss–hh:mm:ss: reason]`: {{SKIPS}}

## Context (reference for recognition and spelling, never evidence of what happened)
{{CONTEXT_INTRO}}
