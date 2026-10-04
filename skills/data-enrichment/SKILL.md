---
name: data-enrichment
description: Use for public page/PDF to Markdown (free Jina, then treg/Olostep), or external/live data the repo has no API key for - email verification, people/companies, social posts/profiles, SERP/SEO, reviews, or image/video/voice generation through treg.to.
---

# Data enrichment (treg.to)

[treg](https://treg.to) is a catalog of ~3,800 third-party endpoints across ~100 providers behind
one token and one prepaid balance: no provider signup, no subscription. For catalog lookups,
search the job, read the price, call it. Public pages use the capture helper below.

Needs `TREG_TOKEN` in the repo's mise env file (`~/.config/mise-env/<org>/<repo>.env`), plus
`TREG_ORG=<team-slug>` when the token is a personal identity token rather than a team API key.
Tokens: treg.to dashboard. `scripts/install --check` verifies helpers; with a token, also balance.

## Public page or PDF → Markdown

Use **Jina first → pinned `olostep.web.scrape` through treg** on failure:
`uv run .agents/skills/data-enrichment/scripts/capture_url.py URL --out DIR`.
Jina needs no token; paid fallback needs the env above. Python callers use `capture(url, out)`.

One page, hosted providers, no browser. Inline links stay; a separate link list unions inline and
provider links. Raw JSON (including available HTML), receipts, `page.md` and `capture.json` survive
validation. Transport/origin status, provider, charges and call IDs remain separate; missing status
or final URL stays unknown (`reported_url` may only echo the request). Check coverage yourself.

`DIR` is a durable cache: matching completed capture reuses it; failed/pending/mismatched output
refuses. A new directory requests fresh capture. UUID idempotency key is saved before paid work;
recover a lost paid response with treg `--idempotency-key` and the same scrape request. No retries or
second paid provider; Jina 429 stops without spending. Unknown price or price over $0.01 refuses fallback; charges on rejected
answers are retained. Empty/challenge/consent shells, origin errors and warnings trigger fallback.

Public HTTP(S) only, no credentials/local targets. This guard is not server-side SSRF protection:
providers fetch the URL. Batch callers own robots, site scope, discovery and backoff (`Retry-After`
is saved); keep total anonymous Jina traffic ≤20/min. In-process calls space Jina starts by 3s.
Exit codes: 0 complete/cached, 1 failed, 2 bad URL or refused output directory.

```sh
TREG() { uv run .agents/skills/data-enrichment/scripts/treg.py "$@"; }
TREG search "find work email"          # free, no token: id | price | observed success | what it does
TREG get treg.people.email.find        # free: parameters, price note, providers behind a routed id
TREG call treg.people.email.find --data '{"full_name":"Jane Doe","domain":"example.com"}'
TREG balance
```

`call` prints the provider's answer on stdout and `status · charged · served by` on stderr. Raw
HTTP is the same thing: `https://treg.to/call/<id>` with `X-Treg-Token` (and `X-Treg-Org`).

## What this makes possible (inspiration, not the list)

- **People**: work email from name + domain or a LinkedIn URL, email verification, phone, role and
  job history. "Who is the CTO at these 40 companies, and how do I reach them?"
- **Companies**: firmographics, funding, tech stack, headcount, the email format a domain uses,
  lookalike lists. "Which of our trial signups are companies over 50 people?"
- **Open web**: clean article text from pages that 403 a plain fetch or need JavaScript, web search,
  bounded crawls.
- **Social**: posts, profiles, comments and search on X, LinkedIn, Instagram, TikTok, YouTube
  (incl. captions), Reddit, Threads, Bluesky; creator discovery. "What did these 20 accounts post
  this week?"
- **SEO / AI visibility**: Google SERP and news results, keyword volume and difficulty, backlinks,
  domain authority, brand mentions in AI answer engines.
- **Reviews and commerce**: App Store, Google Play, Trustpilot, Yelp, Amazon listings and reviews.
  "Summarize what competitors' one-star reviews complain about."
- **Own accounts via OAuth**: Search Console, GA4, Google/Meta Ads, Google Business Profile reviews.
- **Generation**: text-to-image, text-to-video, voice and music across models, prices side by side.
- **Market and public data**: stocks, crypto, FX, scholarly papers, clinical studies.

`treg.<capability>` ids are **routed**: treg tries providers cheapest first and names the one that
answered. Any other id is one specific provider.

## Rules that save money and embarrassment

- **Look before you call.** `get <id>` shows the unit: `per_call` is flat, `per_result` bills per
  returned row (your `limit` sets the bill), and a routed call may also pay for providers that
  billed a miss on the way. The helper caps a routed call at $0.05 (`--max-cost`); treg's own
  default is $1.
- **The real charge is the `charged` figure** (`X-Treg-Cost-Micro`), not the catalog estimate.
- **Never repeat a paid lookup.** Every hit bills, repeats included: store results in the repo and
  read them back. Retrying a lost answer: same `--idempotency-key`, no second charge. Never call
  from tests or uncapped loops.
- **A 200 is not a result.** Scrapers return homepages, paywalls and error pages with status 200;
  check the body is about what you asked for (headline words present, plausible length).
- **A found email is a guess until verified.** Run `treg.people.email.verify` before any outreach;
  `invalid` is dead, `accept_all` is risky. Never mail an address no provider returned.
- **Failures:** 429 / 5xx / timeout are not billed; try the next provider. A 4xx is your
  parameters: fix them, do not shop it around. 402 = balance empty, top up in the dashboard.
- **Personal data:** look up people only for a legitimate business purpose; EU contacts fall under
  GDPR. Keep results in the repo, not in chat.
- Generation calls are async (minutes) and their result URLs expire: read the llms.txt section first.

## Going deeper (open only what the task needs)

| Need | Read |
| --- | --- |
| Which platforms exist, with counts and starting prices | `curl -s https://treg.to/catalog/platforms` |
| The right endpoint for a job | `TREG search "<job>"`, then `TREG get <id>` |
| One provider's whole offering | `https://treg.to/tools/<provider>` (e.g. `hunter`) |
| Jobs compared across providers, chained recipes | [use cases](https://treg.to/use-cases), [workflows](https://treg.to/workflows) |
| Everything else: routing headers, async generation, idempotency, error codes, own keys/OAuth, MCP | [llms.txt](https://treg.to/llms.txt) (~750 lines; grep it, do not read it whole) |
| Source, issues, self-hosting | [superdesigndev/treg](https://github.com/superdesigndev/treg) |

The official `treg` CLI and MCP server do the same over a login stored on the machine; this skill
uses the env token so worktrees, cloud sandboxes and colleagues behave the same. Missing capability:
`POST https://treg.to/tool-requests {"capability": "<what you need>"}`.

Offline tests (source repo): `uv run --with pytest pytest skills/data-enrichment -q`.
