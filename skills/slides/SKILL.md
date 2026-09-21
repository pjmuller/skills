---
name: slides
description: Create, edit, review and export presentations with a clear story, concise speaker notes and visual verification. Includes Slidev expertise. Read the project's project-slides skill first for paths and brand. Use for talks, pitch decks, teaching slides and redesigns; preserve a requested format such as PowerPoint.
---

# Slides

Make the audience understand, remember or decide something. A beautiful deck that leaves
them unsure of the point has failed. These are north stars, not a mandatory template.

Read the project's `project-slides` wrapper when present: it owns deck locations, brand, audience,
local commands and delivery conventions. This shared skill owns craft and Slidev mechanics.
For new wrappers or installation, see [integration](references/integration.md).

## Shape the story before styling

Infer the audience, occasion, time available and desired outcome from the brief and existing
material. Ask only when a missing answer would change the deck. Distinguish a live talk from
a document people must understand without a speaker; a handout may need more context.

- Write the takeaway in one sentence. Arrange slide headlines into a coherent argument:
  a recognizable situation, what changes our understanding, evidence, then a useful conclusion.
  Read the headlines alone: they should carry the argument. Choose the arc that fits;
  not every talk is a sales pitch or needs a company introduction.
- Give each slide one job. A comparison can be one idea; two unrelated takeaways deserve
  separate slides. Split, cut or move detail into notes/appendix before shrinking text.
- Prefer concrete examples and explanatory titles to topic labels. The audience should not
  have to reverse-engineer the scenario. Preserve qualifications that change the conclusion.
- Ground claims, numbers and quotations in sources. Keep source links with the relevant slide
  or notes. Label invented examples and illustrative data; never pass them off as evidence.

For a substantial new deck, sketch headlines and the intended visual before building. For a
small edit, preserve the working narrative. An outline is a working aid, not an approval gate.

## Make the point visible

Choose the simplest visual that explains the idea: a direct comparison, annotated screenshot,
chart, diagram, short code sample, or one strong image. HTML/SVG can make a precise visual;
Mermaid is useful for relationships, not a requirement for every slide.

Use consistent visual language, generous space, readable labels and deliberate emphasis.
Show the few dimensions that affect a decision, not every available field. Keep chart scales
honest, label units and uncertainty, and do not rely on colour alone for meaning.

Images earn their space by explaining, making something memorable, or setting an intentional
mood. If generated artwork would help, choose a coherent art direction and purposeful humour;
avoid generic decorative AI imagery. Respect requests to brainstorm without generating yet.
Use existing brand assets and avoid revealing private information in screenshots.

## Support the speaker

For live talks, put concise bullet cues in presenter notes: the example, essential nuance,
transition, or demo cue the speaker could forget. Do not duplicate the slide or write a script
unless requested. Keep editorial/review history outside presenter notes. Reveal content only
when the order helps understanding. Estimate speaking time from the notes, allowing for
demos, pauses and questions; flag and cut an overfull talk. Where possible, rehearse with
the speaker to replace the estimate with actual timing.

## Build and verify the actual deliverable

Keep the existing format and toolchain. For a new code-based deck, Slidev is a useful default:
read [Slidev authoring](references/slidev.md). For an explicitly requested PowerPoint or other
format, use the available format-specific skill/tool and apply the craft guidance here.

Inspect every new or changed slide as rendered, at its intended aspect ratio. An overview
catches pacing and inconsistent styling; full-size views catch unreadable labels, clipping,
missing assets and awkward spacing. Check first/final and meaningful intermediate reveal
states. After shared style changes, inspect affected existing decks too.

Verify the delivered format, not just the dev view: exports can differ. Confirm expected
slide/page count (accounting for intentional click pages), notes and asset rendering. A build
success is not visual QA. Fix problems and recheck; state any verification limitation plainly.
Deliver the requested artifact or preview with only the remaining decision/action for the user.

[Sources and upstream license](references/sources.md).
