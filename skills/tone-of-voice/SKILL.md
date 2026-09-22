---
name: tone-of-voice
description: Build or refresh a person's tone-of-voice file in a short interview: gather writing they are proud of (pasted text, sent mail via google-workspace-core, Google Docs, LinkedIn posts), extract how they sound and what they never sound like, confirm in ping-pong, write `tone-of-voice.md` and point the global agent prompt at it. Use for "capture my tone of voice", "write like me", "my writing style file", or when an agent drafts messages in someone's name and no such file exists.
---

# Tone of voice

Outcome: one `tone-of-voice.md` the person owns, derived from **their real writing**, not
from taste, that any agent reads before drafting in their name. Starter shape and the
anti-AI-slop checklist: [template.md](template.md). The file is theirs: do not send it
anywhere, do not copy private mail into it beyond short verbatim samples they approved.

## 1. Collect samples (ask, don't assume)
Ask which of these they can give, and take every one offered. 10–30 pieces across at least
two channels is enough; more of the same channel adds little.
- **Pasted text**: messages, posts, emails they are proud of, and one or two they rewrote
  because the first draft "sounded wrong" (the edit is the strongest signal).
- **Sent mail** (repo with a `google-workspace-core` wrapper, their own account only):
  `gmail-search 'from:me -newsletter after:<1 year ago>' -n 200` to list, then
  `gmail-export '<query>' -o /tmp/tov/<name> -n 60`; prefer mail to people outside the
  company. Ask before exporting; delete the export folder when done (its skill's clean-up rule).
- **Google Docs / LinkedIn posts**: `gws.py … docs export <url>` per doc; posts pasted or
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
their global agent prompt (skill `agents-md`, section "Writing in my name") with the absolute
path. Refresh later from new samples, never from memory of a conversation.
