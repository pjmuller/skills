# Browser and computer use for T3 agents

Escalate in this order. Verify the signed-in identity before authenticated work; never script
keystrokes into a browser (focus is unverifiable). Writes in a logged-in account follow
the normal confirm rules. Personal profile → account map lives in the user's own prompt.

| # | Route | When | Notes |
| --- | --- | --- | --- |
| 1 | T3 `preview_*` (MCP) | Always first: browser work incl. signed-in accounts, localhost, user watches | `preview_status` → `preview_open {profileId, reuseExistingTab:false}`: a **new tab per profile**. A reused tab keeps its old profile even when you pass another `profileId` (no error, verified v0.1.1); check the tab's `profileId` in `tabs[]`. Omitted profile = Default (may have no logins). A profile's cookies are shared by every thread using it; incognito tabs are isolated. Snapshot caps ~50 elements: read lists with `preview_evaluate`. |
| 2a | User's real Chrome (CDP) | T3 can't: login missing in T3, site breaks in T3, passkey-only | `chrome-devtools` / `playwright-cli attach --cdp=chrome`. One connection per task: Chrome ≥ 144 shows a focus-stealing "Allow remote debugging?" modal on every new connection, which the user approves. Also ask the user once to sign in inside T3 so the next run stays on route 1. |
| 2b | Computer use (Codex/Astra `cua_repl`; from Claude via `delegate_task`) | Visual steps CDP can't script, OS dialogs, native apps | Foreground only, aborts when the user touches the same app. Never on T3's own browser. Claude computer use is interactive-CLI only. |
| — | headless Playwright | Agent-only visual check, no login | Faster and more reliable than a background preview tab. |

## Signing in inside T3 (v0.1.x)

- Import: Settings → Integrations → Browser profiles → import from Chrome = cookies only, Chrome must be quit, re-run when a Chrome login is fresher. **Google sessions don't survive import** on recent Chrome (device-bound session credentials keep the key in Chrome): sign in to Google inside T3 instead. Several Google accounts in one profile: pick by email with `?authuser=<email>` (e.g. `mail.google.com/mail/?authuser=…`), not by `/u/<n>` slot. Only the agent session that opened a tab can close it.
- Login page: default = ask the user once to log in inside the visible T3 tab with their password manager app (name host, account, profile, why). Agent-driven logins only when they ask for it.
- Password/TOTP, agent-driven: a vault helper (e.g. [bitwarden](../bitwarden/SKILL.md) `bw-once copy`) puts one field on the clipboard; agent `preview_press Meta+V` lands only while that tab has keyboard focus (the user clicked into it). In-page clipboard reads are denied. Never `preview_type` a secret.
- Passkeys: v0.1.0 has no macOS passkey sheet (password-manager passkeys unavailable); sign in in Chrome, then re-import cookies.

## Real Chrome over CDP (route 2a)

- Every `chrome-devtools start`, `playwright-cli attach --cdp`, or `connect_over_cdp` = one consent modal ([Chrome blog](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session); persisting it: [chrome-devtools-mcp #825](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/825), not planned). The modal is the user's approval: one connection per task; never automate the dialog.
- Precondition (user, once): `chrome://inspect/#remote-debugging` toggle. Toggle off or handshake stale → report; never quit/restart the user's Chrome or edit its prefs.
- One Chrome process = every profile: open your own tab (`new_page <url> --background`, never `--bringToFront`), close only that; new CDP tabs open in the last-used profile.
- `chrome-devtools` (`pnpm add -g chrome-devtools-mcp`): `start --autoConnect` first (without it a fresh logged-out headless Chrome launches), read with `list_pages`, `evaluate_script` (~7× smaller than `take_snapshot`), then `close_page <id>` and `stop`.
- Avoid agent-browser on the user's Chrome: its `close` closes the whole browser.
- Claude in Chrome (`--chrome`) needs a `/login` credential; a setup-token disables it.
