---
name: perplexity-core
description: "Use for sourced web research with URLs (\"who is this person\", \"profile this company\", size a market, check a fact, prep a meeting) as cited text or schema-shaped JSON. Paid per call; never from tests."
---

# Perplexity core

One PEP 723 script; the consuming repo supplies `PERPLEXITY_API_KEY` in its mise env file. The core
directory is replaced on update: nothing local lives here. `scripts/install --check` verifies uv,
deps and key. Offline tests: `uv run --with pytest pytest skills/perplexity-core/scripts -q`.

```sh
PX() { uv run .agents/skills/perplexity-core/scripts/px.py "$@"; }
PX check                                        # key + SDK, spends nothing
PX ask "Who is Jane Doe at Example NV?" --people-search
PX ask - < question.md --out answer.md          # long prompt from stdin
PX ask "Example NV, Belgium" --schema company.json --json
```

## Contract

- **Every `ask` is paid** (cents; `--context-size high` and `--people-search` cost more). No tests,
  UI checks or uncapped loops; cache answers in the repo as Markdown.
- **Exit 3 = no answer**: the API sometimes returns retrieved URLs with empty text (seen under rate
  limiting). After retries the CLI prints those URLs on stderr. A failed call, never "no information".
- **Sourced or nothing**: search tools are always on (without them the model doesn't search and
  invents); default instructions demand inline source URLs and a plain "unknown". `Sources:` lists
  only URLs the API actually retrieved.
- **`--schema FILE`**: top-level fields become nullable + required; placeholders ("not disclosed")
  become `null`; keys ending in `url`/`_urls` survive only when they occur in the retrieved results.
- Defaults `PERPLEXITY_MODEL` (`google/gemini-3.8-flash`), `PERPLEXITY_CONTEXT_SIZE` (`medium`);
  per call `--model` / `--context-size`.
- **Personal data**: public professional facts for a legitimate purpose; output in the repo, not chat;
  skip private details.

## Recipes

- **Attendee list**: one `--people-search` ask per person (name + city + event), then one synthesis
  ask over the collected facts. Commit the Markdown; label guesses.
- **Company profiles**: one schema (`website_url`, `summary`, `employee_range`, `business_model`,
  `customer_type` B2B/B2B2C/B2C) so a list stays comparable.
