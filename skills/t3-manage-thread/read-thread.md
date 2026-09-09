# Reading a thread's transcript (t3-read-thread)

T3 has no agent-facing "read thread" API; every message is projected into T3's local
SQLite store (`~/.t3/userdata/state.sqlite`, table `projection_thread_messages`). The helper
copies the store (+ WAL) to a temp dir before reading and deletes the copy on exit — the
running server is never locked and nothing is written back. Keep that invariant if you extend it.

```bash
t3-read-thread THREAD_ID              # markdown transcript (long messages truncated)
t3-read-thread THREAD_ID --outline    # one line per message: #index, role, time, size, first line
t3-read-thread THREAD_ID --msg 3,7-9,-1   # only those messages, full text
```

Everything else (`--last`, `--role`, `--full`, `--json`, `--list --project-root`): `--help`.

- **Progressive disclosure on huge threads**: `--outline` first, then `--msg N` for the few messages
  that matter; `--full` only as a last resort. `--json` composes with `jq` for anything else.
- The projection holds only the visible user/assistant messages — **not** tool calls or
  assistant reasoning. Don't conclude "the worker did nothing" from a quiet transcript.
- Hand-rolled queries: projection columns are **snake_case** (`thread_id`, `settled_at`,
  `settled_override`, `title`) — thread rows live in `projection_threads`, turn state in
  `projection_turns` (`state = 'completed'` once a turn goes idle).

**Read before pinging**: check whether a worker already did the thing, or read the brief
another agent gave a thread you were asked to extend.
