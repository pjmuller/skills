# Slidev authoring

Adapted from the bundled [upstream sources](sources.md), with lessons from existing decks.
Use the project's installed version and scripts; newer upstream features may be unavailable.

## Local toolchain

Read the deck package's `package.json`, lockfile, existing deck and style entrypoint. Use its
local CLI (`pnpm exec slidev`), not `pnpm dlx @slidev/cli` (bypasses the lockfile and local
exporter dependencies); `mise exec --` where the project requires it. New workspace → keep Slidev
dependencies apart from unrelated application packages.

```sh
pnpm install
pnpm exec slidev talk.md --open
pnpm exec slidev export talk.md --format png --output /tmp/talk-review
pnpm exec slidev export talk.md --output /tmp/talk.pdf
```

Author against the hot-reloading dev server; free port when another deck owns 3030; stop only
servers you started. Export needs local `playwright-chromium` and its Chromium binary. pnpm 10+
may block install scripts: check `onlyBuiltDependencies` / `pnpm approve-builds` before
diagnosing a missing browser, and allow only the required packages (commonly
`playwright-chromium`, `esbuild`, on older stacks `vue-demi`). Follow the actual error for
recovery; `pnpm exec slidev export --help` lists the installed version's flags.

## Headmatter and notes

The first YAML block configures the deck **and slide 1**: put the opening slide's layout there
and its content directly below. An extra separator creates an empty first slide; fix the source,
never silently skip the exported page.

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

A slide's trailing HTML comments become speaker notes (check `/presenter/`). `defaults:`
supplies common frontmatter; an explicit slide `class` replaces the default, so repeat the
brand root class in variants. `hide: true` parks slides (source/notes kept) out of the
presented deck and expected export count.

## Layout and visuals

- `center`/`statement` suit a single claim; `two-cols` with `::right::` suits comparisons;
  `two-cols-header` offers a shared heading with `::left::` and `::right::` slots.
  Theme support varies; choose layout for the message.
- `public/diagram.svg` is `/diagram.svg`. Local assets for offline delivery;
  `image-left`/`image-right` or plain HTML for intentional cropping.
- Markdown, HTML and Vue work together; reusable components in `components/` auto-import.
  Keep blank lines around Markdown/code fences nested inside HTML blocks.
- Mermaid: fenced `mermaid` block; `{scale: 0.8}` is a starting point. Render, inspect labels,
  then adjust scale or simplify. Paired diagrams often fit better as two columns flowing
  top-to-bottom than stacked. Same visual scale when size carries meaning; never fix an
  overloaded diagram with tiny text.
- Pin `colorSchema: light` or `dark` in headmatter and design the palette for it. Unset, Slidev
  follows the viewer's OS preference while the exporter renders light, so hardcoded colours can
  pass PNG review and still be invisible in the browser.
- `aspectRatio` and `canvasWidth` belong in headmatter; a square social carousel and a
  widescreen talk need different compositions.

## CSS that does not damage other decks

A slide's `<style>` is scoped to that slide. Shared styles belong in the project's global
entrypoint (`style.css` or `styles/index.css`). Namespace shared classes under a deck/brand
root; generic selectors such as `.node` can collide with Mermaid's generated SVG.

Variants reuse brand tokens and CSS custom properties, not duplicated rules. CSS `@import`
before ordinary rules. Check export loads the intended fonts (bundle licensed fonts or use an
available fallback offline). Inspect computed theme styles before fighting them (a theme can
dim `h1 + p`).

## Reveals and technical explanations

`<v-clicks>` around a list or `v-click` on one element paces an explanation; `v-after` follows
the previous reveal. Meaningful content stays in the final static state. Notes can mark
`[click]` cues. Test forward/back navigation and the export. Simple transitions usually suffice.

For code, show the smallest relevant excerpt. Fences support line highlighting (`{2-3}`)
and click stages (`{1|2-3|all}`). More advanced code animation, imports and interactive demos:
[advanced Slidev](slidev-advanced.md).

## Export and delivery

- PNG review output should match the intended slide count. Count rendered slides, not raw
  `---` lines (frontmatter and imported files make that misleading).
- PDF normally captures final states. `--with-clicks` adds pages per reveal: use it when those
  stages are part of the handout, and adjust the expected count accordingly.
- Slide PDF exports do not include speaker notes. Keep the notes in the source/presenter
  view; for a separate notes deliverable, use `pnpm exec slidev export-notes talk.md`
  (present in 52.x–53.x), checking that command's help for output options.
- If a PDF loses images or global-layer state, try `--per-slide --wait-until networkidle
  --wait 1000` when supported. This fixed real deck exports where waiting alone did not.
  Inspect the resulting pages; extra waits are not proof of correctness.
- Check PDF page count and render pages back to images; for PNG open the actual images.
  Review output in a temporary/ignored directory; final deliverables at the agreed location.
- `pptx` export commonly produces slide images. Do not promise editable PowerPoint objects;
  newer versions offer `pptx-editable` with limits and fallbacks. Verify actual editability
  in the target tool, or use native PowerPoint authoring when that is the requirement.
- To deliver a web deck: `pnpm exec slidev build talk.md --base /talk/`. Match base path and
  routing to the host, and verify assets after deployment. Presenter notes can ship in a
  static build; `build --without-notes` (53.x) drops them when not meant for viewers.
  Publish only within the user's requested scope.
