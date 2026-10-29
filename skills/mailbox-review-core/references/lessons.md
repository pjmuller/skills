# Landing a lesson (after the operator's go)

Batch per target; status (proposed / go / landed) lives in the report's lessons section, where the
next run reads it.

- **Brain:** one brain thread per run (`t3_thread_launch` in the wrapper's brain checkout), started
  at the first go, later batches via `t3_thread_send`, keyed to the run ids it fixes. It follows the
  brain's `AGENTS.md` and repo-local brain-dev skills (`local-brain-work` first) and proves the rule
  on the real case via `brain-simulate`/`brain-ask` against a `dev/*` ref (simulation only, never a
  rerun of the customer thread): before wrong, after right; then `brain-publish`. The go on that
  exact text is the publish go; a failed proof or materially different text returns to the operator
  with the simulated before/after.
  Proof commands, from the brain checkout ([brain-ask](https://github.com/replypen/replypen-brain-skills/blob/main/skills/brain-ask/SKILL.md)):
  `rp ask --replay-run <run> --brain-ref dev/<branch>` reruns the real email/chat case side-effect free
  and diffs it with the original (`--tenant-brain-ref` for a tenant overlay, `--mirror-ref <repo>=dev/<branch>`
  for a mirrored repo). Not replayable (e.g. an app-triggered analysis run) → the same `rp ask --simulation`
  question on `main` and on the dev ref, compared; the wrapper names its recipe.
  Brain-dev skills live in the brain checkout (`.agents/skills/`); missing → run
  `replypen-brain-skills/install.sh` inside it. Runs commit `journal/` to the brain's `main` all
  day: edit in a worktree and let `brain-publish` reconcile.
- **Help article:** the wrapper's edit and publish path, then sync ReplyPen's KB and verify live.
- **Product code:** its own `t3_thread_launch` in the owning repo, a PR per
  [Shipping a found fix](go-deep.md#shipping-a-found-fix).
- **Fix facts at their source.** A product fact the brain reads from a mirrored repo (wrapper lists
  the mirrors) is fixed in that repo's docs, not copied into the brain.
