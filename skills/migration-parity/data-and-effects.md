# Data and effect comparisons

## Trustworthy baseline

Pin reference code/version and fixture provenance, including schema/settings, identity/permissions and capture boundary. Reuse immutable captures; refresh explicitly. A reference that imports the new implementation cannot independently verify that implementation.

Live data changes: distinguish a mapper tested against a frozen schema from an integration tested against today's schema. Record partial captures as partial, including failed cases. Do not silently make transient errors the expected result. Check representative fixtures can actually authenticate and exercise the intended behavior.

## Narrow, explainable diffs

Compare values, types and effects across relevant outputs: responses, files/streams, exit codes and operational logs. Preserve null versus missing, numeric precision, array order and multiplicity unless the contract says otherwise. For cross-runtime representation differences (e.g. floating-point rounding), define any acceptable tolerance at the contract level and scope it like other normalization rules. Object-key order is usually irrelevant to JSON, but may control a UI consuming it; test that consumer separately.

Normalize only proven nondeterminism. Every rule needs a scoped path, reason and a nearby semantic difference that must still fail. Example:

| Difference | Treatment |
| --- | --- |
| Generated IDs for two test-created records | Map only the IDs proven paired by the execution ledger, including their references |
| Existing customer record IDs | Compare literally |
| Creation timestamps | Ignore only generated fields; still compare business dates |
| Set-valued rights | Compare membership, preserving duplicates if meaningful |
| File upload | Compare bytes/hash, metadata, placement and ownership; URL equality alone is insufficient |

Separate variable identity from business content; avoid deleting whole nested objects to make a comparison pass. Repeated old runs can reveal nondeterminism. Document the allowed outcome or deliberate stabilization rather than claiming exact equality.

## Replay versus real execution

Offline replay should receive inputs, not expected answers. Remove ambient credentials and use dependency seams or a suitable sandbox to prevent effects; instrument actual mutation boundaries when feasible. Self-reported zero counters alone are not isolation. Include errors, malformed inputs, asynchronous behavior and rerun/resume after partial failure where relevant. Compare throughput as well as correctness for batch systems.

Real execution requires authorized fixtures and independently checked targets, including nested/update/file targets. Prevent notifications, payments and unrelated jobs unless explicitly in scope. Isolation must hold at effect boundaries, not just in fixture labels.

For non-idempotent operations, persist intent before execution and journal created resources as IDs become known. After a timeout/disconnect, reconcile before retrying. Use separate equivalent old/new records for update comparisons; sequential edits to the same record contaminate starting state. Verify downstream values, attachment retention/removal, job completion and unintended changes—not merely a successful return status.

Clean up only resources proven created by this run, within the authorized scope. Preserve any required comparison evidence first. Report leftovers explicitly; do not turn uncertain ownership into a cleanup delete.

## Evidence reports

Reports should bind code/deployed version, input/schema fingerprint, environment, time and completeness. Keep sensitive captures private; commit sanitized summaries and reusable tooling only.
