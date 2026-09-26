---
name: tone-of-voice
description: "Build or refresh a person's tone-of-voice file in a short interview: gather writing they are proud of (pasted text, sent mail via google-workspace-core, Google Docs, LinkedIn posts), extract how they sound and what they never sound like, confirm in ping-pong, write `tone-of-voice.md` and point the global agent prompt at it. Use for 'capture my tone of voice', 'write like me', 'my writing style file', or when an agent drafts messages in someone's name and no such file exists."
---

# Tone of voice

Outcome: one `tone-of-voice.md` the person owns, derived from **their real writing**, not
from taste, that any agent reads before drafting in their name. Starter shape and the
anti-AI-slop checklist: [template.md](template.md). The file is theirs: do not send it
anywhere, do not copy private mail into it beyond short verbatim samples they approved.

The live `tone-of-voice.md` stays outside this installation (skill updates replace it).

## 1. Collect samples (ask, don't assume)
Ask which of these they can give, and take every one offered. 10–30 pieces across at least
two channels is enough; more of the same channel adds little.
- **Pasted text**: messages, posts, emails they are proud of, and one or two they rewrote
  because the first draft "sounded wrong" (the edit is the strongest signal).
- **Sent mail** (repo with a `google-workspace-core` wrapper, their own account only):
  [search → export](../google-workspace-core/references/gmail-search.md) with
  `from:me newer_than:1y -newsletter`, ~60 messages, preferring mail to people outside the
  company. Ask before exporting; clean up the export as that doc says.
- **Google Docs / LinkedIn posts**: `doc-read <url>` (Markdown) per doc; posts pasted or
  fetched with a LinkedIn skill if one is installed. Slides speaker notes count too.
- **Recipient split**: mark each sample by audience (peer, customer, colleague, public post)
  and language. Tone often differs per audience; the file must say so.

## 2. Extract, then confirm in ping-pong
From the samples, draft (do not ask them to describe themselves; people misreport):
- sentence length and rhythm, openers and closers, typical asks;
- language mix, formality markers (tu/vous, je/u), dialect words, jargon they keep;
- humour: kind, placement, frequency; emoji and punctuation habits;
- what they talk about first (problem, number, person, product);
- what is **absent** from every sample (no corporate warm-up, no signature, …);
- 3–6 verbatim samples, one per audience, that they still like.
Show the draft in ≤ 40 lines and ask three things: what is wrong, what is missing, which
sample they would never send today. Iterate until they say "that's me". Two rounds is normal.

## 3. Write and wire in
Write `tone-of-voice.md` where they keep personal docs (setup repo, notes vault), with a
short summary header, "How I sound", "What I never sound like", the anti-slop checklist from
the template (trimmed to what applies) and the approved samples. Then add the pointer line in
their global agent prompt ("Writing in my name" in the
[agents-md template](../agents-md/global-template.md)) with the absolute path. Refresh later from new samples, never from memory of a conversation.
