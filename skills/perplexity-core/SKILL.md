---
name: perplexity-core
description: Use when an agent needs sourced web research (a person, a company, a market, a fact with URLs) through the shared Perplexity Agent API CLI; free-text answers with retrieved sources or structured JSON from a schema. Paid per call; never run it in tests.
---

# Perplexity core

One PEP 723 script, no wrapper needed: the consuming repo only supplies `PERPLEXITY_API_KEY`
through its mise env file. The core directory is replaced on update, so nothing local lives here.

```sh
PX() { uv run .agents/skills/perplexity-core/scripts/px.py "$@"; }
PX check                                        # key + SDK, spends nothing
PX ask "Who is Jo Wyns at Farmad?" --people-search
PX ask - < question.md --out answer.md          # long prompts from stdin, file output
PX ask "Farmad, Belgium" --schema company.json --json   # structured, urls verified
```

`scripts/install --check` verifies uv, deps and the key. Offline tests (source repo):
`uv run --with pytest pytest skills/perplexity-core/scripts -q`.

## Contract

- **Every `ask` is paid** (cents; `--context-size high` and `--people-search` cost more). Never
  call it from tests, UI checks or loops without a cap; cache results in the repo (markdown) instead.
- **Exit 3 = no answer.** The API sometimes returns retrieved URLs with an empty answer (seen under
  rate limiting); the CLI retries once, then exits 3 and prints the URLs to stderr. Treat it as a
  failed call, never as "no information". 429s are retried with backoff.
- **Sourced or nothing.** Search tools are always on; the default instructions demand inline source
  URLs and plain "unknown". `Sources:` lists only URLs the API actually retrieved.
- **Structured mode** (`--schema FILE`): every top-level field becomes nullable + required;
  placeholder strings ("not disclosed") become `null`; any key ending in `url`/`_urls` is kept only
  when it occurs in the retrieved results (no invented LinkedIn/company links).
- Model/context defaults: `PERPLEXITY_MODEL` (default `google/gemini-3.8-flash`) and
  `PERPLEXITY_CONTEXT_SIZE` (`medium`); override per call with `--model` / `--context-size`.
- Personal data: research public professional facts for a legitimate purpose (meeting prep,
  audience tailoring); keep the output in the repo, not in chat history, and skip private details.

## Recipes

- **Audience / attendee list**: one `ask` per unknown person (`--people-search`, name + city +
  event), then one synthesis `ask` over the collected facts for the group picture. Commit the
  markdown; label guesses.
- **Company profile**: schema with `website_url`, `summary`, `employee_range`, `business_model`,
  `customer_type` (B2B / B2B2C / B2C) so answers are comparable across a list.
