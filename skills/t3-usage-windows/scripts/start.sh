#!/usr/bin/env bash
set -uo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: t3-usage-windows start [--dry-run] [--profile ID_OR_NAME]

Starts one low-cost hello-world turn on OpenAI and every enabled Claude profile
registered in T3 Code, then settles all successfully created child threads.

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

for dependency in jq t3-spawn-thread t3-settle-thread; do
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

# Mirror T3/t3-spawn-thread enablement semantics. Built-in Codex and Claude are
# enabled by default; named Claude instances come directly from the registry.
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

  (if enabled("codex"; "codex") then
     ["codex", "OpenAI"] | @tsv
   else empty end),
  (if enabled("claudeAgent"; "claudeAgent") and
      (($settings.providerInstances // {})["claudeAgent"] == null) then
     ["claudeAgent", "Claude"] | @tsv
   else empty end),
  (($settings.providerInstances // {}) | to_entries[]
    | select(.value.driver == "claudeAgent")
    | select(enabled(.key; "claudeAgent"))
    | [.key, (.value.displayName // .key)] | @tsv)
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

# Prefer the caller's repo, then the source repo. CLI global installs have no git
# root; a launchd cwd of / must never become a T3 project, so fall back to home.
hello_project="$(git rev-parse --show-toplevel 2>/dev/null ||
  git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel 2>/dev/null ||
  { [[ "$PWD" != / ]] && pwd -P || printf '%s\n' "$HOME"; })"

created_ids=()
created_labels=()
failures=0

for provider_entry in "${providers[@]}"; do
  IFS=$'\t' read -r profile label <<< "$provider_entry"
  if [[ "$profile" == "codex" ]]; then
    model="gpt-5.6-luna"
    model_label="Luna"
  else
    model="claude-haiku-4-5"
    model_label="Haiku"
  fi

  command=(t3-spawn-thread --no-open --project "$hello_project" --title "Hello world — $label $model_label"
    --profile "$profile" --model "$model" --thinking low)
  ((dry_run)) && command+=(--dry-run)
  command+=(-- "Reply only: Hello world.")

  if output="$("${command[@]}" 2>&1)"; then
    status=0
  else
    status=$?
  fi
  printf '%s\n' "$output"

  expected="Provider: $profile · Model: $model · Thinking: low"
  if ((status != 0)); then
    echo "FAILED: $label ($profile) spawn exited $status" >&2
    failures=$((failures + 1))
    continue
  elif ! grep -Fxq "$expected" <<< "$output"; then
    echo "FAILED: $label resolved an unexpected provider/model selection" >&2
    failures=$((failures + 1))
  fi

  if ((! dry_run)); then
    thread_id="$(sed -n 's/^Thread ID: //p' <<< "$output" | tail -1)"
    if [[ -z "$thread_id" ]]; then
      echo "FAILED: $label spawn returned no thread ID" >&2
      failures=$((failures + 1))
    else
      created_ids+=("$thread_id")
      created_labels+=("$label")
    fi
  fi
done

if ((! dry_run)); then
  for index in "${!created_ids[@]}"; do
    if output="$(t3-settle-thread --wait 300 "${created_ids[$index]}" 2>&1)"; then
      status=0
    else
      status=$?
    fi
    printf '%s\n' "$output"
    if ((status != 0)) || ! grep -Eq '^Settled at: .*[0-9]Z$' <<< "$output"; then
      echo "FAILED: ${created_labels[$index]} settle did not verify a timestamp" >&2
      failures=$((failures + 1))
    fi
  done
fi

if ((failures)); then
  echo "Hello-world run finished with $failures failure(s)." >&2
  exit 1
fi

if ((dry_run)); then
  printf 'Dry run verified %d provider(s).\n' "${#providers[@]}"
else
  printf 'Created and settled %d provider thread(s).\n' "${#created_ids[@]}"
fi
