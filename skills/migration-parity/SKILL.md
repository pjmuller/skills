---
name: migration-parity
description: Verify old-versus-new behavior during rewrites, ports, replatforming or major framework upgrades, including long-running autonomous projects. Use when a working reference exists; not for greenfield development or schema-only migrations.
---

# Migration parity

Use the working system as an executable reference. Preserve outcomes users depend on; identify intentional changes explicitly. Scale this guidance to the risk: a small migration may need a few fixtures, not a new harness.

## Establish the working agreement

Extract from the user's brief and repository context:
- **Target and stop line:** what ships, where, and what remains untouched.
- **Authority:** permitted environments, identities, reads/writes, deployments and cleanup. A skill grants no additional permission.
- **Acceptance:** behavior that must match, acceptable changes, operational needs (latency, jobs, integrations), and evidence required to finish.

Resolve missing high-impact decisions early. Decide reversible implementation details autonomously; continue independent work while a necessary answer is pending. Keep the agreement short and persistent.

## Prove one complete path early

Choose a representative, demanding workflow spanning the real boundaries. For example: create a record with attachments and related data, reopen/edit it, then verify persisted results. Include failure and authorization behavior where relevant.

Establish valid fixtures, permissions and an independent old-system baseline before broad implementation. First make one path work through the actual interface and downstream effects. Then expand across **different behaviors**, not arbitrary sample counts. Use existing tools; add small reproducible helpers where repeated manual work or risky mutations justify them.

Where practical, shadow-run old and new against the same real inputs with effects disabled or redirected to isolated targets. Verify that isolation before replaying traffic.

## Compare at the right layers

- [Data and effects](data-and-effects.md): JSON, database state, APIs, jobs and external mutations.
- [User workflows](user-workflows.md): browser/UI, rendering, interaction, edit mode and persistence.

Keep code parity against frozen inputs separate from compatibility with changing live dependencies. Label evidence as offline, mocked, read-only live, or real mutation. A passing lower layer does not prove the next one.

Classify every material difference: **defect**, **input/environment drift**, **permitted change**, or **unresolved**. Classification needs evidence; unexplained differences never become passes through broader ignore rules. A behavior or stored-data change is permitted only within the agreed acceptance; otherwise propose it and keep it unresolved. This includes fixes to legacy bugs that consumers may depend on. Do not silently call improvements parity.

## Sustain autonomous work

Keep one compact checkpoint: objective/boundaries, current source and deployed versions, fixture/evidence locations, decisions, open risks, next action and outstanding resources to clean up. Store secrets separately. Refresh it at milestones so another agent can resume without replaying the conversation.

Parallelize once seams are clear. Give each worker an outcome, owned files/surface, input/output examples, boundaries and verification responsibility. Version shared contracts and example fixtures before fan-out; give contract changes one owner and recheck affected workers when they change. Keep integration and deployment ownership explicit. Review risky contracts early, then consolidate implementation reviews at stable integrated milestones rather than every worker amendment. Verify worker claims against artifacts and the integrated system.

Ship incrementally within authorization, checking the **deployed version** and its behavior. Measure representative latency/resource use early; investigate regressions before adding infrastructure or cache complexity.

## Finish with evidence, not momentum

Report what matched, deliberate deviations, remaining gaps, human testing priorities and links to try. Reconcile test mutations and stop temporary processes. 

Treat cutover and retirement separately: identify remaining callers, background jobs, stored links and shared data before removing the old system. Record rollback limitations once the new system accepts writes. Reach the agreed stop line; do not infer permission to switch traffic or decommission infrastructure.
