---
name: agents-md
description: "Use to write, trim or merge an agent entrypoint (a repo's AGENTS.md / CLAUDE.md, or the global cross-project prompt and its shared template), or to write a handoff prompt between people, agents or roles (\"onboard agents to this repo\", \"this prompt is bloated\", \"re-sync the global template\"). Not general documentation."
---

# Agent entrypoints

Give a capable agent the context that changes its decisions: what the project is for, who
depends on it, where responsibility ends, how to verify its work. Explain why and the desired
outcome; leave implementation open unless a real constraint or verification need demands precision.

| Concern | Open |
| --- | --- |
| A repository's entrypoint | this file |
| User-level file loaded in every repo: write, prune, merge the [template](global-template.md), re-sync, port improvements | [global.md](global.md) |
| Product-owner vs developer adaptation, agent-owned Git housekeeping | [roles.md](roles.md) |
| Handoffs: relay prompt, dev → non-technical, bug report → dev | [handoff.md](handoff.md) |
| Independent review and reasoned pushback | [review procedure](../t3-manage-thread/code-review.md) |
| PR description, notifying the approver, reviewing a PR | [pr-review](../pr-review/SKILL.md) |

Bundled files are templates; the person's live prompt stays outside this installation (skill
updates replace it). Where to register: [README](../../README.md#registration-scope).

## Ground it

Read the existing entrypoint, parent instructions and linked skills/glossaries. Resolve
symlinks and forwarding files before choosing the canonical file; preserve the discovery
arrangement and unrelated edits. Check every claim, old or new, against source, manifests and
test/CI entrypoints: prose is evidence, not proof. Never invent product strategy.

## Choose what earns space

Lenses, not a template or heading quota. Keep distinctive intent and verified constraints;
omit what adds no decision value; link detail to its owner instead of copying it.

- **Intent and users:** problem, audience, valuable outcome, meaningful tradeoffs; business
  context only where it changes product decisions.
- **Scope and boundaries:** what this repo owns, what neighbours own, the few technologies or
  seams needed to locate work. Repo also hosts research/support/business work → say so, without
  forcing every request into a coding workflow.
- **Domain vocabulary:** recurring ambiguous terms, aliases and crucial distinctions, briefly,
  in the product's own language. Link shared terminology at its owner (e.g. ReplyPen terms in
  connected repos); define only local differences. No generic dictionary, renaming or
  model inventory; term count is not a target.
- **Verification:** actual commands and when they apply, fixtures/environment, observable
  success; local vs live checks; docs-only CI paths for doc changes. Preserve non-obvious
  safety and deployment constraints.
- **Routing and constraints:** a few task-relevant links and real invariants, each with its
  reason in a clause. An operational rule only when missing it invites a concrete mistake; no
  speculative blanket ban from one past incident.
- **Cut:** generic engineering advice, restated global instructions, task history, stale
  milestones, volatile numbers/inventories, copied trees/runbooks/skill content, exhaustive
  schema or implementation detail, rigid recipes. A new supporting file only when the detail has
  no home and earns its maintenance. Stay in scope; shorter is better only while decisions stay
  clear.

**Public output (hard rule):** stand on public evidence only; never copy private business facts,
internal samples, personal absolute paths or secrets from reference repos. Distill the pattern;
neutral examples only where they clarify a distinction.

## Check the result

Verify links (anchors, symlinks) from the entrypoint's actual location; no deployments or
expensive suites just to validate prose. Dry-run a representative change and an ambiguous
request: can a fresh agent find the owner, vocabulary and verification without needless rules?
After simplifying, check no real constraint was erased. Report consequential uncertainty or
conflicts; never fabricate certainty.
