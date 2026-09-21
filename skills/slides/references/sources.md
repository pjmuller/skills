# Sources and attribution

## Slidev

Slidev by Anthony Fu and contributors, MIT licensed. Selected guidance is condensed and
adapted into `slidev.md` and `slidev-advanced.md`; it is bundled here, not a runtime dependency
on a second installed skill. Examples were simplified; project/export pitfalls and presentation
judgement are our additions. This is a curated guide, not the complete upstream manual.

Reviewed 2026-09-21 at commit `30a0a54c8739b4b395d9b336a6304cc8ebcc3947`:
[upstream skill and sibling references](https://github.com/slidevjs/slidev/tree/30a0a54c8739b4b395d9b336a6304cc8ebcc3947/skills/slidev).
Adaptation sources: `SKILL.md`; reference files `core-syntax`, `core-cli`, `core-headmatter`,
`core-frontmatter`, `core-layouts`, `core-components`, `core-animations`, `core-exporting`,
`core-hosting`, `style-scoped`, `diagram-mermaid`, `diagram-latex`, `layout-canvas-size`,
`layout-global-layers`, `animation-click-marker`, `code-line-highlighting`, `code-magic-move`,
`code-import-snippet`, `syntax-importing-slides`, `syntax-frontmatter-merging`, `editor-monaco`,
`editor-monaco-run` and `presenter-timer` (all `.md`).

The full [upstream MIT notice](../LICENSE.slidev) travels with this installed skill.
Use [official documentation](https://sli.dev/) for capabilities outside the curated selection;
check local version support rather than assuming upstream main matches an older deck.

## Presentation craft

Original concise synthesis, informed by:

- [TEDx: prepare speakers and program](https://www.ted.com/tedx/organizer-guide/prepare-speakers-and-program):
  separate complex visuals into digestible ideas and rehearse delivery.
- [Duarte: the audience is the hero](https://www.duarte.com/blog/presentation-storytelling-audience-is-hero/):
  organize the story around the audience's situation and change, rather than company biography.
- [Duarte: develop a big idea](https://www.duarte.com/blog/how-to-develop-the-best-big-idea-for-your-presentation/):
  connect one clear point of view to the audience's stakes and desired action.

These sources inform the judgement guidance, not a mandatory narrative formula. No proprietary
training material, slide assets or source prose is redistributed.

Operational lessons were distilled from existing Rootcause, KampAdmin, DentAI, ProBackup
ideation, LeerHeld and SaaS event decks: local CLI resolution, headmatter, brand class inheritance,
CSS collisions, empirical diagram sizing and export verification. Company-specific material
stays in project wrappers; the public core contains no customer data or private brand assets.
