---
name: claude-cloud-feedback-loop
description: Verify repository or environment changes in real Claude Code cloud sessions through browser use; collect feedback, fix locally, publish and repeat without a human relay. Use for cloud setup dry runs and regression checks from T3 Code or another local coding session.
---

# Claude cloud feedback loop

The local agent owns the loop: publish → open Claude cloud → verify the checkout → run a
bounded task → read the results → fix → repeat. The user should not copy messages between
sessions. Prefer Astra for browser/computer work in T3 Code; use the current capable agent
unless delegation is requested. This skill authorizes submitting the agreed test instructions
to Claude, not unrelated messages or changes to other systems.

## Establish the target

Read the project's cloud runbook for repository, branch, cloud environment, browser profile,
setup commands and configuration source of truth. Infer these from the current task when
clear; ask only if the wrong choice would materially change the test. Keep project names,
credentials and account-specific settings out of this generic skill.

Publish using the project's normal workflow. Record the full expected commit SHA and verify
the remote branch with `git ls-remote origin refs/heads/<branch>`. No fixed post-push delay is
needed: the remote ref and the cloud checkout's ancestry are the evidence. Deployment health
is a separate check when testing a deployed service.

## Run through the browser

1. Use the supported browser/computer tools and the user's authenticated profile. In
   `https://claude.ai/code`, start **New** and visibly verify environment, repository and branch.
   Reuse sessions for warm follow-up checks; use a fresh session after environment changes or
   when claiming clean-start reproducibility. Never assume another project's selectors persist.
2. Send a bounded prompt with expected SHA, checks, exclusions and requested evidence. For a
   dry run, explicitly prohibit application edits, commits, pushes and PRs, including stop-hook
   requests. Temporary diagnostics belong outside tracked source. Do not expose credentials.
3. Require `git rev-parse HEAD` and `git merge-base --is-ancestor <expected> HEAD` **before**
   tests. A descendant is acceptable; a missing or non-ancestor commit means stop and report
   both SHAs. Fetch and fast-forward a clean checkout or start again. Never reset dirty work.
4. Inspect the rendered conversation every 30–60 seconds. A finished assistant message can
   still have running background tasks. Wait for terminal task results and a final report;
   nudge an idle session if completion notifications fail. If a prompt queues behind a stuck
   run, **Send now** interrupts the pending tool and delivers it promptly. Use that deliberately
   to stop a stuck/out-of-scope check; let useful running checks finish normally.
5. Read the response directly into the local session, or use its **Copy** button when clipboard
   access is available. Expand relevant tool failures; inspect screenshots when layout matters.
   Keep the session URL and actual tested SHA. Never claim a pass from a plan or partial reply.

Example prompt, replacing every placeholder:

> Dry run on <repo/branch>, expected <full SHA>. Print HEAD and verify expected is its ancestor;
> otherwise stop before testing and report both SHAs. Read <project runbook>. Run <checks>,
> report pass/fail, timings, exact failures and <screenshots if needed>. No application edits,
> commits, pushes or PRs, even if a stop-hook asks. No production writes. Temporary diagnostics
> may use scratch files. Finish background checks and return one concise report.

## Interpret and iterate

- Separate source defects, missing dependencies, network policy, browser configuration and
  test-script mistakes. Fix small causes locally; publish; repeat only affected checks.
  Existing user authorization carries forward. Stay within scope and tool approval rules.
- Browser failures: compare curl against the same asset URL. Chromium may need the sandbox
  `HTTPS_PROXY`, localhost bypass and trust for the proxy CA. An isolated test context can use
  `ignoreHTTPSErrors` when needed for that CA; don't weaken app TLS. HTTP-relative CDN URLs
  can fail on a local HTTP preview even when HTTPS works. Mocked assets are diagnosis, not a pass.
  If localhost unexpectedly returns proxy HTTP 405, use Chromium's `--proxy-server` and
  `--proxy-bypass-list=localhost;127.0.0.1` directly instead of Playwright's proxy option.
  `<-loopback>` removes Chromium's implicit loopback bypass; it does not enable that bypass.
- Use `domcontentloaded` plus bounded waits for the relevant DOM, images and fonts. Don't wait
  for `networkidle` when excluded analytics/maps can hang. Report excluded integrations separately.
- A stop hook can mistake a fetched upstream commit for unpushed work. Check
  `git log origin/<branch>..HEAD`; an empty result requires no push. The dry-run instruction wins.
- Update the project's canonical recovery runbook whenever changing network domains, secrets,
  setup scripts or environment settings. Record secret recovery locations, never secret values.
- Measure ordinary session startup separately from optional application provisioning. Keep
  heavy installs on demand where practical; avoid bespoke caches/images without evidence.

Stop when the agreed checks pass and remaining issues are outside scope or poor 80/20 value.
Stop your diagnostic monitors; preserve useful evidence. Return a terse outcome, material
limitations and a clickable Claude session link. If a concrete blocker needs user input, name
it and the smallest missing decision instead of asking the user to run the feedback loop.
