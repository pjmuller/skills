---
name: migration-parity
description: "Use while porting, rewriting or replatforming a working system (or a major framework upgrade) that must keep behaving like the old one (\"port this to Go\", \"prove the new API matches\", \"parity check\", shadow run, cutover plan), including long autonomous migrations. Not greenfield or schema-only migrations."
---

# Migration parity

Register repo-locally, only while a migration is active (globally it would load everywhere).

The working system is the executable reference: preserve outcomes users depend on; name intentional changes explicitly. Scale to the risk: a small migration may need a few fixtures, not a harness.

## Establish the working agreement

From the brief and repo context:
- **Target and stop line:** what ships, where, and what remains untouched.
- **Authority:** permitted environments, identities, reads/writes, deployments and cleanup. A skill grants no additional permission.
- **Acceptance:** behavior that must match, acceptable changes, operational needs (latency, jobs, integrations), and evidence required to finish.

Resolve missing high-impact decisions early; decide reversible details yourself and keep working while an answer is pending. Keep the agreement short and persistent.

## Prove one complete path early

Pick a representative, demanding workflow spanning the real boundaries (e.g. create a record with attachments and related data, reopen/edit it, verify persisted results), including failure and authorization behavior.

Before broad implementation: valid fixtures, permissions and an independent old-system baseline. Make that one path work through the actual interface and downstream effects, then expand across **different behaviors**, not sample counts. Add small reproducible helpers only where repeated manual work or risky mutations justify them.

Where practical, shadow-run old and new against the same real inputs with effects disabled or redirected; [verify isolation](data-and-effects.md#replay-versus-real-execution) before replaying traffic.

## Compare at the right layers

- [Data and effects](data-and-effects.md): JSON, database state, APIs, jobs and external mutations.
- [User workflows](user-workflows.md): browser/UI, rendering, interaction, edit mode and persistence.

Keep code parity against frozen inputs separate from compatibility with changing live dependencies. Label evidence offline, mocked, read-only live, or real mutation. A passing lower layer doesn't prove the next.

Classify every material difference as **defect**, **input/environment drift**, **permitted change** or **unresolved**, with evidence; never turn unexplained differences into passes via broader ignore rules. A behavior or stored-data change is permitted only within the agreed acceptance, else propose it and keep it unresolved, including fixes to legacy bugs consumers may depend on. Never silently call improvements parity.

## Sustain autonomous work

Keep one compact checkpoint (objective/boundaries, source and deployed versions, fixture/evidence locations, decisions, open risks, next action, resources to clean up; secrets elsewhere), refreshed at milestones so another agent can resume without the conversation.

Parallelize once seams are clear. Each worker gets an outcome, owned files/surface, input/output examples, boundaries and verification duty. Version shared contracts and fixtures before fan-out; one owner per contract, recheck affected workers when it changes. Integration and deployment ownership explicit. Review risky contracts early, implementations at stable integrated milestones. Verify worker claims against artifacts and the integrated system.

Ship incrementally within authorization, checking the **deployed version**'s behavior. Measure representative latency/resource use early; investigate regressions before adding infrastructure or caches.

## Finish with evidence, not momentum

Report what matched, deliberate deviations, remaining gaps, [human testing priorities](user-workflows.md#handoff-and-future-diagnosis) and links to try. Reconcile test mutations ([cleanup rules](data-and-effects.md#replay-versus-real-execution)); stop temporary processes.

Cutover and retirement are separate steps: find remaining callers, background jobs, stored links and shared data before removing the old system; record rollback limits once the new one accepts writes. **Stop at the agreed line: never infer permission to switch traffic or decommission infrastructure.**
