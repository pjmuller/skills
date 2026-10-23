---
name: ui-before-after
description: Capture the same app screens before and after a UI change (Playwright scenes against a local or staging URL) and build a before/after report - a self-contained HTML for a ticket, a compact inline version and a ticket table. Use when shipped UI changes need someone's taste review, when a feedback round asks for before/after screenshots, or when a designer should be able to keep or revert each change.
---

# UI before / after

Intent: the reviewer (often the person with design taste, who was not in the loop) judges each
change by looking, not by reading a diff. Same screen, same state, same viewport, two shots.

## Recipe

1. **Scenes first, before any edit.** Write `scenes.json` ([example](examples/scenes.example.json)):
   one scene per screen, steps `goto` · `click` · `fill` · `press` · `wait` · `wait_for` · `eval` ·
   `scroll_into_view` · `shot` (a `full_page` shot ignores scrolling). A failing step ends that scene,
   the run continues and exits 1. Reproduce the state the feedback was about: an `eval` step can swap
   in long titles or realistic counts on the page; a seeded local database can be nudged with SQL.
   Use synthetic look-alike data only: the screenshots end up in tickets.
2. **BEFORE** on unchanged code: a detached worktree at `origin/main` running the app locally, then
   `ui-shoot scenes.json --base-url http://localhost:PORT --out shots/before`. Never reconstruct a
   "before" from memory or from the edited code.
3. Make the changes. **AFTER** with the same scenes: `--out shots/after`. Add a phone-width run
   (`--viewport 390x844`) when layout changed.
4. Write `manifest.json` ([example](examples/manifest.example.json)): per row the screen, the kind
   (`bug`, `taste`, `quality`), one or two sentences on what changed and why, the before/after files.
   Mark preference changes as `taste`: that is what the reviewer may revert.
5. `ui-compare manifest.json --out ~/Downloads/<project>-<topic>-<date>` writes:

| File | For |
|---|---|
| `before-after.html` | one self-contained file: attach to the ticket, open anywhere |
| `index.html` + `before/` `after/` | browsing locally, attaching single PNGs |
| `compact.html` + `compact/` | inline in the chat: a few KB of HTML pointing at absolute JPEG thumbnail paths; pass its contents to T3 `html_render`, which inlines local images (host theme variables, no page background) |
| `attachments/` + `ticket-table.md` | upload `attachments/*` to the ticket (named `before-<file>` / `after-<file>`), then append the table: its `![[file:…]]` cells show the screenshots inline |

6. Ticket for the reviewer: per change the screen, bug vs preference, the before/after, the file to
   touch and how to revert it; bug fixes in their own commit so a taste revert never undoes a fix.

`scripts/install` links `ui-shoot` and `ui-compare` into `~/.local/bin`; `--check` also says whether
Playwright's Chromium is present (install once: `uv run --with playwright playwright install chromium`).
A project's own Playwright setup works too; only the manifest and `ui-compare` are needed for the report.
