# One-time setup, safe to rerun

Inspect relevant local setup only: current repository entrypoint/registered skills,
known personal setup repo, registered T3 projects and referenced workflow wrappers.
Do not scan arbitrary personal files or copy someone else's credentials/policy.
Discover facts first; ask only for the dispatch location, intended accounts or
ownership boundaries that cannot be established. Cloud-only agents without a local
T3 session cannot use these dispatch helpers; report that limit, not readiness.

## Register and check

In the user's personal setup repository, register the public instructions locally:

```bash
pnpm dlx skills add pjmuller/skills -s t3-route -a claude-code codex -y
```

This instruction-only skill has no installer. Install/check the existing command
skills actually needed (`t3-manage-thread`; `t3-find-thread` for reuse), using each
skill's `scripts/install` and `scripts/install --check`. Verify T3 connectivity and
helper availability, not just skill registration. Follow the repository's existing
Claude/Codex registration layout; do not create competing copies. A source owner
may use the repository's established source-symlink convention instead.
When enabling Gmail, check `t3-mail-link resolve --help`. If the installed helper
lacks `resolve`, update through its existing registration/refresh mechanism, then
rerun installer/readiness checks; relinking an old installation alone cannot add it.

## Discover capability and identity

Build a small private capability note from the selected wrappers, not a new registry:

| Record | Verify read-only |
| --- | --- |
| Project roots/ownership | registered T3 projects and repository entrypoints; avoid auxiliary worktrees as default destinations |
| ClickUp wrapper/config | wrapper policy, configured workspace/list hints, `whoami`; a service token is a **service identity**, not the operator |
| Workspace wrapper/account | `workspace.json` account + required `scopes`, selected credential references, `whoami` identity + actual granted `scopes` from tokeninfo, observation date |
| Browser fallback | user's profile-routing policy and signed-in identity, only when needed |
| Thread helpers | installed command paths/check results and relevant search capability |

Distinguish documented, installed, authenticated and permission-scoped capabilities.
Configured `scopes` are requirements; record actual grants from `whoami.scopes`
(tokeninfo), not the broader `mint_scopes`. If the wrapper expects a specific
email (including `GWS_EXPECTED_EMAIL`), compare the verified identity; mismatch is a
hard stop for that integration. Successful `whoami` does not prove Gmail permission:
use an appropriate read-only probe when Gmail routing is being enabled. Never print
tokens or private message bodies in the readiness note. Missing optional ClickUp,
Gmail or browser access means partial readiness, not failure of all routing.

## Create the private entrypoint

Create or refine a committed sibling skill, outside `t3-route`, with:

- A precise local trigger: explicit command plus the designated dispatch conversation.
- A link to this core, dispatch identity/location and model/lifecycle defaults.
- A small project catalog: roots, ownership and sibling boundaries.
- Links to the user's own integration wrappers and relevant triage/playbooks.

Reuse existing owning references rather than another rulebook. Add a narrow setup-repo
entrypoint note: "In the designated dispatch conversation, invoke `<private-wrapper>`;
an execution brief must not redispatch its same task (see `t3-route`)." Establish the
actual designation as a dedicated setup thread (for example, "Dispatch"): discover
and record its title + exact T3 ID privately using supported helpers/native tools,
never invent an ID or infer it from cwd. An onboarding request can authorize creating
that dedicated conversation; it does not redispatch this execution task.
Link global rules instead of duplicating them. Keep account and personal policy in
the wrapper. Reruns preserve custom policy; propose only evidence-backed changes.

## Verification handshake

Run a dry-run spawn using the chosen root/model and a neutral task; inspect actual
account routing without creating a thread. Then rehearse a ticket/mail/screenshot
route supported by this user's integrations, without external writes: show fetched
evidence, inferred intent, destination and whether a verified thread would be reused.
Check that execution context cannot redispatch the same task. Apply one neutral user
correction to its owning private reference and read it back. Report readiness and
specific gaps; never claim another person's account was tested from this machine.
For isolated forward-evaluation, use the neutral [cases and screenshot](tests/cases.md)
without live tools; judge decisions rather than matching instruction wording.

Daily use: paste tasks/links/images in the dispatch conversation; correct misrouting
there. Public-core updates replace only the core: compare the sibling wrapper's
before/after hash or diff to verify policy preservation, and recheck its core links.
