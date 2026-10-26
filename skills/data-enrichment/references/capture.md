# Page capture (`scripts/capture_url.py`)

One public URL → Markdown via hosted providers, no browser: **free Jina first, then one pinned paid
`olostep.web.scrape` call through treg** (needs `TREG_TOKEN`). Fallback triggers: empty/thin,
challenge or cookie-consent shells, origin HTTP errors, provider warnings or truncation.

- **Spend guards**: no retries, no second paid provider. Jina 429 stops without spending. Fallback
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
