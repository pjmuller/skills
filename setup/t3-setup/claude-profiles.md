# Claude Code profiles: multi-account + 1-year setup-token

Recommended way to run several Claude subscriptions (Pro/Max/Team) on one machine, each one
authenticated for a year instead of a month. Field-tested 2026-10-02 → 2026-11-06 on three Max
accounts used all day through T3 and `claude -p`: no auth failure, and one token survived a plan
upgrade (5x → 20x).

> [!IMPORTANT]
> A `/login` credential dies after ~30 days (absolute refresh-token expiry; a plan change can revoke it
> sooner). `claude setup-token` mints a **one-year** token that outranks `/login`
> ([precedence](https://code.claude.com/docs/en/authentication#authentication-precedence): step 5 vs 7),
> so model turns keep working when the monthly login dies. It is **inference-only**: see Limits.

## One home per account

- Each account gets its own `CLAUDE_CONFIG_DIR` (`~/.claude_<slug>_home`); the default account keeps
  `~/.claude` with the variable **unset**. Never isolate with `HOME`.
- The Keychain item is named after the exact `CLAUDE_CONFIG_DIR` string; setting it to
  `$HOME/.claude`, or a differently spelled path, reads an item login never wrote → "Not logged in".
- T3: one Claude provider instance per home via `config.homePath`, never a `CLAUDE_CONFIG_DIR`
  environment row ([SKILL.md](SKILL.md#accounts-and-providers)).
- Share `CLAUDE.md` and `skills` across homes by symlink; never share credentials.

## Per profile

1. Log in once with `/login` (`env -u CLAUDE_CODE_OAUTH_TOKEN -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN
   CLAUDE_CONFIG_DIR=… claude auth login --claudeai --email <email>`): records the account and
   organization in `<home>/.claude.json`, which routing and usage tools read.
2. `CLAUDE_CONFIG_DIR=<home> claude setup-token` (omit the variable for the default home). Open the
   URL in the browser profile signed in to **that** account and pick the intended organization (a
   similarly named old team org is a common trap).
3. Store it in `<home>/settings.json` → `"env": {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-…"}`,
   `chmod 600`. Never in a shell rc, mise/global env or a repo: a global token overrides every
   profile's account.
4. Verify: `claude auth status --json` → `authMethod: oauth_token`; `claude -p "reply with ok" --model haiku`
   answers. In T3, refresh the provider until it shows ready.
5. Put a renewal reminder ~11 months out (e.g. `t3-schedule add --once …`).

<details><summary>Letting an agent mint it (pty gotchas)</summary>

`claude setup-token` is interactive; an agent drives it in a pty:

- `BROWSER=/usr/bin/true` stops the browser auto-opening the wrong profile; print the URL instead.
- The default pty is 80 columns, so the 108-character token wraps: set a wide window size
  (`TIOCSWINSZ`, e.g. 400 cols) **and** join every yellow (`\x1b[38;5;220m`) segment after
  "Your OAuth token" before matching `sk-ant-oat01-[A-Za-z0-9_-]+`.
- The code prompt echoes asterisks; the CLI keeps running after printing the token: kill the child
  once captured.
- Under `nohup`/background runs stdout is block-buffered: `PYTHONUNBUFFERED=1` or `flush=True`, else
  the URL never shows.
- Accept the code from a file (`--code-file`) so the agent can paste it from the browser itself.
</details>

## Limits

The token carries only `user:inference`
([docs](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token)). Still needing
a live `/login` (≤30 days):

| Feature | With setup-token |
| --- | --- |
| Remote Control, claude.ai connectors (e.g. Claude Docs MCP) | unavailable (documented) |
| Claude in Chrome | `--chrome` silently ignored; log shows `[Claude in Chrome] Disabled: OAuth token has no scope accepted` |
| Cloud sessions API (`/v1/code/sessions`) | 401 `oauth_scope_insufficient` (tested 2026-11-06) |
| Usage API (quota %) | refused; `t3-limits` reads quota from a tiny probe turn instead ([limits.md](../../skills/t3-manage-thread/limits.md)) |
| `--bare` | ignores the token |
| Local MCP, skills, hooks, T3, `claude -p` | work |

Tools that need the `/login` credential must strip the token, or it wins: `env -u CLAUDE_CODE_OAUTH_TOKEN`
**and** skip user settings (`--setting-sources project,local`), since the token lives there. When that
login has expired, re-run step 1; the setup-token is untouched.

## Sharing and renewal

- The token is a bearer secret for the whole subscription. Prefer one per (account, machine); a copy
  on a second machine must be replaced there too when you re-mint or revoke.
- Renew: repeat steps 2-4 before expiry. Open: whether a plan **downgrade** revokes it (an upgrade did not).
