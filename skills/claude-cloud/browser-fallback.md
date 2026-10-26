# Browser fallback

Web UI only for permission prompts, uploads or rendered artifacts; else the CLI. Use the user's
authenticated browser profile and the project's cloud runbook. Authorizes agreed test prompts only,
not unrelated messages or system changes.

1. Open https://claude.ai/code → **New**; visibly verify environment, repository and branch.
   Fresh vs warm session: same rule as [dry-run.md](dry-run.md).
2. Send the hand-composed [dry-run prompt](dry-run.md) (full SHA, ancestry gate, exclusions).
   Missing/non-ancestor SHA: stop; fetch/fast-forward only a clean checkout or start again, never reset dirty work.
3. Check every 30–60 s until background tasks finish and a final report arrives; nudge idle sessions
   (completion notifications can go missing). **Send now** interrupts a pending tool: only for stuck/out-of-scope work.
4. Read the response (or **Copy**), expand relevant tool failures, inspect screenshots when layout matters.
5. Fix locally, publish, repeat affected checks. A plan or partial response is not a pass.
   Return outcome, limitations, tested SHA and clickable session URL.

## Editing a cloud environment (allowlist, variables)

No API endpoint: network domains, env vars and the setup script change in the web UI only. Verified 2026-09-22 in an authenticated Chrome profile:

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
the project's recovery runbook (domains, secrets, setup script): record where secrets are recovered from, never values.
