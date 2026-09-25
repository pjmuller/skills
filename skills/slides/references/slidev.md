# Slidev authoring

Adapted from the bundled [upstream sources](sources.md), with lessons from existing decks.
Use the project's installed version and scripts; newer upstream features may be unavailable.

## Local toolchain

Find the deck's package directory and read `package.json`, lockfile, existing deck and style
entrypoint. Use its local CLI (`pnpm exec slidev`), not `pnpm dlx @slidev/cli`, which bypasses
the lockfile and local exporter dependencies. Use `mise exec --` where the project requires it.
For a new workspace, keep Slidev dependencies separate from unrelated application packages.

```sh
pnpm install
pnpm exec slidev talk.md --open
pnpm exec slidev export talk.md --format png --output /tmp/talk-review
pnpm exec slidev export talk.md --output /tmp/talk.pdf
```

Author against the hot-reloading dev server. Use a free port when another deck owns 3030;
stop only servers you started. Export requires local `playwright-chromium` and its Chromium
binary. pnpm 10+ may block dependency install scripts: inspect `onlyBuiltDependencies` or
`pnpm approve-builds` before diagnosing a missing browser. Allow the required packages
(commonly `playwright-chromium`, `esbuild`, and on older stacks `vue-demi`) rather than all
dependency scripts. Follow the actual missing-dependency/browser error for recovery.
Use `pnpm exec slidev export --help` to check flags supported by the installed version.

## Headmatter and notes

The first YAML block configures the deck **and slide 1**. Put the opening slide's layout
there and its content immediately below. An extra separator before that content creates an
empty first slide; fix the source instead of silently skipping the exported page.

```md
---
theme: default
title: A shorter path to an answer
layout: center
---

# A shorter path to an answer

<!--
- Open with the familiar handoff
- Ask who has seen the same delay
-->

---
layout: two-cols-header
---

# The handoff loses context

::left::

Before: three people reconstruct the same question.

::right::

After: one shared context travels with the question.

<!--
- Illustrative comparison, not measured results
- Transition: what context must travel?
-->
```

HTML comments at the end of a slide become speaker notes. Check them in `/presenter/`.
`defaults:` supplies common per-slide frontmatter; an explicit slide `class` replaces the
default class, so repeat the brand root class when adding a variant.
Use `hide: true` to park slides without deleting their source/notes when cutting a talk;
hidden slides are excluded from the presented deck and expected export count.

## Layout and visuals

- `center`/`statement` suit a single claim; `two-cols` with `::right::` suits comparisons;
  `two-cols-header` offers a shared heading with `::left::` and `::right::` slots.
  Theme support varies. Choose layout for the message, not to fill a template.
- `public/diagram.svg` is addressed as `/diagram.svg`. Prefer local assets for reliable
  offline delivery. Use `image-left`/`image-right` or ordinary HTML for intentional cropping.
- Markdown, HTML and Vue work together; reusable components in `components/` auto-import.
  Keep blank lines around Markdown/code fences nested inside HTML blocks.
- Mermaid uses a fenced `mermaid` block; `{scale: 0.8}` is a starting point, not a size law.
  Render, inspect labels, then adjust scale or simplify. For paired diagrams, a two-column
  layout with top-to-bottom flow often fits better than stacking. Keep the same visual scale
  when size carries meaning. Do not compensate for an overloaded diagram with tiny text.
- Pin `colorSchema: light` or `dark` in headmatter and design the palette for it. Unset, Slidev
  follows the viewer's OS preference while the exporter renders light, so hardcoded colours can
  pass PNG review and still be invisible in the browser.
- `aspectRatio` and `canvasWidth` belong in headmatter. Design for the delivery surface:
  a square social carousel and a widescreen talk need different compositions.

## CSS that does not damage other decks

A slide's `<style>` is scoped to that slide. Shared styles belong in the project's global
entrypoint (`style.css` or `styles/index.css`). Namespace shared classes under a deck/brand
root; generic selectors such as `.node` can collide with Mermaid's generated SVG.

Reuse brand tokens and CSS custom properties for variants instead of duplicating rules.
Keep CSS `@import` statements before ordinary rules. Check that export loads the intended
fonts; bundle suitable licensed fonts or use an available fallback for offline delivery.
Inspect computed theme styles before fighting them: a theme can dim `h1 + p`, for example.

## Reveals and technical explanations

Use `<v-clicks>` around a list or `v-click` on one element to pace an explanation;
`v-after` follows the previous reveal. Keep meaningful content in the final static state.
Notes can use `[click]` to track reveal cues. Test forward/back navigation and the export.
Simple transitions usually suffice; differing forward/back transitions are supported but
rarely improve the argument.

For code, show the smallest relevant excerpt. Fences support line highlighting (`{2-3}`)
and click stages (`{1|2-3|all}`). More advanced code animation, imports and interactive demos:
[advanced Slidev](slidev-advanced.md).

## Export and delivery

- PNG review output should match the intended slide count. Count rendered slides, not raw
  `---` lines (frontmatter and imported files make that misleading).
- PDF normally captures final states. `--with-clicks` adds pages per reveal: use it when those
  stages are part of the handout, and adjust the expected count accordingly.
- Slide PDF exports do not include speaker notes. Keep the notes in the source/presenter
  view; for a separate notes deliverable, use `pnpm exec slidev export-notes talk.md` when
  available (verified in 52.x), checking that command's help for output options.
- If a PDF loses images or global-layer state, try `--per-slide --wait-until networkidle
  --wait 1000` when supported. This fixed real deck exports where waiting alone did not.
  Inspect the resulting pages; extra waits are not proof of correctness.
- Check PDF page count and render pages back to images, using available PDF tools. For PNG,
  open the actual images. Leave review output in a temporary or ignored directory; preserve
  requested final deliverables at the agreed location.
- `pptx` export commonly produces slide images. Do not promise editable PowerPoint objects;
  newer versions offer `pptx-editable` with limits and fallbacks. Verify actual editability
  in the target tool, or use native PowerPoint authoring when that is the requirement.
- To deliver a web deck: `pnpm exec slidev build talk.md --base /talk/`. Match base path and
  routing to the host, and verify assets after deployment. Presenter notes can ship in a
  static build; use `--without-notes` when supported if they are not intended for viewers.
  Publish only within the user's requested scope.
