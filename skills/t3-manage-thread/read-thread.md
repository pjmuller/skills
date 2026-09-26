# Reading a thread's transcript (t3-read-thread)

Flags and examples: `t3-read-thread --help`. T3 has no agent-facing read API, so
the helper reads the SQLite projection (`$T3CODE_HOME/userdata/state.sqlite`,
`projection_thread_messages`) from a temp copy (+ WAL): the running server is
never locked and nothing is written back. Keep that invariant if you extend it.

- **Huge threads**: `--outline` or `--grep REGEX` first, then `--msg N` for the
  few that matter; `--full` last. Indices are positions in the role-filtered list
  (`--role user` renumbers), so take them from the same filter you read with.
- `--json` includes the parsed `model_selection`: attest the provider, model and
  effort a spawn actually got instead of trusting the command.
- The projection holds only visible user/assistant messages, **not** tool calls
  or reasoning. A quiet transcript doesn't mean the worker did nothing.
- Hand-rolled queries: columns are snake_case; thread rows in
  `projection_threads` (`settled_at`, `settled_override`, `title`), turn state in
  `projection_turns` (`state = 'completed'` once idle).

**Read before pinging**: check whether a worker already did the thing, or read
the brief another agent gave a thread you were asked to extend.
