#!/usr/bin/env bash
set -uo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: t3-usage-windows start [--dry-run] [--profile ID_OR_NAME]

Launches one cheap warm-up turn (Luna/Haiku, low effort) per enabled Codex and
Claude profile via t3-relay; each warm-up thread settles itself.

  --only  restrict to these provider instance ids ("codex", "claudeAgent",
          "claudeAgent_work", ...). Unknown/disabled ids warn on stderr.
EOF
  exit "${1:-2}"
}

dry_run=0
only=""
profile_query=""
while (($#)); do
  case "$1" in
    --dry-run) dry_run=1 ;;
    --profile) shift; profile_query="${1:-}"; [[ -n "$profile_query" ]] || usage ;;
    --only) shift; only="${1:-}"; [[ -n "$only" ]] || usage ;;
    --only=*) only="${1#*=}" ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
  shift
done

for dependency in jq t3-relay; do
  command -v "$dependency" >/dev/null || {
    echo "Missing dependency: $dependency" >&2
    exit 1
  }
done

t3_base_dir="${T3CODE_HOME:-$HOME/.t3}"
settings_file="$t3_base_dir/userdata/settings.json"
[[ -f "$settings_file" ]] || {
  echo "T3 settings not found: $settings_file" >&2
  exit 1
}

# Mirror T3 enablement semantics. Built-in Codex and Claude are
# enabled by default; named Codex/Claude instances come directly from the registry.
# Rows: instance id, label, driver.
providers=()
while IFS= read -r provider; do
  providers+=("$provider")
done < <(jq -r '
  . as $settings |
  def default_enabled($driver): ($driver == "codex" or $driver == "claudeAgent");
  def enabled($id; $driver):
    ($settings.providerInstances // {})[$id] as $instance
    | if $instance != null then
        if ($instance.enabled == false) or ($instance.config.enabled == false) then false
        else ($instance.enabled // $instance.config.enabled // default_enabled($driver)) end
      else (($settings.providers // {})[$id].enabled // default_enabled($driver)) end;

  (if enabled("codex"; "codex") and
      (($settings.providerInstances // {})["codex"] == null) then
     ["codex", "OpenAI", "codex"] | @tsv
   else empty end),
  (if enabled("claudeAgent"; "claudeAgent") and
      (($settings.providerInstances // {})["claudeAgent"] == null) then
     ["claudeAgent", "Claude", "claudeAgent"] | @tsv
   else empty end),
  (($settings.providerInstances // {}) | to_entries[]
    | select(.value.driver == "codex" or .value.driver == "claudeAgent")
    | select(enabled(.key; .value.driver))
    | [.key, (.value.displayName // .key), .value.driver] | @tsv)
' "$settings_file")

((${#providers[@]})) || {
  echo "No enabled OpenAI or Claude providers found in T3 Code." >&2
  exit 1
}

if [[ -n "$profile_query" ]]; then
  only="$(printf '%s\n' "${providers[@]}" | uv run --no-project python -c '
import sys
sys.path.insert(0, sys.argv[1])
from profiles import matching
ids = [line.split("\t")[0] for line in sys.stdin.read().splitlines()]
print(",".join(i for i in ids if i in matching(sys.argv[2], ids)))
' "$(dirname "$(readlink -f "$0")")" "$profile_query")"
  [[ -n "$only" ]] || { echo "No enabled providers matched --profile $profile_query" >&2; exit 1; }
fi

if [[ -n "$only" ]]; then
  IFS=',' read -ra wanted <<< "$only"
  selected=()
  for want in "${wanted[@]}"; do
    want="${want// /}"
    [[ -z "$want" ]] && continue
    match=""
    for provider_entry in "${providers[@]}"; do
      [[ "${provider_entry%%$'\t'*}" == "$want" ]] && match="$provider_entry" && break
    done
    if [[ -n "$match" ]]; then
      selected+=("$match")
    else
      echo "Warning: --only $want is not an enabled provider instance, skipping" >&2
    fi
  done
  providers=("${selected[@]}")
  ((${#providers[@]})) || {
    echo "No enabled providers matched --only $only." >&2
    exit 1
  }
fi

# Must be a registered T3 project: the caller's repo, else this skill's source repo
# (launchd runs from /, which must never become a project), else home.
warmup_project="$(git rev-parse --show-toplevel 2>/dev/null ||
  git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel 2>/dev/null ||
  { [[ "$PWD" != / ]] && pwd -P || printf '%s\n' "$HOME"; })"

prompt="Reply only: ok. Then, as your last tool call, t3_thread_organize settle without threadId."
failures=0
for provider_entry in "${providers[@]}"; do
  IFS=$'\t' read -r profile label driver <<< "$provider_entry"
  model=haiku
  [[ "$driver" == codex ]] && model=luna
  command=(t3-relay launch --project "$warmup_project" --instance "$profile" --model "$model"
    --effort low --allow-small-model --title "Warm-up — $label" -- "$prompt")
  if ((dry_run)); then
    for arg in "${command[@]}"; do  # byte-safe shell quoting (printf %q mangles UTF-8 under LANG=C)
      [[ "$arg" =~ ^[A-Za-z0-9_./:=,-]+$ ]] && printf '%s ' "$arg" || printf "'%s' " "${arg//\'/\'\\\'\'}"
    done; echo
  elif ! "${command[@]}"; then
    echo "FAILED: $label ($profile) relay launch" >&2
    failures=$((failures + 1))
  fi
done

if ((failures)); then
  echo "Warm-up run finished with $failures failure(s)." >&2
  exit 1
fi
((dry_run)) && verb="Would launch" || verb="Launched"
printf '%s %d warm-up thread(s); each settles itself.\n' "$verb" "${#providers[@]}"
