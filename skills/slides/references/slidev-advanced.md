# Slidev: use only when the explanation benefits

These capabilities are a menu, not a checklist. Adapted from [upstream](sources.md).
Check the installed version before introducing newer syntax into an existing deck.

## Code that changes

Use Shiki's line highlights for attention. Use Magic Move when the change itself is the point:

`````md
````md magic-move
```ts
const answer = await search(question)
```
```ts
const answer = await search(question, context)
```
````
`````

The wrapper uses four backticks; inner blocks use three. Verify every click state. An imported
snippet (`<<< @/snippets/example.ts`) keeps a runnable example and the slide in sync, but trim
it to the lines the audience needs. Avoid a scrolling code pane in a projected talk.

## Reuse and custom visuals

`src: ./pages/intro.md` in slide frontmatter imports slides; the importing entry's duplicate
frontmatter keys win. Split genuinely reusable sections, not every slide by habit.

Vue components in `components/` support diagrams and interactive visualizations without
turning the deck into an application. Keep a useful static state for exports. Global layers
(`global-top.vue`, `global-bottom.vue`) suit persistent branding, but test them during export;
`slide-top.vue` can avoid state-related capture problems in supported versions.

KaTeX supports `$...$` inline and `$$...$$` blocks. Give symbols meaning in the explanation.
Use a simple local diagram when an external renderer would make offline delivery unreliable.

## Live demonstrations

Monaco fences (`{monaco}` / `{monaco-run}`) can make workshops interactive; normal code fences
are more reliable for a talk that does not need editing. Rehearse the real execution path,
latency and reset state, and have a static fallback. HTML/Vue, embedded media and iframes may
work live while appearing empty or frozen in exports.

`duration: 20min` with `timer: countdown` can support rehearsal. Presenter view, recordings
and remote controls are optional; use the project's installed CLI help for their exact flags.
Do not expose remote control just to get a local preview.

Newer upstream features include Comark, editable PPTX and an MCP endpoint. They are not
prerequisites for this skill; no toolchain upgrade is implied. Consult the linked upstream
feature reference only when a request needs a capability beyond this bundled guide.
