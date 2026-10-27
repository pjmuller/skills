---
name: slides
description: "Use to create, edit, review or export a presentation (\"make slides about…\", \"fix this deck\", talk, pitch, teaching slides, redesign), Slidev or a requested format such as PowerPoint. Read the project's project-slides wrapper first."
---

# Slides

Make the audience understand, remember or decide something; a beautiful deck that leaves them
unsure of the point has failed. North stars, not a mandatory template.

The project's `project-slides` wrapper, when present, owns deck locations, brand, audience, local
commands, delivery conventions and the house style guide: apply it before asking. New wrapper or
installation → [integration](references/integration.md).

## Craft checklist

Infer audience, occasion, time and outcome from the brief and existing material; ask only when the
answer would change the deck. A deck read without a speaker may need more context than a live talk.

- **Story first.** Takeaway in one sentence; headlines alone carry the argument (a recognizable
  situation, what changes our understanding, evidence, a useful conclusion). Pick the arc that fits;
  not every talk needs a pitch or company intro. New deck → sketch headlines and visuals first (a
  working aid, not an approval gate); small edit → keep the working narrative.
- **One job per slide** (a comparison can be one idea; two unrelated takeaways are two slides). Split, cut or move detail to
  notes/appendix before shrinking text.
- **Concrete over abstract:** examples and explanatory titles, not topic labels; keep qualifications
  that change the conclusion.
- **Grounded:** claims, numbers and quotes link a source on the slide or in notes; label invented
  examples and illustrative data.
- **Spoken quotes:** dictated words read poorly verbatim. On the slide, restate only the part that
  carries this slide's point, without quote marks or the speaker's habitual phrases; keep the
  verbatim source in notes or source files. Quote exactly only when the wording itself is the point.
- **Simplest visual that explains:** comparison, annotated screenshot, chart, diagram, short code or
  one strong image; HTML/SVG for precision, Mermaid for relationships (not every slide). Consistent
  visual language, generous space, readable labels; only the dimensions that affect a decision.
  Honest chart scales, units and uncertainty; never colour alone for meaning.
- **Images earn their space** (explain, make memorable, set an intended mood). Generated art:
  coherent direction, purposeful humour, no generic AI decoration; respect "brainstorm, don't
  generate yet". Use brand assets; no private information in screenshots.
- **Presenter notes** (live talks): short cues the speaker could forget (example, nuance,
  transition, demo); no copy of the slide or script unless asked, no review history. Reveal only
  when order helps. Estimate speaking time incl. demos, pauses and questions; cut an overfull talk;
  rehearse for real timing where possible.

## Build and verify the actual deliverable

Edit only what was requested; nothing else on the slide or in the deck changes. Keep the existing
format and toolchain. New code-based deck → Slidev
([authoring](references/slidev.md)); requested PowerPoint or other format → its own skill/tool,
with this craft.

Inspect every new or changed slide rendered at its aspect ratio: overview for pacing and
consistency, full size for unreadable labels, clipping, missing assets and spacing; first, final
and meaningful reveal states. Shared style change → recheck affected decks.

**Verify the delivered format, not the dev view** (exports differ): slide/page count (intentional
click pages included), notes, assets. A build success is not visual QA. Fix, recheck, state verification
limits plainly; deliver with only the remaining decision for the user. End the final reply with the absolute path of each delivered file, the PDF (or other
export) first.

## Learn from corrections

Edit-round feedback is micro; its value is the macro rule behind it. Track corrections. A pattern
is the same preference on independent slides or decks, or an explicit "always…"; two fixes on one
odd slide are not. Then (or at round end) propose the rule in one line, exact wording plus target
file; write it once the user agrees (or at once when they say act autonomously) and say what was
burned in.

- Universal craft → this file's checklist, proposed upstream in `pjmuller/skills`, not only locally.
- Brand, language, audience, naming, deck mechanics, verification quirks → the wrapper's
  `project-slides/style.md`.
- A rule states intent and test ("titles fit beside the logo: at most 40 characters"), never the
  triggering instance; no example lists or changelog. Fold into an existing rule; an exception
  narrows scope; delete a rule only when the user states a superseding one.

[Sources and upstream license](references/sources.md).
