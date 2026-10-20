#!/usr/bin/env bash
# Shared plumbing for the t3-manage-thread scripts (T3 Code >= 0.1 only). Sourced, never executed.
# Bash 3.2+ (macOS) and Bash 5 (Linux/WSL) compatible.
#
#   normalize_model ALIAS [INSTANCE]   # sol/opus/fable/astra/luna/haiku/gemini → model id
#   house_thinking MODEL               # house effort: sol/opus high, fable/astra medium, haiku low
#   below_model_floor MODEL            # true below OpenAI gpt-6 / Sol 6.1
#   t3_bootstrap                       # t3_base_dir, t3_origin, t3_version, t3_cli (t3-preview-gc)
#
# Threads are started and messaged through T3's MCP tools (agents) or t3-relay (scripts).

t3_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# --- model selection (needs t3_base_dir from t3_bootstrap) --------------------
# normalize_model ALIAS [INSTANCE_ID] — alias → model id; sol/opus follow T3's
# catalog (sol: the given Codex account's own catalog). Full ids pass through.
normalize_model() {
  local normalized
  normalized="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$normalized" in
    sol|opus)
      uv run --script "$t3_lib_dir/model_resolution.py" "$normalized" "$t3_base_dir" "${2:-}"
      ;;
    claude|anthropic) normalize_model opus "${2:-}" ;;
    astra|codex|openai) printf '%s' "gpt-6-astra" ;;
    luna) printf '%s' "gpt-6-luna" ;;
    haiku) printf '%s' "claude-haiku-5-5" ;;
    fable) printf '%s' "claude-fable-5-1" ;;
    gemini) printf '%s' "gemini-3.8-flash-high" ;;
    *) printf '%s' "$1" ;;
  esac
}

# House effort for an explicitly chosen model: sol/opus high, fable/astra medium,
# haiku low; empty when the model has no house default.
house_thinking() {
  case "$1" in
    gpt-*-sol|claude-opus-*) printf 'high' ;;
    claude-fable-*|gpt-*-astra*) printf 'medium' ;;
    claude-haiku-*) printf 'low' ;;
  esac
}

# Model floor: "5.5" in a brief means Opus 5.5, and an older OpenAI build is never
# the default choice (OpenAI >= gpt-6, Sol >= 6.1).
below_model_floor() {
  local m
  m="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$m" =~ ^gpt-([0-9]+)(\.([0-9]+))?(-|$) ]] || return 1
  local major="${BASH_REMATCH[1]}" minor="${BASH_REMATCH[3]:-0}"
  ((major < 6)) && return 0
  [[ "$m" == *-sol ]] && ((major == 6 && minor < 1)) && return 0
  return 1
}

# --- server discovery ---------------------------------------------------------
# Sets: t3_base_dir, t3_origin, t3_version, t3_cli (array: the app's bundled CLI).
t3_bootstrap() {
  t3_base_dir="${T3CODE_HOME:-$HOME/.t3}"
  local runtime_file="$t3_base_dir/userdata/server-runtime.json"
  # server-runtime.json is the server's own state file, but a failing `t3 project add`
  # deletes it while the server keeps running (2026-09-08/09). Remember the last origin
  # that answered so helpers keep working until the desktop rewrites the file.
  local last_origin_file="$t3_base_dir/userdata/last-server-origin"
  local descriptor
  if [[ -f "$runtime_file" ]]; then
    t3_origin="$(jq -er '.origin' "$runtime_file")"
    descriptor="$(curl -fsS --connect-timeout 3 --max-time 15 \
      "$t3_origin/.well-known/t3/environment")" || {
      echo "T3 Code is not reachable at $t3_origin." >&2
      exit 1
    }
    printf '%s\n' "$t3_origin" > "$last_origin_file"
  elif [[ -f "$last_origin_file" ]] && t3_origin="$(<"$last_origin_file")" &&
    descriptor="$(curl -fsS --connect-timeout 3 --max-time 15 "$t3_origin/.well-known/t3/environment")"; then
    echo "note: $runtime_file is missing; using last known origin $t3_origin" >&2
  else
    echo "T3 Code is not running: $runtime_file was not found." >&2
    exit 1
  fi
  t3_version="$(printf '%s' "$descriptor" | jq -er '.serverVersion')"
  t3_cli=("${T3CODE_CLI_PATH:-$t3_base_dir/bin/t3}")
  [[ -x "${t3_cli[0]}" ]] || { echo "T3's bundled CLI is missing at ${t3_cli[0]}: open T3 Code once." >&2; exit 1; }
}
