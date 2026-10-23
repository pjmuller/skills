# Architecture audit — pjmuller/skills — 2026-10-23
First audit. Window since 10-09 (~209 commits; hot: t3-* scripts, gitsync, bitwarden, workspace cores).
Method: two independent model audits → lead verification → implementation → opposite-model review (3 rounds).

## Shipped (`ce06d7a`)
- CI: full suite on every PR and push to main (code-only pushes ran no tests before); macOS-only tests skip on Linux (CI was red).
- Suite `-n 4`: 93 s → 29 s (signal test isolated in a subprocess).
- t3-purge-threads: searches every provider home's transcripts; tests isolated from the real HOME.
- t3-schedule: pending launches survive midnight and are retired only by the relay's verdict; per-job fire lock; atomic state writes;
  an unreadable marker isolates that job and never re-fires; the pending proof is kept until the fire is recorded.
- gitsync: one checked porcelain reader (a failed git read is "unverified", never "landed"); random claim ids instead of second-resolution ones.
- bitwarden: one absolute broker deadline, so "nothing released" is always true.
- google-workspace-core: absolute link that works in vendored copies.

## Open
Broker vault identity (data dir / server URL) is taken from the request; sealing it per vault at enrolment is a security-design change.
