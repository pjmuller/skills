---
name: tone-of-voice
description: "Use for \"capture my tone of voice\", \"write like me\", \"my writing style file\", or when an agent must draft messages in someone's name and they have no tone-of-voice.md yet."
---

# Tone of voice

Outcome: one `tone-of-voice.md` the person owns, derived from **their real writing** (not taste),
read by any agent before drafting in their name. Starter shape and anti-AI-slop checklist:
[template.md](template.md). **Privacy (hard rule):** the file is theirs; never send it anywhere
or copy private mail into it beyond short verbatim samples they approved. It lives outside this
installation (skill updates replace it).

## 1. Collect samples (ask, don't assume)

Take every source they offer; 10–30 pieces across at least two channels is enough.
- **Pasted text**: messages, posts, emails they are proud of, plus one or two they rewrote
  because the first draft "sounded wrong" (the edit is the strongest signal).
- **Sent mail** (repo with a `google-workspace-core` wrapper, their own account only): ask
  first, then [search → export](../google-workspace-core/references/gmail-search.md)
  `from:me newer_than:1y -newsletter`, ~60 messages, preferring mail outside the company; clean
  up the export as that doc says.
- **Google Docs / LinkedIn / slides notes**: `doc-read <url>` (Markdown) per doc; posts pasted
  or via an installed LinkedIn skill.
- Mark each sample's audience (peer, customer, colleague, public post) and language: tone often
  differs per audience and the file must say so.

## 2. Extract, then confirm in ping-pong

Draft from the samples; never ask them to describe themselves (people misreport):
- sentence length and rhythm, openers and closers, typical asks;
- language mix, formality markers (tu/vous, je/u), dialect words, jargon they keep;
- humour (kind, placement, frequency), emoji and punctuation habits;
- what they lead with (problem, number, person, product);
- what is **absent** from every sample (no corporate warm-up, no signature, …);
- 3–6 verbatim samples, one per audience, they still like.

Show it in ≤ 40 lines and ask: what is wrong, what is missing, which sample would you never send
today. Iterate until "that's me" (two rounds is normal).

## 3. Write and wire in

Write `tone-of-voice.md` where they keep personal docs (setup repo, notes vault): short summary
header, "How I sound", "What I never sound like", the template's anti-slop checklist (trimmed to
what applies), approved samples. Add the absolute-path pointer to their global prompt ("Writing
in my name" in the [agents-md template](../agents-md/global-template.md)). Refresh later from new
samples, never from memory of a conversation.
