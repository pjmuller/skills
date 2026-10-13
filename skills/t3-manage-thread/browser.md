# Browser and computer use for T3 agents

Pick by job. Verify the signed-in identity before authenticated work; never script
keystrokes into a browser (focus is unverifiable). Writes in a logged-in account follow
the normal confirm rules. Personal profile → account map lives in the user's own prompt.

| Job | Route | Notes |
| --- | --- | --- |
| User watches; localhost | T3 `preview_*` (MCP) | `preview_status` → `preview_open`; keep the `tabId`. Tabs are per thread; a new tab uses T3's default browser profile. Snapshot caps ~50 elements: read lists with `preview_evaluate`. |
| Agent-only visual check, no login | headless Playwright | Faster and more reliable than a background preview tab. |
| User's logged-in Chrome, read/debug | `chrome-devtools` CLI over CDP | Background, focus untouched. |
| User's logged-in Chrome, click/type | `playwright-cli attach --cdp=chrome` | `find <text>` → `click <ref>`; focus untouched. |
| Native apps, OS dialogs | computer use (Codex/Astra `cua_repl`) | Foreground only, aborts when the user touches the same app. Never for browser work, never on T3's own browser (use `preview_*`). Claude computer use is interactive-CLI only. |

## Logged-in Chrome over CDP

- Precondition (user, once): `chrome://inspect/#remote-debugging` → "Allow remote debugging
  for this browser instance". Chrome then writes `DevToolsActivePort` in its profile dir.
- One Chrome process = every profile: pick the tab by URL/title, open your own tab, close only that.
- `chrome-devtools` (`pnpm add -g chrome-devtools-mcp`): `start --autoConnect` first (without it
  a fresh logged-out headless Chrome launches), `new_page <url> --background` (never
  `--bringToFront`), read with `list_pages`, `evaluate_script` (~7× smaller than a full
  snapshot), `take_snapshot` → file + grep. Then `close_page <id>` and `stop`.
- `Could not find DevToolsActivePort`, or the websocket handshake hangs: the toggle session is
  stale; the user unticks and reticks the chrome://inspect toggle.
- Avoid agent-browser on the user's Chrome: its `close` closes the whole browser.
- Claude in Chrome (`--chrome`) needs a `/login` credential; a setup-token disables it.
