# One-time setup, safe to rerun

Inspect relevant local setup only: current repository entrypoint/registered skills, known
personal setup repo, registered T3 projects and referenced workflow wrappers. Never scan
arbitrary personal files or copy someone else's credentials/policy. Discover facts first; ask
only for the routing-thread location, intended accounts or ownership boundaries you cannot
establish. Cloud-only agents without a local T3 session cannot route: report that, not readiness.

## Register and check

In the user's personal setup repository:

```bash
pnpm dlx skills add pjmuller/skills -s t3-route -a claude-code codex -y
```

No installer here. Install/check the command skills actually needed (`t3-manage-thread`,
which also ships `t3-find-thread` for reuse) with each skill's `scripts/install` and `--check`; verify T3
connectivity and helpers, not just registration. Follow the repo's existing Claude/Codex layout
(a source owner may use its source-symlink convention); no competing copies. Enabling Gmail:
`t3-mail-link resolve --help` must work; if `resolve` is missing, refresh through the existing
registration mechanism and rerun checks (relinking an old install cannot add it).

## Discover capability and identity

Build a small private capability note from the selected wrappers, not a new registry:

| Record | Verify read-only |
| --- | --- |
| Project roots/ownership | registered T3 projects and repo entrypoints; no auxiliary worktrees as default destinations |
| ClickUp wrapper/config | wrapper policy, workspace/list hints, `whoami`; a service token is a **service identity**, not the operator |
| Workspace wrapper/account | `workspace.json` account + required `scopes`, credential references, `whoami` identity + granted `scopes` (tokeninfo), observation date |
| Account inventory | `gws.py accounts discover <code root>` suggests rows; the user marks which mailboxes `gmail_lookup` may try ([inventory](../google-workspace-core/references/accounts.md)); `accounts list --check` |
| Browser fallback | user's profile-routing policy and signed-in identity, only when needed |
| Thread helpers | installed command paths/check results and search capability |

Distinguish documented, installed, authenticated and permission-scoped. Configured `scopes` are
requirements; record actual grants from `whoami.scopes`, not the broader `mint_scopes`. Expected
email (incl. `GWS_EXPECTED_EMAIL`) ≠ verified identity → hard stop for that integration.
`whoami` does not prove Gmail permission: run a read-only Gmail probe when enabling it. Never
print tokens or message bodies in the note. Missing optional ClickUp, Gmail or browser access =
partial readiness, not failure.

## Create the private entrypoint

A committed sibling skill outside `t3-route` with:

- a precise trigger: explicit command plus the designated routing thread;
- a link to this core, routing-thread identity and model/lifecycle defaults
  ([limits](SKILL.md#lifecycle));
- a small project catalog: roots, ownership, sibling boundaries;
- links to the user's integration wrappers and triage/playbooks;
- for recurring short requests, a private trigger lookup (below).

Reuse existing owning references; link global rules instead of duplicating them. Add a narrow
setup-repo entrypoint note: "In the designated routing thread, invoke `<private-wrapper>`; an
execution brief must not re-route its same task (see `t3-route`)." The designation is a
dedicated thread titled with a leading 🧭 (e.g. "🧭 Routing"; `t3-mail-link` keeps 🧭 threads
from owning mail cases): record its title + exact T3 ID privately via helpers/native tools,
never invented or inferred from cwd. An onboarding request may create that thread; it does not
re-route this execution task. Reruns preserve custom policy; propose only evidence-backed changes.

### Trigger lookup

`trigger-lookup.md` beside the private wrapper maps **when** to owner and exact entrypoint; no
procedures or installed-skill inventories. Start from real requests and verified files:

```markdown
| User phrasing / intent | Owner repo | Read |
| --- | --- | --- |
| “laptop hot”, “CPU”, “RAM” | personal setup repo | ../resource-audit/SKILL.md |
| “assistant answer tone” | selected product brain | AGENTS.md |
```

Build it from a bounded read-only sample of the user's own requests (e.g. `t3-my-prompts --days 14
--stats/--outline` to narrow projects, `t3-find-thread` search/peek for titles, `t3_thread_read` to
verify a request). Mark each row's basis (recent request verified · scheduled invocation, not
user-typed · catalog only, use unconfirmed) with short evidence refs (date + short thread id); keep
no raw prompts, account ids, customer details or ticket bodies. Add a row after a real routing
miss; when refreshing, recheck paths and dates and downgrade unverified rows to catalog.

The wrapper links it: "Read `trigger-lookup.md` on first invocation; use it for later routing
messages and reread after compaction or edits." Repo placement/account policy stays in its
references. Matches select context, not permissions; a diagnosis does not authorize stopping
active work. Maintain rows (add, fix, merge aliases, drop obsolete) via
[corrections.md](corrections.md), verifying paths.

## Verification handshake

`t3-pick-instance <chosen model>` shows actual account routing without creating a thread. Then
rehearse a ticket/mail/screenshot route this user's integrations support, without external
writes: fetched evidence, inferred intent, destination, whether a verified thread would be
reused. Check execution context cannot re-route the same task. Apply one neutral correction to
its owning private reference and read it back. Report readiness and specific gaps; never claim
another person's account was tested from this machine. Isolated forward-evaluation: neutral
[cases and screenshot](tests/cases.md) without live tools; judge decisions, not wording.

Daily use: paste tasks/links/images in the routing thread; correct misrouting there. Core
updates replace only the core: diff the sibling wrapper before/after to verify policy
preservation and recheck its core links.
