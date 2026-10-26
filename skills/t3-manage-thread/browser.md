# Browser and computer use for T3 agents

Escalate in order. Verify the signed-in identity before authenticated work; never script keystrokes into a browser. Logged-in writes follow normal confirm rules. Profile → account map: the user's own prompt.

| # | Route | When | Notes |
| --- | --- | --- | --- |
| 1 | T3 `preview_*` (MCP) | Always first: signed-in accounts, localhost, user watches | `preview_status` → `preview_open {profileId, reuseExistingTab:false}`: **new tab per profile**; reused tabs silently keep their old profile (v0.1.1): check `profileId` in `tabs[]`. No profile = Default (may lack logins). Profile cookies shared across threads; incognito = in memory only, still one partition shared by all threads until T3 quits. Snapshot caps ~50 elements: lists via `preview_evaluate`. |
| 2a | User's real Chrome (CDP) | T3 can't: login missing, site breaks, passkey-only | `chrome-devtools` / `playwright-cli attach --cdp=chrome`, one connection per task (consent modal, below). Ask the user once to sign in inside T3 (next time: route 1). |
| 2b | Computer use (Codex/Astra `cua_repl`; Claude via `delegate_task`) | Visual steps CDP can't script, OS dialogs, native apps | Foreground; aborts when the user touches that app. Never on T3's browser. Claude computer use: interactive CLI only. |
| — | headless Playwright | Agent-only visual check, no login | Beats background preview tabs. |

## Signing in inside T3 (v0.1.x)

- Import (Settings → Integrations → Browser profiles → from Chrome) = cookies only, Chrome quit; re-run for fresher logins. **Google sessions don't survive import** (device-bound): sign in inside T3. Several Google accounts per profile: `?authuser=<email>` (e.g. `mail.google.com/mail/?authuser=…`), not `/u/<n>`. Only a tab's opener session can close it.
- Login page: ask the user once to log in in the visible T3 tab via their password manager (name host, account, profile, why). Agent-driven only on request: a vault helper (e.g. [bitwarden](../bitwarden/SKILL.md) `bw-once copy`) clips password/TOTP; `preview_press Meta+V` lands only while the tab has keyboard focus (user clicked in); in-page clipboard reads are denied. Never `preview_type` a secret.
- Passkeys: no macOS passkey sheet (v0.1.0); sign in in Chrome, re-import cookies.

## Real Chrome over CDP (route 2a)

- Chrome ≥ 144: each `chrome-devtools start`, `playwright-cli attach --cdp` or `connect_over_cdp` pops a focus-stealing "Allow remote debugging?" modal ([Chrome blog](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session); [#825](https://github.com/ChromeDevTools/chrome-devtools-mcp/issues/825): no persisting). It is the user's approval: one per task, never automate it.
- Precondition (user, once): `chrome://inspect/#remote-debugging` toggle. Off/stale handshake → report; never quit/restart their Chrome or edit its prefs.
- One process = all profiles; new CDP tabs open in the last-used one. Own tab only (`new_page <url> --background`, never `--bringToFront`), close only that.
- `chrome-devtools` (`pnpm add -g chrome-devtools-mcp`): `start --autoConnect` (else a logged-out headless Chrome launches), `list_pages`, `evaluate_script` (~7× smaller than `take_snapshot`), `close_page <id>`, `stop`.
- No agent-browser on the user's Chrome: its `close` closes the whole browser.
- Claude in Chrome (`--chrome`) needs a `/login` credential; a setup-token disables it.
