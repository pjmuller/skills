# Page capture (`scripts/capture_url.py`)

One public URL → Markdown via hosted providers, no browser: **free Jina first, then one pinned paid
`olostep.web.scrape` call through treg** (needs `TREG_TOKEN`). Fallback triggers: empty/thin,
challenge or cookie-consent shells, origin HTTP errors, provider warnings or truncation.

- **Spend guards**: no retries, no second paid provider. Jina 429 or a login wall stops without
  spending (a scraper can't log in: use the site's public API or a signed-in browser). Fallback
  refuses when the catalog price is unknown, not per-call, or over $0.01. A UUID idempotency key is
  saved in `capture.json` before paid work: recover a lost paid answer with
  `treg.py call olostep.web.scrape --idempotency-key <key>` and the same request. Charges on rejected
  answers stay recorded in the receipts.
- **`DIR` is a durable cache**: a matching completed capture is returned as is; failed, pending or
  mismatched output refuses. New directory = fresh capture.
- **Output**: `page.md` (marked untrusted), `capture.json`, raw provider JSON (incl. HTML when
  available) and receipts, kept even when validation fails. Links: inline links stay, plus a list
  uniting inline and provider links. Transport vs origin status, provider, charges and call ids stay
  separate; missing origin status or final URL stays unknown (`reported_url` may just echo the
  request). Check coverage yourself.
- **Scope**: public HTTP(S), no credentials or local/private hosts. Not SSRF protection: providers
  fetch the URL. Batch callers own robots, site scope, discovery and backoff (`Retry-After` is saved);
  keep anonymous Jina traffic ≤20/min (in-process calls space Jina starts by 3 s).
- **Exit**: 0 complete or cached, 1 failed, 2 bad URL or refused output directory.

## Sites a capture can't read

- **Redirectors** (`share.google`, `t.co`, `lnkd.in`, URL shorteners): resolve first,
  `curl -sL -o /dev/null -w '%{url_effective}' URL`, then capture the destination.
- **X/Twitter post** (scrapers get a login wall, or the post text without its images): free public
  JSON, no account,
  `curl -s 'https://cdn.syndication.twimg.com/tweet-result?id=<status id>&token=0'` (`token` must be
  present, any value; unofficial, checked 2026-11-02). `.text` is the post,
  `.mediaDetails[].media_url_https` the images: posts sharing a prompt or thread often carry the
  text only in the image, so download it (`?name=orig`) and read it. Long-form X articles and
  threads beyond the first post → signed-in browser.
