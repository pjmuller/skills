# Browser fallback

Use the web UI for permission prompts, uploads or rendered artifacts; otherwise use the CLI.
Use supported browser tools and the user's authenticated profile; read the project's cloud runbook.
This workflow authorizes agreed test prompts only, not unrelated messages or system changes.

1. Open https://claude.ai/code → **New**; visibly verify environment, repository and branch.
   Use a fresh session after environment changes; reuse one for warm follow-up checks.
2. Send the bounded [dry-run prompt](dry-run.md), including full SHA, ancestry gate and exclusions.
   Missing/non-ancestor SHA: stop; fetch/fast-forward only a clean checkout or start again, never reset dirty work.
3. Inspect the conversation every 30–60 seconds; wait for terminal background-task results and a final report.
   Nudge idle sessions with missing completion notifications. **Send now** interrupts a pending tool;
   use deliberately for stuck/out-of-scope work and let useful checks finish.
4. Read the response directly or use **Copy** if clipboard access exists; expand relevant tool failures.
   Inspect screenshots/rendered artifacts when layout matters. Keep the session URL and tested SHA.
5. Fix locally, publish and repeat affected checks. A plan or partial response is not a pass.
   Stop diagnostic monitors and return the outcome, limitations and clickable session URL.
