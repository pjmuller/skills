# Role adaptation

Keep one core. Add two or three role lines, preserving the person's repo map,
tooling and working preferences. Deliver the merged prompt; installation should
save, link and verify it, not repeat the design or invent a separate inventory.

For a product owner: “Handle Git, tooling and verification for me. Bring me
product tradeoffs and working results. Research stays research; code gets the
same engineering bar as a developer's.”

For a developer: preserve signing, worktrees and existing PR follow-ups. Explain
technical tradeoffs when useful; don't turn their job title into more ceremony.

Both: agents pull, commit/push and integrate promptly. Small low-risk work can
go directly to the normal development/staging branch where repo rules permit.
Meaningful regression risk warrants a short-lived PR and independent review.
Judge behavior and blast radius, not just line count: a standalone visualization
may need little process, while a small shared UI change can warrant review.
Required repository approvals still apply; never bypass them. Production
promotion follows the repo's release authorization, not “try it and see”.
