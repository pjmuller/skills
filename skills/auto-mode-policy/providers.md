# Provider adapters

Check the installed version and effective configuration before applying. These are different engines;
a Claude JSON overlay has no effect on Codex.

## Claude

[claude.md](claude.md): how the classifier decides, the layers, and `scripts/merge_claude.py` (public
baseline + company overlays + personal overlay, dry run then `--apply`). Use `--home` for every configured
`CLAUDE_CONFIG_DIR`, including nonstandard paths. Preserve existing custom rules in canonical overlays
before merging. Inspect each home's `claude auto-mode config`. Environment facts describe trust; narrow
`autoMode.allow` entries resolve the specific false block. Keep defaults and deny rules; don't add broad
tool allows. [Official configuration](https://code.claude.com/docs/en/auto-mode-config).

## Codex

Shared AGENTS informs the agent/reviewer; command-prefix rules cannot express which payload may go to
which delegated profile. Use `[auto_review].policy` for reviewer-specific authorization. This replaces
the tenant policy: retain the **complete active default**, then append a narrow private supplement.
Managed `guardian_policy_config` wins. Don't set `approval_policy=never` or Full Access to fix trust.
[Official configuration](https://learn.chatgpt.com/docs/sandboxing/auto-review).

Acquire the active default from the configured reviewer model's `model_messages.auto_review.policy`
in each home's `models_cache.json` (or a verified version-matched provider source); never guess a
replacement. Verify the selected reviewer and its `{{ tenant_policy_config }}` template slot. In the
private setup repo save the complete default as `base.md` plus sibling `base.json` with `codex_version`,
`policy_sha256` and `template_sha256` (pin the full template hash, not just the slot's presence).
`extra_policy` requires a matching template slot; a recognized setting alone doesn't prove it is used.

`uv run <skill>/scripts/sync_codex.py --base base.md --overlay <private-supplement.md> --home <CODEX_HOME> …`
previews; `--apply` writes (backup first), `--check` verifies. It validates each home's cached
`codex-auto-review` policy and template against the manifest, preserves TOML and config symlinks, and
refuses unrelated custom policies, `extra_policy` or per-profile `auto_review` overrides. Other reviewer
models need explicit inspection and adapter support first. It doesn't change the permission mode.

On policy/template drift (provider upgrade): inspect the change, refresh base and manifest. Export the
current effective policy to a private file first; `--previous-policy <file>` accepts exactly that old
policy, whose intended supplement you carry into the new overlay. A mismatch stays blocked; never paper
over drift or silently replace unrelated customization.

Check app-server `config/read` and `configRequirements/read` for each profile, then a fresh Auto probe:
managed or per-session overrides can defeat correct files. Record the result; restart only sessions the
task owns.
