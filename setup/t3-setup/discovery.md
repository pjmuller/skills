# Discovery: person + repos → access manifest (sender, read-only)

Paste to the sender's lead agent, filling the two lines:

```text
Onboarding discovery for <person> (<role>, <dev level>, <OS if known>). Repos: <owner/name, …>.
Execute https://raw.githubusercontent.com/pjmuller/skills/main/setup/t3-setup/discovery.md. Read-only.
```

## Rules

- Read-only: no grants, invitations, key creation, production writes or messages. Production reads only
  through each repo's sanctioned read path.
- Never print or write a secret value: names, lengths, `sha256` equality only. Raw outputs with personal
  data → chmod-600 files, deleted at the end.
- External facts (subscription terms, token lifetimes, pricing, CLI auth flows) verified online, cited.
- Facts about the person from the sender's colleague notes; stale notes get re-verified.

## Clusters (one parallel read-only worker each; brief each with this file + the person block)

1. **Person + repos**: role summary safe for their own bundle (no private assessments); per repo:
   owner/name, private, default branch, created, their current permission, deploy trigger
   (`.github/workflows/*`), branch protection (`gh api repos/<o>/<r>/branches/<b>/protection`), Auto-mode
   overlay; whether a personal setup repo exists; prior setup attempts and what's stale; routes a
   dispatch wrapper needs (trackers, mailboxes) and the nearest existing wrapper to copy.
2. **Env + credentials**: per repo every variable (`mise.toml` `[env]`, env files by name, `.env.sample`,
   `ENV[`/`ENV.fetch` greps, skill wrappers) → manifest row; CLIs per repo; subscription auth for each
   provider (how the sender's profile authenticates, what the terms allow); secret delivery size and shape.
3. **Product access boundaries** (per product with roles): the real authorization model from code
   (`file:line`), current roles of the person, what each candidate role exposes, an exact grant proposal
   with negative checks. Anything irreversible (moving data between scopes) → a decision, not a step.
4. **Cloud identity**: accounts/profiles (don't mix them), existing identities and how peers get in,
   resource inventory, draft allow + explicit-deny policies, escalation paths (instance roles, CI/OIDC
   trust, PassRole, shells into containers holding secrets), simulator matrix, identity type
   (SSO > browser login > access key), exact creation commands.
5. **Local feedback loops**: per app the recipe in [verification.md](verification.md#local-app-feedback-loop),
   proven in a sibling worktree with a throwaway DB and a clean environment (`env -i`), then cleaned up.

## Output: `access-manifest` rows

| Name | Purpose | Need | Source | Destination | Validation | Revoke / expiry |
|---|---|---|---|---|---|---|
| `EXAMPLE_API_KEY` | issue tracker skill | skill | own | `~/.config/mise-env/<org>/<repo>.env` (600) | `<cli> whoami` | tracker settings → tokens |

- **Need**: boot · test · skill · prod (prod never goes to the recipient's machine).
- **Source**: own (they create it with their login) · shared (company secret → the Send) · local (they
  generate a dev value) · sender-only (never shared).
- Plus: CLI list per repo, proposed grants (with commands, not run), the decisions for the sender
  (D1, D2… each with options and a pick), and risks found on the way (deploy holes, drifted docs).
