# Replace a routing thread

Use when the user requests a reset/replacement; compaction alone does not request one.
A request to improve this playbook does not itself launch a replacement.

1. Review the current conversation once for explicit corrections and verified routing
   mistakes. Read existing rules first; keep only lessons useful to future requests.
   Update the owning private lookup/playbook; generic mechanics belong in shared skills.
   Merge duplicates, remove superseded rules, and omit task transcripts and private details.
   Follow `t3-route/corrections.md`; commit/push and verify before handing over.
2. Inventory unfinished **owned** work: delegated task IDs, approvals, queued deliveries
   and monitors. Finish/reconcile children here before retirement: their delivery remains
   attached to this thread. Do not assume launching a successor transfers ownership.
   Independent execution threads continue; do not replay their briefs or poll them unasked.
3. Launch once with `t3_thread_launch`, the wrapper's project, explicit workspace,
   model/effort and permitted runtime mode. Title: `<person> routing`, using the wrapper's
   name, never a shared hard-coded person. Brief only the wrapper/entrypoints, predecessor
   ID and necessary unresolved routing context. Initialize this router; do not route the
   initialization or import the full transcript as a backlog.
4. Retain returned ID; read the successor to verify initialization. Pin with
   `t3_thread_organize {action:"pin",threadId:"<new id>"}`. Rename if needed with
   `t3_thread_update {action:"rename",threadId:"<new id>",title:"<person> routing"}`.
   Inspect tool receipts; launch acceptance is not readiness. After a lost launch response,
   list threads before retrying. A pin/readiness failure leaves the predecessor available.
5. Once ready, pinned and no owned work remains, unpin the predecessor with
   `t3_thread_organize {action:"unpin",threadId:"<old id>"}`. Report the successor link,
   then self-settle as the last tool call per [settle-thread.md](settle-thread.md).
   The user's reset request authorizes this retirement; never retire on a docs-only request.

Native pin/rename/settle operations are present in the inspected T3 tool catalog
(2026-10-25). Check the live schema on each installation; if unsupported, report the
specific manual UI step. Never edit the live database to emulate a missing operation.
