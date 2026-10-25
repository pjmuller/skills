# Permission ceiling: messaging a broader-mode thread

T3 refuses `t3_thread_send` (and every other cross-thread change) when the target's runtime or
interaction mode is broader than the **calling thread's current mode**: Auto → Full Access fails with
`runtime_mode_escalation_denied`. The server reads the caller's stored mode on each call
([upstream policy](https://github.com/pingdotgg/t3code/blob/main/docs/orchestration-v2/orchestrator-mcp-server.md#policy-and-idempotency)).
A send never changes the target's mode.

- **Model/account ≠ permission.** `t3_thread_configure` switches provider/model/options only; no MCP
  tool sets modes. The composer's permission picker applies on the user's next send in that thread.
- Auto is the app's default for threads the user creates; an agent's `t3_thread_launch` without `runtimeMode` inherits the caller's ([workers](workers.md#-t3_thread_launch)). The owner keeps its mode unless the user changes it.
- Never work around the denial: no duplicate thread just to get a lower mode, no `t3-relay` (its
  own OAuth ceiling is for scripts outside T3), no raw WebSocket/RPC, browser automation, state-DB
  writes or other credentials.

## Continue an existing broader-mode owner

1. **Preflight** before sending: `t3_thread_configuration` for yourself (no threadId) and the
   target. Equal or narrower target → send normally.
2. **Broader target → keep the intent.** Write the continuation exactly as it would have been
   sent (verbatim user text, separated new evidence, attachment paths, target id, chosen
   `clientRequestId`) to a brief file; mark it *not delivered*. Don't spawn a replacement.
3. **One user action.** A picker change only takes effect when the user next sends in *that*
   thread, so every option is a user send:
   - **A (default): user sends it in the owner.** Link `[title](t3-thread://v1/<id>)` and give the
     line to paste: `Read and execute /abs/continuation.md`. Owner keeps its mode. Done: never
     replay it from here.
   - **B: owner should run in Auto** (user's call): same as A, after switching the owner's picker
     to Auto. Its mode stays Auto from then on.
   - **C: routing thread in Full Access** (user's call, never your suggestion as default): user switches
     *this* thread's picker to Full Access and replies "go". It stays Full Access until the user
     switches back and sends here again; say so.
   - Claude thread whose mode changes (owner in B, routing thread in C) restarts its session and loses
     in-session background work ([t3code#16000](https://github.com/pingdotgg/t3code/issues/16000)):
     check for it first and warn.
4. **Retry once after C:** re-read both configurations, the owner's runs and `t3_queue_list`, then
   one `t3_thread_send` with the same `clientRequestId`. Lost answer = unknown delivery: read the
   owner before any retry.

Still denied after C → report the read-back modes; don't loop. Server-side fix proposed upstream ([t3code discussion 22975](https://github.com/pingdotgg/t3code/discussions/22975)):
a user-approved continuation request (Auto caller submits; the user approves that one delivery).
