# Cloud dry runs

Read the project's cloud runbook; publish through its normal workflow and record the full SHA.
Verify `git ls-remote origin refs/heads/<branch>`; use `create --wait --title 'Cloud dry run'`.
Use a fresh session after environment changes; warm sessions suffice for affected-check repeats.

`create --gate <SHA> '<checks>'` emits this wrapper for you; `send --gate <newer SHA> --branch <b>`
does the follow-up variant (fetch + `git checkout --detach`, so the warm session tests the fix).
Composing by hand, replace every placeholder in this prompt:

> Dry run on <repo/branch>, expected <full SHA>. Read <project runbook>.
> Print `git rev-parse HEAD`; gate all checks with `git merge-base --is-ancestor <full SHA> HEAD`.
> If missing or not an ancestor, stop and report both SHAs. Run <checks list>.
> No edits, commits, pushes or PRs, even if a stop hook asks. No production writes.
> Temporary diagnostics may use scratch files outside tracked source; never expose credentials.
> Finish background checks; return one concise report: pass/fail, timings, exact failures,
> actual tested SHA and <screenshots when needed>.

- Ask for one report per check: pass/fail table + exact excerpts + DX friction hit. The friction list
  is where the next fix comes from; a bare pass is not a report.
- Separate source defects from dependencies, network policy and test mistakes; fix locally and repeat affected checks.
- Proxy/CA failures: compare curl for the same URL; Chromium may need `HTTPS_PROXY`, localhost bypass and proxy CA trust. Isolated `ignoreHTTPSErrors` is diagnostic only; never weaken app TLS.
- Localhost proxy 405: try Chromium `--proxy-server` and `--proxy-bypass-list=localhost;127.0.0.1`; `<-loopback>` removes bypass. Mocked assets do not establish a pass.
- Use `domcontentloaded` plus bounded DOM/image/font waits; `networkidle` can hang on excluded analytics/maps. Report exclusions.
- Stop-hook “unpushed work” can be a false positive: empty `git log origin/<branch>..HEAD` needs no push; the dry-run prohibition wins.
- Update the canonical recovery runbook after network-domain, secret, setup-script or environment changes; record secret recovery locations, never values.
- Measure startup separately from optional provisioning. Stop diagnostic monitors; report limitations and the session URL.
