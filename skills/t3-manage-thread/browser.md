# Browser and computer use for T3 agents

Pick by job. Verify the signed-in identity before authenticated work; never script
keystrokes into a browser (focus is unverifiable). Writes in a logged-in account follow
the normal confirm rules. Personal profile → account map lives in the user's own prompt.

| Job | Route | Notes |
| --- | --- | --- |
| Any browser work, incl. signed-in accounts; user watches; localhost | T3 `preview_*` (MCP) | `preview_status` → `preview_open {profileId}` (explicit; the Settings default profile may be empty); keep the `tabId`. A profile's cookies are shared by every thread using it; no-profile/incognito tabs are isolated. Snapshot caps ~50 elements: read lists with `preview_evaluate`. |
| Agent-only visual check, no login | headless Playwright | Faster and more reliable than a background preview tab. |
| User's real Chrome (CDP) | `chrome-devtools` / `playwright-cli attach --cdp=chrome` | **Last resort, user's OK per task.** Chrome ≥ 144 shows a focus-stealing "Allow remote debugging?" modal on every new connection. |
| Native apps, OS dialogs | computer use (Codex/Astra `cua_repl`) | Foreground only, aborts when the user touches the same app. Never for browser work, never on T3's own browser (use `preview_*`). Claude computer use is interactive-CLI only. |

## Signing in inside T3 (v0.1.0)

- Import: Settings → Integrations → Browser profiles → import from Chrome = cookies only, Chrome must be quit, re-run when a Chrome login is fresher.
- Password/TOTP: a vault helper (e.g. [bitwarden](../bitwarden/SKILL.md) `bw-once copy`) puts one field on the clipboard; agent `preview_press Meta+V` lands only while that tab has keyboard focus (the user clicked into it). In-page clipboard reads are denied. Never `preview_type` a secret.
- Passkeys: v0.1.0 has no macOS passkey sheet (password-manager passkeys unavailable); sign in in Chrome, then re-import cookies.

## Real Chrome over CDP (last resort)

- Every `chrome-devtools start`, `playwright-cli attach --cdp`, or `connect_over_cdp` = one consent modal ([Chrome blog](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session); persisting it: [chrome-devtools-mcp #825](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/825), not planned). Ask first; one connection per task; never automate the dialog.
- Precondition (user, once): `chrome://inspect/#remote-debugging` toggle. Toggle off or handshake stale → report; never quit/restart the user's Chrome or edit its prefs.
- One Chrome process = every profile: open your own tab (`new_page <url> --background`, never `--bringToFront`), close only that; new CDP tabs open in the last-used profile.
- `chrome-devtools` (`pnpm add -g chrome-devtools-mcp`): `start --autoConnect` first (without it a fresh logged-out headless Chrome launches), read with `list_pages`, `evaluate_script` (~7× smaller than `take_snapshot`), then `close_page <id>` and `stop`.
- Avoid agent-browser on the user's Chrome: its `close` closes the whole browser.
- Claude in Chrome (`--chrome`) needs a `/login` credential; a setup-token disables it.
