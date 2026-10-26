---
name: auto-mode-policy
description: "Use when the user corrects a false Auto-mode denial (\"this should be allowed\", approves the blocked call, or switches to Full Access to clear it): turn it into a scoped standing rule on every Claude/Codex profile and verify it in Auto. Also onboarding this on a colleague's machine. Editing Claude rule files directly → claude-auto-mode."
---

# Auto-mode policy repair

Keep routine authorized work in Auto. A correction like “this should be allowed” is new
authorization evidence: capture its actual scope, fix the durable rule, resume the task. Don't
require “go”, a second confirmation or Full Access when the correction already names the
permission. An unexplained “no” is not a blanket authorization.

## A mode switch is a correction

Switching Auto → Full Access (or approving the blocked call) right after an agent reported a block
is the user's correction for that action class, same as "this should be allowed". Finish the task in
the granted mode, then make the durable repair below without asking; report the new rule in one line.
Scope it to the intent behind the blocked action ([Generalize](#generalize-to-the-intent)), never to
"everything Full Access allowed". **Exception:** irreversible data loss, production data writes,
credential exposure, spend or publishing private data → propose the rule in the report, apply only
on an explicit yes. Goal: each Full Access detour happens once per action class.

## Diagnose before editing

Read the rejected action and rationale, the user's correction, loaded global instructions and the
setup repo's policy pointer. Separate:

- **Missing trust/context:** who may read which data, through which provider/account, for what purpose.
- **Policy conflict:** an old instruction or classifier rule contradicts the user's standing intent.
- **Runtime constraint:** sandbox, managed policy, unavailable tool or login. Prose cannot remove it.

Inspect the actual configured provider homes, including custom paths and symlinks. Don't infer
account trust from a billing label or assume another person's profiles share the same owner.

## Put the correction in its owner

| Change | Canonical home |
|---|---|
| Portable correction workflow | This public skill and the global agent template |
| Personal authorization, exact roots and approved destinations | Private setup repo policy files |
| Company-wide permission | Company's private overlay, subject to its policy |
| Always-needed scope or pointer | Shared global AGENTS.md / CLAUDE.md |
| Provider enforcement | [Provider adapters](providers.md), generated from those sources |

## Generalize to the intent

A rule names a **class of work the user evidently trusts**, not the one blocked command: the user
approved painting the wall black, so the rule is "repaint walls in any colour". If the user would
obviously say yes to the next three variants (other repo, script, colour), the rule covers them.
Shape: **data/source + operation + audience/destination + purpose**, worded as intent ("publishing
releases of our own tooling through its documented release script"), hard limits spelled out.

- **Widen or merge before adding.** Extend the closest existing rule or merge two into a broader one.
  Target a few dozen north-star rules, not hundreds of special cases.
- **Generalize along the trusted axis only.** Releasing our own public kit generalizes to our other
  tooling releases, not to publishing private repos or customer data. Reading context through approved
  agent profiles does not imply publishing it, unrelated SaaS uploads, other accounts' credentials, or
  production data changes.
- **Don't generalize** the risky classes (data loss, production data, credentials, spend, private
  data): the rule stays as narrow as the evidence.
- Personal facts go in the private rule, never public defaults. Reuse an existing skill/overlay
  before adding infrastructure.

**Hard limits:** the user's correction authorizes the scoped policy edit and apply; inspect the diff
yourself, no extra approval checkpoint. Without such authorization, never weaken your own guardrails
to evade a denial. Higher-priority or managed restrictions stay binding. Never retry the denied
action through another tool to bypass the reviewer.

## Apply to the fleet, then prove it

1. Back up affected live settings outside Git. Preserve unrelated settings, deny rules and sandbox/mode.
2. Apply the provider adapters to **every configured home**, deduplicating resolved config files.
   Sync the global instruction file to each home; inspect overrides that would shadow it. Add the
   apply/check recipe to the private setup pointer so future corrections follow the same route.
3. Check effective settings, not just edited files; a running session may not have reloaded
   (fresh processes may be needed).
4. Test a harmless representative action in Auto, plus a negative case outside the grant evaluated
   without executing anything destructive or sending real data. An explicit denial ends that probe;
   retry only with new authorization/evidence or a materially safer action. Report a real runtime
   limitation instead of silently switching modes.
5. Commit/publish reusable source and sync its consumers; commit private rules separately. Resume
   the original task and verify delivery. Report scope, profile coverage and anything unverified.
   Never promise a probabilistic classifier won't err again.

## Colleague setup

Install this skill in their private setup repo (plus `claude-auto-mode` for Claude), link its path
from their global prompt, add a private policy pointer from [the template](template.md). Use their own
homes, account trust and data roots; preserve their permission modes. Installing this playbook grants
no access. No shared credentials or personal paths in the public template.
