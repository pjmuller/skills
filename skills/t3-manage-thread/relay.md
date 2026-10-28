# t3-relay: start or message a thread from a script outside T3

For launchd jobs and pollers (t3-schedule, recording-watcher, t3-mail-link, warm-ups). Agents inside T3
call the MCP tools directly and never need this, not even to get past a `runtime_mode_escalation_denied`
([permission-ceiling.md](permission-ceiling.md)).

T3 ≥ 0.1.2's own CLI (`~/.t3/bin/t3 thread start|send|show|list`) is fine for a quick manual thread, but
takes no model options (T3 defaults: Opus medium, Sol low) and no retry key: scripts keep `t3-relay`
for capacity routing, house effort and confirmed delivery.

```bash
t3-relay launch --project /abs/repo --title "⏰ Daily digest" --model opus [--wait 120] -- "Read and execute /abs/brief.md"
t3-relay send --thread <threadId> [--mode queue] [--wait 120] -- "New mail in the linked thread: …"
t3-relay status <rid> [--wait 60]   # ok <threadId> | failed <why> | pending <why>
t3-relay check                      # T3 reachable, MCP client approved, legacy relay hosts listed
```

- **Model**: alias, id or provider, resolved per [routing.md](routing.md#models) (account by capacity,
  house effort, small-model refusal). No `--model`: the named `--instance`'s provider default, else
  opus, else astra; unknown provider → `--model` required. `--instance` constrains Claude/Codex capacity
  routing (other providers keep the named account); `--effort` overrides house effort.
- **Launches** run in the user's new-thread permission default (`defaultRuntimeMode`, e.g. Auto; unset →
  `full-access`) at the project root.
- **Probe cleanup:** `launch --settle-after-run SECS` waits for a completed, untouched first run,
  then settles it via MCP. Use only for warm-ups/probes where a completed turn is the whole task;
  it does not judge the answer. Failed, unfinished, snoozed or repurposed threads stay open.
  Cleanup errors leave launch acceptance successful (no duplicate retry). Lost launch responses
  skip cleanup. Mutually exclusive with `--settle-when-done`, whose agent judges real work.
- **Output contract** (callers parse it): exit 0 prints `accepted: relay <rid> via mcp (<threadId>)` and
  the thread/message exists (`--wait` adds `ok <threadId>`). Exit 1 = T3 refused or unreachable, nothing
  ran. `--settle-after-run` adds `settled: <threadId>` or `left open: <reason>: <threadId>` after
  acceptance; cleanup failure keeps exit 0. Exit 1 means retry is safe. Exit 2 = usage.
  Lost answer (timeout after sending): still `accepted`; `status`
  decides by the effect (thread with that title since the request / message `clientRequestId
  relay-<rid>`), absent after 10 min = `failed`. With `--wait` that case exits 3 while unresolved: don't
  retry. Records: `~/.t3/userdata/t3-relay/` (7 days).

## How it works

`t3-relay` is an approved MCP client of T3 itself (`client:<session>` namespace) on loopback `/mcp`,
calling the same tools agents use: deterministic, no model, no host thread. Its 30-day token comes from
T3's MCP OAuth (PKCE), approved with a one-time pairing code minted by the desktop app's own CLI
(`~/.t3/bin/t3 auth pairing create`; a global `t3` can lag the app); cached 0600 in
`~/.t3/userdata/t3-relay/mcp-client.secret`, renewed when 3 days remain or on 401. Nothing to set up.
Internals (OAuth routes, read-only `statev2.sqlite` lookups for `status`) live only in `scripts/t3-relay`.

- **Not webhooks**: since T3 0.1.1 ([#20447](https://github.com/pingdotgg/t3code/pull/20447)) every
  webhook `{{placeholder}}` is framed as untrusted data, so a model bridge rightly refuses instructions
  from it; don't word around that safety layer. Leftover `⚙️ T3 relay` webhook tasks (`t3-relay check`
  lists them): `delete_scheduled_task` each, then settle its host thread.
- **Not `t3 auth session issue`**: its sessions have no runtime ceiling, so MCP treats them as
  `approval-required` and refuses `full-access` launches. The OAuth approval sets the ceiling.

Probe: `t3-relay launch --model haiku --allow-small-model --effort low --settle-when-done --wait 60
--project <repo> --title "relay probe" -- 'Reply "ok".'`
