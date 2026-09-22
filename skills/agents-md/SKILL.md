---
name: agents-md
description: "Create, simplify or prune agent entrypoints: a repository's AGENTS.md / canonical CLAUDE.md, or the global cross-project file (~/.claude/CLAUDE.md, ~/.codex/AGENTS.md), including merging the shared global template into someone's existing file. Use for agent onboarding, project context, domain taxonomy, trimming bloated prompts; not general documentation rewrites."
---

# Agent entrypoints

Give a capable agent the context that changes its decisions: what this project is
for, who depends on it, where responsibility ends, and how to verify its work.
Explain why and the desired outcome; leave implementation choices open unless a
real constraint or concrete verification requirement makes precision necessary.

This file covers a repository's entrypoint. The user-level file loaded in every
repo (write, prune, merge the [template](global-template.md), port improvements)
has its own economics: [global.md](global.md). Handoffs between people, agents
and roles (relay prompt, dev → non-technical, bug report → dev): [handoff.md](handoff.md).

Register this skill repo-locally in the personal setup repository for initial
global-prompt setup and periodic pruning, template sync and machine-wide prompt
maintenance. If a project should discover it for its own entrypoint or handoffs,
register it explicitly in that project too. The bundled files are reusable
templates and procedures; the person's live prompt stays outside this replaceable
skill installation.

## Ground it

Read the existing entrypoint, applicable parent instructions, and linked skills
or glossaries. Resolve symlinks and forwarding files before choosing the canonical
file to edit; preserve the repository's discovery arrangement and unrelated edits.
Inspect source, manifests and test/CI entrypoints to check claims. Existing prose
is evidence, not proof: resolve stale or conflicting claims against current
behavior and explicit intent. Do not invent product strategy when evidence is absent.

## Choose what earns space

These are lenses, not a template or heading quota. Omit what adds no decision value.

- **Intent and users:** the problem, audience, valuable outcome and meaningful
  tradeoffs. Include business context only where it changes product decisions.
- **Scope and boundaries:** what this repo owns, what neighboring systems own,
  and the few technologies or architectural seams needed to locate work. If it
  also hosts research/support/business work, clarify that scope without forcing
  every request into a coding workflow. Link maintained maps instead of copying trees.
- **Domain vocabulary:** recurring ambiguous terms, useful aliases and crucial
  distinctions, briefly defined. Prefer the product's existing language. Link
  shared terminology at its owner, especially Rootcause terms in connected repos;
  define only local differences here. Do not make a generic dictionary, rename
  concepts, or enumerate every model. Term count is not a target.
- **Verification:** actual commands and when they apply, required fixtures or
  environment, and observable success. Distinguish local checks from live checks;
  use existing docs-only CI paths for documentation changes. Link longer test or
  release runbooks. Preserve non-obvious safety and deployment constraints.
- **Routing and constraints:** a few task-relevant links and real invariants with
  their reasons. Include an operational rule only when missing it invites a
  concrete mistake; do not turn a past incident into a speculative blanket ban.

## Simplify as well as create

Keep the project's distinctive intent and verified constraints. Remove generic
engineering advice, restated global instructions, task history, stale milestones,
volatile numbers/inventories, exhaustive schema or implementation detail, rigid
how-to recipes, and duplicated skill/runbook content. Replace useful detail with
a link to its maintained owner; create supporting files only when that detail
has no suitable home and earns the maintenance cost. Avoid broad rewrites outside
the requested scope. Shorter is better only while the decisions remain clear.

Public output must stand on public evidence: never copy private business facts,
internal samples, personal absolute paths or secrets from reference repositories.
Distill the pattern; use neutral examples only when they clarify a distinction.

## Check the result

Verify definitions against their source, commands against existing configuration,
and links from the entrypoint's actual location, including anchors and symlinks.
Do not run deployments or expensive app suites merely to validate prose.
Mentally try a representative change and an ambiguous request: can a fresh agent
identify the right owner, vocabulary and verification without unnecessary rules?
For simplification, check that removing detail did not erase a real constraint.
Report consequential uncertainty or conflicts instead of fabricating certainty.
