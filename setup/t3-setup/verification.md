# Verification: checkpoints, local feedback loops, acceptance

## Checkpoints

`ONBOARDING.md` in the recipient's setup repo, committed after every lane transition (no secret values,
no Send links). A new session reads it first and resumes.

```markdown
| Lane | Step | Status | Last good check (date, command → result) | Error (exact line) | Next command |
|---|---|---|---|---|---|
| B | Workspace token (work mailbox) | blocked | — | consent screen: admin policy | ask user to retry in T3 browser |
```

Status: pending · running · waiting-human · blocked · passed. One-shot steps (Send fetch, credential
issuance, OAuth mint) record "done at <time>" so a resumed session never repeats them blindly.

## Local app feedback loop

Coding agents need a boot + check loop that runs in seconds and cannot touch the outside world.

1. Runtime from the repo's pins (`mise install`), deps (`bundle install` / `pnpm install`), native libs via brew.
2. Database: compose service or throwaway container (`--tmpfs` data dir) bound to loopback; schema load,
   never a production dump.
3. Seed: the repo's demo/fake seed (fictional names, `@example.invalid`); a seed that imports from
   production or uses real addresses is a finding, not a step.
4. External effects off: mail to a local catcher or `:test`, background workers not started (web process
   only), sandbox/demo flags set, integration keys unset or dummy. List the settings checked.
5. Smoke: HTTP status per key route, one UI check in the T3 browser (login + one page), a fast test subset,
   then the full suite once. Record timings.
6. Clean-room runner for machines whose env files hold production URLs: `env -i` + explicit dev variables.

## Acceptance matrix

Two columns, never merged: what the sender proved on their machine vs what ran on the recipient's.
"Not yet run" is a valid state; a sender-side pass never fills the recipient column.

| Area | Sender (prepared/verified) | Recipient machine (proof) |
|---|---|---|
| Bootstrap | references, revisions, ZIP secret scan | tool versions in a fresh shell; a real T3 turn per provider |
| Identity + access | grants applied, policy simulation | `gh api user`, cloud `whoami`, product CLI identity; negative checks (forbidden ids → 404/403) |
| Apps | recipe proven in a clean room | seeded pages 200, UI login, mail/jobs isolated, tests green |
| Workflow | wrapper templates, routes | installer `--check`s, scheduler smoke removed, a tracker link and a mail link route correctly |
| Delivery | Send created (views, expiry) | Send consumed once, files 600, stage deleted; Send shows used/deleted |
| Usability | — | one real task from their job, end to end |

Finish with the feedback block from [SKILL.md](SKILL.md#verify-live-and-record).
