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

## Editing a cloud environment (allowlist, variables)

The API has no environment-edit endpoint: network domains, env vars and the setup script are
changed in the web UI only, and the platform applies them to **new** sessions. Recipe verified
2026-09-22 in an authenticated Chrome profile:

1. Open https://claude.ai/code in the Chrome profile that owns the environment (account name shows
   bottom-left). Above the composer, click the cloud-icon pill with the environment name.
2. Click **Cloud** in the popup; the submenu lists the environments. Focus the target with Right Arrow,
   then Right Arrow again: **Edit cloud environment** opens (the item's accessible name ends in
   "environment settings, right arrow"; clicking the name only selects it).
3. **Network access** = Custom; **Allowed domains** below it is a plain multiline textarea, one
   domain per line, no chips. It shows ~4 lines and scrolls internally; wildcards like `*.example.com`
   work. Append the agreed line, keep the rest byte-identical, click **Save changes**: the modal closes
   asynchronously, no confirm dialog or toast. Reopen to verify. Inspection only: **Cancel**.
4. Gotcha: **Environment variables sit on the same modal, unmasked, also in the accessibility
   tree.** Never dump the full modal snapshot or full-page screenshots: read only the Allowed-domains
   locator and crop screenshots to the network section.
5. Changes apply to new sessions only (modal notice); verify with a fresh `create --gate` session.

Change only the agreed line; never read env-var values aloud or into a transcript. Afterwards update
the project's recovery runbook.
