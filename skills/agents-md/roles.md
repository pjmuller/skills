# Adapt the role, keep the quality bar

Use one [global core](global-template.md), with two or three role lines. Product
owners also ship code through agents; job title never lowers verification,
review, data-safety or repository approval requirements. Choose **one** Git
workflow from actual team policy, not from the person's technical confidence.

## Product owner who also builds

Suggested role paragraph:

> I own product outcomes and also implement through agents. Handle routine Git,
> tooling and verification yourself; bring me product tradeoffs, concrete blockers
> and a working result I can inspect. For research or writing, don't start servers
> or broad test suites. When changing code, meet the same bar as a developer.

Fold these into the core, without a second competing Commit section:

- At task start, inspect status, fetch, read repo instructions, discover the actual
  default/development branch and its protection rules. Pull safely before work
  and integrate new upstream work before pushing. An inaccessible rules API is
  unknown policy, not permission to push directly.
- Prefer the shared integration branch where team policy allows it. Routine
  commit/push is the agent's job. Avoid long-lived private branches. If a PR is
  required, use a short-lived branch/worktree, push, open/reuse the PR, fix checks
  and prepare it for the required reviewer without another reminder.
- Merge promptly once required approvals/checks and authority are satisfied.
  Never self-approve, bypass protection or mistake an AI review for a required
  human review. Distinguish pushed, awaiting approval, merged and deployed.
- Resolve ordinary conflicts in your owned work; stop only for genuine intent
  ambiguity. Never reset/stash/switch branches in a shared dirty checkout or
  rebase someone else's work. Isolate integration when needed.
- Report the result through a preview, deployed URL or PR; don't make the human
  operate the CLI. Escalations include observed symptoms, attempted verification
  and the smallest decision needed. Research/writing requests remain research/
  writing unless implementation was requested.

## Developer

Preserve the team's worktrees, PR reuse, signing and release process. Handle the
same Git housekeeping autonomously; explain technical tradeoffs when they help
review. Don't replace an established PR workflow with a template's direct-push
default, or invent deploy rights from an admin account's technical capability.

## Both roles when coding

Consequential design decisions get an opposite-family opinion before building.
Complex features and changes to auth, data, money or external contracts get an
independent review before shipping, even if small. Roughly 100–200 changed lines
is a useful review trigger, not a safe-under-this-size exemption. Verify critical
paths, prune needless complexity, and update the relevant project skill.

## Git policy discovery

Read repo instructions and CI/release configuration. For GitHub, inspect
`gh repo view --json defaultBranchRef`, applicable rules via
`gh api repos/OWNER/REPO/rules/branches/BRANCH`, and classic branch protection
where applicable. Encode only the resulting personal default globally;
project-specific branches, reviewers and deployment gates belong in that repo.
Never infer "unprotected" from a failed or partial query.
