# Provider adapters

Check the installed version and effective configuration before applying. These are different engines;
a Claude JSON overlay has no effect on Codex.

## Claude

Use the installed `claude-auto-mode` skill's `scripts/merge.py`: public baseline + company overlays +
personal overlay, dry run then `--apply`. Use `--home` for every configured `CLAUDE_CONFIG_DIR`,
including nonstandard paths. Preserve existing custom rules in canonical overlays before merging.
Inspect each home's `claude auto-mode config`. Environment facts describe trust; narrow `autoMode.allow`
entries resolve the specific false block. Keep defaults and deny rules; don't add broad tool allows.
[Official configuration](https://code.claude.com/docs/en/auto-mode-config).

## Codex

Shared AGENTS informs the agent/reviewer; command-prefix rules cannot express which payload may go to
which delegated profile. Use `[auto_review].policy` for reviewer-specific authorization. This replaces
the tenant policy: retain the **complete active default**, then append a narrow private supplement.
Managed `guardian_policy_config` wins. Don't set `approval_policy=never` or Full Access to fix trust.
[Official configuration](https://learn.chatgpt.com/docs/sandboxing/auto-review).

Acquire the active default from the configured reviewer model's `model_messages.auto_review.policy`
in each home's `models_cache.json`, or a verified version-matched provider source. Verify the selected
reviewer and `{{ tenant_policy_config }}` template slot. Save the complete default in `base.md` and a sibling `base.json` with `codex_version`,
`policy_sha256` and `template_sha256` in the private setup repo. Pin the full template hash, not just
the presence of its policy slot. Don't guess a replacement if the active policy is unavailable. `extra_policy`
requires a matching template slot; a recognized setting alone doesn't prove it is used.

`uv run <skill>/scripts/sync_codex.py --base <complete-default.md> --overlay <private-supplement.md>
--home <CODEX_HOME> …` previews changes; `--apply` writes, `--check` verifies. It validates the cached
`codex-auto-review` policy against the base in every home, preserves TOML and config symlinks, and
refuses to overwrite an unrelated custom policy. Other reviewer models require explicit inspection
and adapter support first. On policy/template drift, inspect the change and refresh the complete base and manifest. Export the
current effective policy to a private text file first; an upgrade can pass `--previous-policy <file>`
to accept that exact old policy. Preserve its intended supplement in the new overlay. A mismatched
previous policy remains blocked; never paper over drift or silently replace unrelated customization. The helper doesn't change the runtime's permission mode.

Check app-server `config/read` and `configRequirements/read` for each profile, then a fresh Auto probe:
managed or per-session overrides can defeat otherwise correct files. Record the result and restart
only sessions the task owns if needed. Check policy/template drift after provider upgrades.
