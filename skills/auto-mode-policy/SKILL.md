---
name: auto-mode-policy
description: Repair false auto-mode denials across Claude and Codex profiles after the user clarifies what should be allowed; record scoped standing authorization, update the correct policy layer, and verify it without switching to full access. Also use when onboarding this policy workflow on a colleague's machine.
---

# Auto-mode policy repair

Keep routine authorized work in Auto. A user correction such as “this should be allowed” is
new authorization evidence: capture its actual scope, fix the durable rule, and resume the task.
Do not require the word “go”, a second confirmation, or Full Access when the correction already
names the permission being granted. An unexplained “no” is not a blanket authorization.

## A mode switch is a correction

Switching from Auto to Full Access (or approving the blocked call) right after an agent reported a
block is the user's correction for that blocked action class, just like saying "this should be
allowed". Finish the task in the granted mode, then make the durable repair below without asking and
report the new rule in one line. Scope it to the intent behind the blocked action (see
[Generalize](#generalize-to-the-intent)), never to "everything Full Access allowed". Exception: irreversible data loss,
production data writes, credential exposure, spend or publishing private data: propose the rule in
the report and apply it only on an explicit yes. Goal: each Full Access detour happens once per
action class, so Auto keeps adapting to how this user works.

## Diagnose before editing

Read the exact rejected action and rationale, the user's correction, loaded global instructions,
and the setup repo's policy pointer. Separate:

- **Missing trust/context:** who may read which data, through which provider/account, for what purpose.
- **Policy conflict:** an old instruction or classifier rule contradicts the user's standing intent.
- **Runtime constraint:** sandbox, managed policy, unavailable tool or login. Prose cannot remove it.

Inspect actual configured provider homes, including custom paths and symlinks. Do not infer account
trust from a billing label, or assume another person's profiles share the same owner.

## Put the correction in its owner

| Change | Canonical home |
|---|---|
| Portable correction workflow | This public skill and the global agent template |
| Personal authorization, exact roots and approved destinations | Private setup repo policy files |
| Company-wide permission | Company's private overlay, subject to its policy |
| Always-needed scope or pointer | Shared global AGENTS.md / CLAUDE.md |
| Provider enforcement | [Provider adapters](providers.md), generated from those sources |

## Generalize to the intent

A rule names a **class of work the user evidently trusts**, not the one command that was blocked: the
user approved painting the wall black, the rule is "repaint walls in any colour", not "black is fine".
Ask what the user would answer to the next three variants (other repo, other script, other colour);
if "obviously yes", the rule covers them. Shape: **data/source + operation + audience/destination +
purpose**, worded as intent ("publishing releases of our own tooling through its documented release
script"), with the hard limits spelled out.

- **Widen or merge before adding.** Read the existing rules first; extend the closest one or merge two
  into a broader one. Target a few dozen north-star rules, not hundreds of special cases.
- **Generalize along the trusted axis only.** Releasing our own public kit generalizes to our other
  tooling releases, not to publishing private repos or customer data. Reading context through approved
  agent profiles does not imply publishing it, unrelated SaaS uploads, other accounts' credentials, or
  production data changes.
- **Don't generalize** the risky classes above (data loss, production data, credentials, spend, private
  data): there the rule stays as narrow as the evidence.
- Personal facts go in the private rule, never published as universal defaults. Reuse an existing
  skill/overlay before adding infrastructure.

The user's request to correct this policy authorizes the scoped policy edit and apply. Inspect the
concrete diff yourself; don't manufacture another approval checkpoint. Without such authorization,
an agent must not weaken its own guardrails to evade a denial. Higher-priority or managed restrictions
remain binding. Never retry the denied action through another tool to bypass the reviewer.

## Apply to the fleet, then prove it

1. Back up affected live settings outside Git. Preserve unrelated settings, deny rules and sandbox/mode.
2. Apply the provider adapters to **every configured home**, deduplicating resolved config files.
   Sync the global instruction file to each home; inspect overrides that would shadow it. Add the
   apply/check recipe to the private setup pointer so future corrections follow the same route.
3. Check effective settings, not just edited source files. Fresh processes may be required. A new
   file does not prove an existing session reloaded its policy.
4. Test a harmless representative action in Auto. Include a negative case that stays outside the
   grant, evaluated without executing a destructive operation or sending real data anywhere.
   An explicit denial ends that probe; only new authorization/evidence or a materially safer action
   justifies a retry. Report a real runtime limitation instead of silently switching modes.
5. Commit/publish reusable source and sync its registered consumers; commit private rules separately.
   Resume the original task and verify delivery. Report scope, profile coverage and any unverified
   behavior, tersely. Never promise a probabilistic classifier cannot make another mistake.

## Colleague setup

Install this skill in their private setup repo, plus `claude-auto-mode` if they use Claude. Link its
absolute path from their global prompt and add a private policy pointer using [the template](template.md).
Use their own configured homes, account trust and approved data roots. Preserve their permission modes;
installing this playbook alone grants no new access. No shared credentials or PJ-specific paths belong
in the public template.
