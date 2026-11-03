# Impact-driven local QA

Goal: before a human merges, every runtime path an upgrade can reach has run for real at least once,
on base and branch, with the same inputs. Tests cover logic; this covers the edges they stub.

## 1. Map (10 minutes, before testing)

Per selected package: who imports it (`grep` our code), who pulls it in (`uv tree --invert --package X`,
`pnpm why X`, `bundle exec gem dependency -R X`, `go mod why X`), and which user-visible flow sits
behind each call site (an upload, a page, a job, a partner call, a send). Packages that only reach
tests or dev tools stop here. Depth follows risk: majors, untrusted input, network/TLS, the DB driver.

## 2. Exercise each edge for real (safe environment only)

| Edge the upgrade touches | Real local exercise |
| --- | --- |
| Runtime, base image, server, framework, templating | Build the **production image**; boot web + worker against a throwaway DB (`--tmpfs`, production's engine major); migrate; seed the synthetic tenant through the project's own seed path; fetch real pages via signed links. Diff base vs branch responses, masking timestamps and random ids. |
| File / image / document parsing | Corpus = real files already in the repo + generated edge cases (EXIF rotation, colour modes, 16-bit, animated, truncated, oversize, garbage). Feed them through **our** functions, not the library directly; dump outputs losslessly; diff pixels/bytes and compare which inputs are refused. |
| Outbound HTTP to a partner | The partner's staging or sandbox tier (the wrapper's e2e). Partner flakes: rerun the extra failures on base and branch before calling one ours. |
| Cloud SDK (AWS, GCP, …) | Read-only calls with the project's profile (identity, `describe`/`get`): exercises transport, TLS and signing without writes. |
| Send-only SaaS SDK (analytics, error tracking, mail API) | Point its host at a local capture server; assert the request arrives and parses. Never the real endpoint with real data. |
| DB driver / ORM / queue | Full suite on a throwaway container of production's engine major; boot a worker and see it poll and schedule. |
| Asset / build tooling | Rebuild; compare output hashes. Screenshots only when the output changed. |

## 3. Read the result

- Identical on both = evidence. A difference = a finding to explain in the PR (expected per release
  notes, or a regression). Failing on both = your setup or pre-existing, not the upgrade.
- A 500 on both sides is usually the synthetic setup (missing secret, plaintext where the app
  expects encrypted data): fix the seed, don't skip the page.
- Scripts that worked go into the wrapper's skill folder so next month's run starts from them.
- Throwaway containers, networks, images and worktrees are removed at the end.
