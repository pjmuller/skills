# Feedback round: implement a narrated product walkthrough in this thread

Someone clicks through the product saying what to change; the brief says execute here. Outcome:
changes shipped and verified live, a before/after report, and a handoff that lets the person with
design taste keep, tweak or revert each preference change.

> [!IMPORTANT]
> More than ~5 feedback items: never root-cause them one by one in the lead thread; fan out.

1. **Transcript** in feedback mode ([video-shrink-for-gemini](../video-shrink-for-gemini/SKILL.md)):
   numbered feedback items with timestamps and wall-clock. Check counts and claims against frames.
2. **Triage** each item: bug · quality (prompt/data) · taste · leave alone (the speaker said so) ·
   needs a decision. The speaker's diagnosis is a hypothesis: check the data first. (Round one: "sort
   by replies" was already true; the bold number on screen was the email count.)
3. **Fan out root cause** in parallel, read-only, one worker per cluster: native sub-agents for
   code mapping, `delegate_task` for opposite-model or long work. Brief: items + timestamps,
   transcript path, owning skill docs; ask for root cause (`file:line`), smallest change, risk,
   how to verify. Anything that "hangs", "is generic" or "is wrong" also
   gets a production read (rows, logs, read-only): round one's two real bugs were only visible
   there (a phone number in a learned sign-off made every sample draft fail a privacy check; a
   55 s cross-project relink ran inside an OAuth callback). An independent plan opinion runs
   alongside with the same evidence and no proposals; reconcile when both are back.
4. **BEFORE shots before any edit**: detached worktree at `origin/main`, seeded local app, fixed
   viewport, scenes via [ui-before-after](../ui-before-after/SKILL.md) (or the project's one-command
   shooter). Keep the before server running until the report is built: a state found later (a
   failure screen, a phone width) still needs its genuine before shot. Reproduce the speaker's state
   with synthetic look-alike data (long titles, realistic counts); never copy customer or production
   data into screenshots, scene files or tickets.
5. **Implement.** The lead owns shared files and the core changes. Heavy repetitive work (catalogues,
   icon/asset sourcing, copy sweeps) goes to cheaper workers with exclusive file ownership and a brief
   that fits their sandbox ([Codex sandbox](../t3-manage-thread/workers.md#codex-sandbox-limits)).
   Taste changes stay small, scoped (a modifier class, one template branch) and listed one per line
   in the project's design-deviation log, so each reverts alone. **Commit bug fixes locally before
   the first taste edit** (push both after review): splitting a mixed tree later means hand-stripping
   hunks from shared files. A worker in its own
   worktree commits there and the lead cherry-picks; an uncommitted diff re-applied with `git apply`
   fails as a whole on the first file the lead also touched.
6. **Verify.** Unit tests on the critical paths; the browser suite on unchanged `main` too, so
   pre-existing failures are not blamed on you; AFTER shots with the same scenes; one phone-width pass.
7. **Ship.** Opposite-model review; bug-fix and taste commits apart; deploy; check live.
8. **Side effects of the walk itself.** A walk on a shared box (staging) with a real mailbox or
   account can switch real processing on: drafts placed in a live inbox, a mailbox now watched twice.
   Read the box's rows for what the walk created, pause it at once, and offer the project's teardown
   (an account-removal tool, deleting a placed draft) as a decision: irreversible, so ask.
9. **Report.** Compact before/after inline (`compact.html` through the host's HTML renderer), the full
   report in `~/Downloads`, a ticket for the taste owner: per change the screen, bug vs preference,
   before/after, file and how to revert. Side effects you found in production (data moved, flows
   switched on) are decisions for the user, asked as such.

Kill only processes you started, by PID or port: a `pkill -f` pattern can hit another agent's server.
