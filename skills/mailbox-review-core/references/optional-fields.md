# Optional finding fields

Read by the reviewer only when emitting one of these; see [reviewer.md](reviewer.md) for the base schema.

When a draft is plainly wrong and a small brain change (policy line, script output, routing hint, KB article) would clearly have steered the run to the right answer, add `brain_proposal`: `{"target": "brain file or article", "change": "one-line change", "why": "which run it fixes and why", "detail": "optional private path to the exact diff"}`. Read the current brain file first; if it already says the right thing, it is a model/host issue, not a proposal. Write the exact diff to a private file next to your finding and point `detail` at it. Proposals render in their own section, also for non-actionable threads; nothing is applied.

Only for a demonstrably incorrect **unmodified unsent AI draft**, include `replacement_body` with the complete plain-text body. Match the latest run's `draft_markdown` byte-for-byte to exactly one Gmail draft. Preserve existing quotes verbatim; keep the correction narrow. If the draft was human-edited, another reply exists, authorship is uncertain, or the thread/run changed, recommend the owner's next action instead. The coordinator validates and performs any authorized correction separately.
