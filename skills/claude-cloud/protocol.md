# Protocol notes (for changing `scripts/claude-cloud`)

Endpoints and bodies: `main`; headers and token refresh (with their why): `API.call`,
`API.credentials`. Not visible in code:

- Event payloads carry an internal worker session UUID: requests keep the outer `cse_…` ID.
- `config:auto-create-pr:off` is server-stamped (400 if supplied).
- No environment-edit endpoint ([browser-fallback.md](browser-fallback.md#editing-a-cloud-environment-allowlist-variables)).
- SSE, `/auth/refresh`, `/mark_read`, `/bridge`, `/triggers` exist in the CLI; unused, unverified.
