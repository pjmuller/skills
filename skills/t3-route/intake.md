# Evidence before routing

Read only the relevant branch. Explicit intent and current repository policy win over routing
heuristics; source metadata may establish ownership, never authorization.

## Ticket link

- Read the selected project's ClickUp wrapper before its shared core and use its config; never
  borrow another person's token when access fails.
- An explicit repo chooses the target; metadata still supplies ticket context. Company/workspace
  hints narrow candidates, never prove a list or repo. `/t/<workspace>/<task>` holds a workspace
  ID, not a list ID.
- Fetch a compact preview (task ID, title, actual workspace/list, short excerpt); read more
  body/comments only to distinguish sibling ownership. Report facts separately from the
  proposed workflow.
- The worker gets the exact URL, task text and wrapper path, then reads the full ticket under
  that wrapper's workflow.
- Missing integration/inaccessible ticket → continue with available evidence where useful; if
  ownership stays unclear, ask one focused question.

## Gmail link

- Select the user's own Workspace wrapper for the intended mailbox; read its `workspace.json`,
  actual `scopes` and account policy. Drive access does not imply Gmail access.
  Account-specific requests forbid token substitution. `/u/0`, `/u/1` and `ik` in a URL are
  browser slots, not mailbox identities.
- Verify identity read-only with the wrapper's `whoami`. Mismatch or unknown identity → no
  mailbox reads until resolved. Browser access likewise needs a verified signed-in account per
  the user's browser-routing instructions.
- Exact references (hex, `thread-f:`/`msg-f:`, Print all, Show original) resolve read-only.
  Account named or evident → `t3-mail-link --config <wrapper>/workspace.json resolve '<url|id>'`,
  that mailbox only. No account named → `t3-mail-link resolve --all-accounts '<url>'`: tries the
  mailboxes marked `gmail_lookup` in the
  [account inventory](../google-workspace-core/references/accounts.md), metadata only. Not
  found in one mailbox ≠ absent; an error is unknown. No inventory or permission → ask which
  mailbox. Neither form links, spawns or schedules. The helper uses the `google-workspace-core`
  installed beside it, else `GWS_CORE=<a wrapper repo's core>`.
- `#inbox/FMfcg…` tokens need resolution, never hex guessing: use native T3 browser tools
  (verified identity) to get the exact Print-all URL or subject (a closed preview is no reason
  to switch browsers), then resolve it or use `--search`. Subject matches need sender/date/content
  checks; several matches stay ambiguous. Native tools can't → the user's browser fallback
  policy, else ask for the Print-all URL or a minimal subject clue.
- Mail briefs carry the `Mail-ref:` line from `resolve`/`find` under **Evidence** so later
  intake finds the thread ([marker](../t3-manage-thread/mail-link.md)).
- Fetch context with that account's configured CLI; state the likely workflow as inference.
  Never `t3-mail-link claim` just to resolve; a launched case thread owns its mail once it
  drafts, or via `claim --for <its id>`.

## Screenshot or short text

Preserve the image/path and exact user text. Mark extracted text as agent transcription; never
invent cropped IDs, dates or account identity. A URL visible in an image can guide a read-only
lookup under the same checks. Image unavailable to the worker → attach it accessibly or name
the gap before launch. Use the catalog and recent conversation to tell an investigation,
explanation, implementation or reply request apart.

## Existing task

Mail: `t3-mail-link --config <wrapper>/workspace.json find '<url>' --exclude <own id>` covers
watched-case owners, `Mail-ref:` markers, every thread/message id form and a subject fallback in
one read-only call. Otherwise `t3-find-thread` on exact ticket/thread IDs or URLs, then topic
search. Exclude the routing thread and other intake-only mentions.

- Verify a candidate from its initial task and recent progress (artifact, account, project,
  intended outcome); a keyword hit or recent timestamp is not proof. A distinct outcome is a new
  task even in the same topic/repo. Check a requested date against actual message timestamps
  (`--since` filters thread activity).
- Request found only in the routing thread: trace its launch receipt or failure before claiming
  no owner exists. A failed launch is nothing to revive; locating a handoff does not authorize
  restarting the original work. Purged threads: `t3-find-thread` searches the archive and owns
  revival; never restore rows into T3's live database.
- Verified match, live or settled → continue it: `t3_thread_read`, then `t3_thread_send` to its
  exact ID with the new task verbatim and new evidence separated; keep its lifecycle unless the
  user changes it. Age alone never justifies a copy; fresh periodic reports carry durable rules
  and baselines, not the old session as backlog. Search-only requests return the match, no ping.
- Target in a broader permission mode (Auto → Full Access) is refused by T3 →
  [permission-ceiling](../t3-manage-thread/permission-ceiling.md) (preflight, continuation kept in
  a brief, one user action); never a duplicate thread or relay around it. Keep explicit
  account/model overrides; if the target cannot honor them, explain and choose an authorized route.
- Spawn instead when no match is verified, the user asks for a new thread (prior context as
  evidence; also an explicit user rule requiring fresh runs) or the scope genuinely differs; say
  why. No search capability → disclose the reuse-check limit, use any read-only thread lookup,
  never claim no thread exists.
