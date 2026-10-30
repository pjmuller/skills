# Replace a routing thread

Only on the user's reset/replacement request; compaction alone isn't one, nor is a request to improve
this playbook. The router *suggests* one at `t3-context` status `reset` (50 user messages) or on
drift ([t3-route](../t3-route/SKILL.md#report-and-learn)) and runs step 1 then, even without a
reset; at status `lessons` it runs step 1 silently.

1. **Lessons**: from stored history, not memory (compaction drops detail): `t3_thread_read` the user
   messages since the last lessons commit (its message names `<thread short id> through position <n>`;
   none for this thread → from its start),
   for explicit corrections and verified routing mistakes. Read existing rules first; update the owning private lookup/playbook (generic mechanics → shared
   skills), merging duplicates and removing superseded rules; no transcripts or private details.
   Follow [t3-route corrections](../t3-route/corrections.md); commit/push (message ends `routing lessons:
   <thread short id> through position <n>`, also when nothing changed: `--allow-empty`) and verify before handing over.
2. **Owned work**: inventory delegated task IDs, approvals, queued deliveries and monitors; finish or
   reconcile them here (their delivery stays attached to this thread; a successor doesn't inherit
   ownership). Independent execution threads continue: don't replay their briefs or poll them unasked.
3. **Launch once** (`t3_thread_launch`): the wrapper's project, explicit workspace, model/effort and
   runtime mode. Title `🧭 <person> routing` with the wrapper's name (`t3-mail-link` keys on 🧭 so
   routers never own mail cases). Brief only the user's designation verbatim ("<person> designates
   this thread as their router: each new task here is their request for a new T3 thread"), the
   wrapper and its reading list, the predecessor ID and necessary unresolved routing context. The successor reads that list once, in batches under its tool-output cap (Codex ≈10k tokens), and initializes itself (no setup routing, backlog,
   historical launches or monitoring of old workers), confirms readiness and waits.
4. **Verify**: read the successor (launch acceptance is not readiness), then
   `t3_thread_organize {action:"pin",threadId:"<new id>"}`; rename if needed with
   `t3_thread_update {action:"rename",threadId,title}`. Lost launch response → list threads before
   retrying. A pin/readiness failure leaves the predecessor in place.
5. **Retire**: once ready, pinned and no owned work remains, `t3_thread_organize {action:"unpin"}` the
   predecessor, report the successor link, self-settle as the last tool call
   ([settle-thread.md](settle-thread.md)). The reset request authorizes this; a docs-only request never does.

Pin/rename/settle were in the T3 tool catalog on 2026-10-25; check the live schema. Unsupported → report
the manual UI step; never edit the live database to emulate it.
