---
name: data-enrichment
description: "Use when a task needs external data the repo has no key for: geocode an address, read a public page/PDF a plain fetch can't, find or verify a work email, enrich a person/company, social posts, SERP/SEO, reviews, image/video/voice generation. Paid per call."
---

# Data enrichment

Three helpers, PEP 723 scripts run with `uv run` (paths below relative to this skill; consumer repos
carry it at `.agents/skills/data-enrichment/`). `scripts/install --check` verifies them (and the treg
balance when a token is set). Offline tests: `uv run --with pytest pytest skills/data-enrichment -q`.

| Need | Command | Read first |
| --- | --- | --- |
| Address → coordinates | `uv run scripts/geocode.py 'ADDRESS' [--provider geopunt]` | [geocoding.md](references/geocoding.md): **Mapbox results are never stored** |
| Public page/PDF → Markdown | `uv run scripts/capture_url.py URL --out DIR` (Python: `capture(url, out)`) | [capture.md](references/capture.md): cache, paid fallback, exit codes |
| Any third-party API job | `uv run scripts/treg.py search\|get\|call\|balance` | this page |

Paid paths need `TREG_TOKEN` in the repo's mise env file (`~/.config/mise-env/<org>/<repo>.env`),
plus `TREG_ORG=<team-slug>` for a personal identity token (team API keys embed the team). Tokens:
treg.to dashboard.

## treg.to catalog

[treg](https://treg.to): ~3,800 endpoints from ~100 providers (people/company enrichment, email
verification, social on X/LinkedIn/Instagram/TikTok/YouTube/Reddit, SERP and SEO, store reviews,
OAuth'd Search Console/GA4/Ads, image/video/voice generation, market and scholarly data) behind one
token and one prepaid balance.

```sh
TREG() { uv run .agents/skills/data-enrichment/scripts/treg.py "$@"; }
TREG search "find work email"          # free, no token: id | price | observed success | summary
TREG get treg.people.email.find        # free: parameters, price note, routed providers
TREG call treg.people.email.find --data '{"full_name":"Jane Doe","domain":"example.com"}'
```

`call` prints the answer on stdout, `status · charged · served by · call id` on stderr. Raw HTTP:
`https://treg.to/call/<id>` with `X-Treg-Token` (and `X-Treg-Org`). `treg.<capability>` ids are
routed (cheapest provider first, the one that answered is named); other ids are one provider.

## Money and data rules

- **Look before you call**: `get <id>` shows the unit. `per_result` bills per row (`limit` sets the
  bill); a routed call may also pay providers that billed a miss. The helper caps routed calls at
  $0.05 (`--max-cost`; treg's default is $1). The real charge is `charged` (`X-Treg-Cost-Micro`).
- **Never repeat a paid lookup**: repeats bill too. Store results in the repo; retry a lost answer
  with the same `--idempotency-key`. Never call from tests or uncapped loops.
- **A 200 is not a result**: scrapers return homepages, paywalls and error pages with 200; check
  the body is about what you asked.
- **A found email is a guess**: `treg.people.email.verify` before outreach (`invalid` = dead,
  `accept_all` = risky). Never mail an address no provider returned.
- **Failures**: 429/5xx/timeout are not billed, try the next provider; 4xx = fix your parameters,
  don't shop it around; 402 = balance empty (top up in the dashboard).
- **Personal data**: legitimate business purpose only (EU = GDPR); results in the repo, not chat.
- Generation is async (minutes) and result URLs expire: read that llms.txt section first.

## Going deeper

- Platforms: `curl -s https://treg.to/catalog/platforms`; one platform as JSON:
  `/catalog/platforms/<slug>` (the `.md` variants llms.txt promises 404, checked 2026-10-10).
- One provider: `https://treg.to/tools/<provider>`; recipes: [use cases](https://treg.to/use-cases),
  [workflows](https://treg.to/workflows).
- Routing headers, async, idempotency, errors, own keys/OAuth, MCP: [llms.txt](https://treg.to/llms.txt)
  (long: grep it). Source: [superdesigndev/treg](https://github.com/superdesigndev/treg).
- Missing capability: `POST https://treg.to/tool-requests {"capability": "<need>"}`.

The official `treg` CLI/MCP use a machine login; this skill uses the env token so worktrees, cloud
sandboxes and colleagues behave the same.
