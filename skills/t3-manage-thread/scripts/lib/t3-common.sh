#!/usr/bin/env bash
# Shared plumbing for the t3-manage-thread helpers (spawn / ping / settle / hide).
# Sourced, never executed. Bash 3.2+ (macOS) and Bash 5 (Linux/WSL) compatible.
#
#   t3_require jq curl uuidgen        # hard dependency check
#   t3_bootstrap                      # base dir, origin, server version, pinned t3 CLI
#   t3_issue_session LABEL [TTL]      # scoped bearer token + auto-revoke trap
#   t3_dispatch PAYLOAD [OUTFILE]     # POST to /api/orchestration/dispatch
#   t3_shell_snapshot                 # GET  /api/orchestration/shell
#   t3_open_url URL                   # best-effort focus (macOS / Linux / WSL)
#   t3_thread_snapshot ID             # one thread out of the shell snapshot
#   t3_dispatch_command TYPE ID ...   # thread.* command + server-side refusal reason
#   t3_supervise LABEL LOG ARGV...    # detached worker under launchd / systemd --user
#
# Define a `t3_extra_cleanup` function before calling t3_issue_session to hook
# extra teardown into the EXIT trap (t3-settle-thread uses it to drop its
# detached worker job).

# --- dependencies ------------------------------------------------------------
t3_require() {
  local dependency
  for dependency in "$@"; do
    command -v "$dependency" >/dev/null || {
      echo "Missing dependency: $dependency" >&2
      exit 1
    }
  done
}

# --- server discovery + pinned CLI -------------------------------------------
# Sets: t3_base_dir, t3_origin, t3_version, t3_cli (array).
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
  t3_setup_pnpm_path
  t3_select_cli
}

# pnpm's global bin dir is not on PATH in mise-managed shells, so add it here.
# pnpm >= 11 links global bins into $PNPM_HOME/bin and refuses `pnpm add -g`
# unless that exact dir is on PATH; pre-11 linked them into $PNPM_HOME itself.
# $PNPM_HOME/bin is prepended so a fresh global bin always beats a stale pre-11
# shim; the pnpm binary itself is not in either dir, so mise's pnpm stays first.
t3_setup_pnpm_path() {
  if [[ -z "${PNPM_HOME:-}" ]]; then
    case "$(uname -s)" in
      Darwin) PNPM_HOME="$HOME/Library/pnpm" ;;
      *) PNPM_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/pnpm" ;;
    esac
  fi
  export PNPM_HOME
  case ":$PATH:" in
    *":$PNPM_HOME/bin:"*) ;;
    *) export PATH="$PNPM_HOME/bin:$PATH" ;;
  esac
}

t3_local_version() {
  # "t3 v0.0.33" → "0.0.33"
  t3 --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Prefer a local t3 binary pinned to the server version; self-heal a missing or
# stale install via pnpm add -g, and only fall back to the slower pnpm dlx.
t3_select_cli() {
  t3_cli=()
  if command -v t3 >/dev/null && [[ "$(t3_local_version)" == "$t3_version" ]]; then
    t3_cli=(t3)
  elif command -v pnpm >/dev/null; then
    local install_log
    install_log="$(mktemp "${TMPDIR:-/tmp}/t3-install.XXXXXX")"
    if pnpm add -g "t3@$t3_version" >"$install_log" 2>&1; then
      hash -r
      if [[ "$(t3_local_version)" == "$t3_version" ]]; then
        echo "note: installed global t3@$t3_version to match the T3 server" >&2
        t3_cli=(t3)
      else
        echo "note: installed t3@$t3_version but PATH still resolves t3 to $(command -v t3 || echo '<none>') ($(t3_local_version || true))" >&2
      fi
    else
      echo "note: pnpm add -g t3@$t3_version failed:" >&2
      sed 's/^/  /' "$install_log" >&2
    fi
    rm -f -- "$install_log"
    if [[ ${#t3_cli[@]} -eq 0 ]]; then
      echo "note: falling back to pnpm dlx t3@$t3_version" >&2
      t3_cli=(pnpm --silent dlx "t3@$t3_version")
    fi
  else
    echo "Missing dependency: t3 CLI v$t3_version (or pnpm to fetch it via dlx)" >&2
    exit 1
  fi
}

# --- scoped auth session -----------------------------------------------------
# t3_issue_session LABEL [TTL]  (TTL as accepted by the CLI, default 2m)
# Sets: t3_auth_session_id, t3_credential_dir, t3_auth_header_file; installs the
# revoke/cleanup EXIT trap. `desktop-managed-local` auth is not a blocker: the
# matching CLI mints and revokes its own short-lived scoped bearer session.
t3_issue_session() {
  local label="$1"
  local ttl="${2:-2m}"
  local issue_stderr_file issued_json="" attempt
  issue_stderr_file="$(mktemp "${TMPDIR:-/tmp}/$label-issue.XXXXXX")"
  for attempt in 1 2; do
    issued_json="$("${t3_cli[@]}" auth session issue --base-dir "$t3_base_dir" \
      --ttl "$ttl" --label "$label" --subject local-skill --json 2>>"$issue_stderr_file")" || issued_json=""
    [[ -z "$issued_json" ]] || break
    echo "attempt $attempt: auth session issue produced no stdout, retrying" >>"$issue_stderr_file"
  done
  if ! t3_auth_session_id="$(printf '%s' "$issued_json" | jq -er '.sessionId' 2>/dev/null)"; then
    echo "Could not issue a T3 auth session via: ${t3_cli[*]}" >&2
    echo "stdout was: ${issued_json:-<empty>}" >&2
    sed 's/^/stderr: /' "$issue_stderr_file" >&2
    rm -f -- "$issue_stderr_file"
    exit 1
  fi
  rm -f -- "$issue_stderr_file"
  t3_credential_dir="$(mktemp -d "${TMPDIR:-/tmp}/$label.XXXXXX")"
  chmod 700 "$t3_credential_dir"
  trap t3_cleanup EXIT
  t3_auth_header_file="$t3_credential_dir/authorization-header"
  printf 'Authorization: Bearer %s\n' "$(printf '%s' "$issued_json" | jq -er '.token')" \
    > "$t3_auth_header_file"
  chmod 600 "$t3_auth_header_file"
}

t3_cleanup() {
  if [[ -n "${t3_auth_session_id:-}" ]]; then
    # Revocation is hygiene, not part of the user operation. The T3 CLI has
    # occasionally wedged here after a successful dispatch, leaving scheduled
    # jobs stuck forever even though their ping already landed. Tokens are
    # short-lived, so bound cleanup and let expiry be the final backstop.
    "${t3_cli[@]}" auth session revoke --base-dir "$t3_base_dir" \
      "$t3_auth_session_id" >/dev/null 2>&1 &
    local revoke_pid=$! watchdog_pid
    (
      sleep 5
      kill "$revoke_pid" 2>/dev/null || true
      sleep 1
      kill -KILL "$revoke_pid" 2>/dev/null || true
    ) </dev/null >/dev/null 2>&1 &
    watchdog_pid=$!
    wait "$revoke_pid" 2>/dev/null || true
    kill "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true
  fi
  [[ -z "${t3_credential_dir:-}" ]] || rm -rf -- "$t3_credential_dir"
  if declare -F t3_extra_cleanup >/dev/null; then
    t3_extra_cleanup
  fi
}

# --- API calls ---------------------------------------------------------------
# On failure the response body goes to stderr: a bare `curl: (22) ... 401` (seen 2026-09-09,
# every scheduled spawn failed for 90 min) hides whether T3 rejected the signature, the
# session id or the scope.
t3_shell_snapshot() {
  local body
  body="$(mktemp "${TMPDIR:-/tmp}/t3-shell.XXXXXX")"
  if curl -sS --fail-with-body --connect-timeout 3 --max-time 20 \
    -H "@$t3_auth_header_file" "$t3_origin/api/orchestration/shell" -o "$body"; then
    cat "$body"; rm -f -- "$body"
    return 0
  fi
  echo "T3 shell snapshot failed (session $t3_auth_session_id): $(head -c 400 "$body" | tr -d '\n')" >&2
  rm -f -- "$body"
  return 1
}

# t3_dispatch PAYLOAD [RESPONSE_FILE]
t3_dispatch() {
  local payload="$1"
  local response_file="${2:-/dev/null}"
  printf '%s' "$payload" | curl --fail-with-body -sS \
    --connect-timeout 3 --max-time 20 \
    -H "@$t3_auth_header_file" -H 'Content-Type: application/json' \
    --data-binary @- "$t3_origin/api/orchestration/dispatch" > "$response_file"
}

# --- portability -------------------------------------------------------------
t3_is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" ]] && return 0
  [[ -r /proc/version ]] && grep -qi microsoft /proc/version
}

# Best-effort: focusing the app must never fail the caller.
t3_open_url() {
  local url="$1"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    open "$url" >/dev/null 2>&1 || true
    return 0
  fi
  if t3_is_wsl; then
    if command -v wslview >/dev/null; then
      wslview "$url" >/dev/null 2>&1 && return 0
    fi
    local cmd_exe
    cmd_exe="$(command -v cmd.exe || true)"
    [[ -n "$cmd_exe" ]] || cmd_exe=/mnt/c/Windows/System32/cmd.exe
    if [[ -x "$cmd_exe" ]]; then
      "$cmd_exe" /c start "" "$url" >/dev/null 2>&1 || true
    fi
    return 0
  fi
  command -v xdg-open >/dev/null && { xdg-open "$url" >/dev/null 2>&1 || true; }
  return 0
}

# --- thread commands ---------------------------------------------------------
# t3_thread_snapshot THREAD_ID — the thread's entry in the shell snapshot (JSON,
# empty when T3 does not know the thread).
t3_thread_snapshot() {
  t3_shell_snapshot | jq -c --arg id "$1" '.threads[] | select(.id == $id)'
}

# t3_dispatch_command TYPE THREAD_ID [EXTRA_JQ_FILTER] [SNOOZED_UNTIL]
# Dispatch errors only carry a traceId, so on refusal this digs the
# human-readable invariant out of the server trace log.
t3_dispatch_command() {
  local type="$1" thread_id="$2" extra="${3:-.}" snoozed_until="${4-}"
  local payload response_file trace_id trace_log detail attempt
  payload="$(jq -n --arg type "$type" \
    --arg commandId "$(uuidgen | tr '[:upper:]' '[:lower:]')" \
    --arg threadId "$thread_id" \
    --arg snoozedUntil "$snoozed_until" \
    "{type:\$type,commandId:\$commandId,threadId:\$threadId} | $extra")"
  response_file="$t3_credential_dir/dispatch-response"
  t3_dispatch "$payload" "$response_file" && return 0
  trace_id="$(jq -r '.traceId // empty' "$response_file" 2>/dev/null || true)"
  echo "T3 rejected $type for thread $thread_id." >&2
  if [[ -n "$trace_id" ]]; then
    trace_log="$t3_base_dir/userdata/logs/server.trace.ndjson"
    detail=""
    for attempt in 1 2 3; do
      detail="$( (grep -hF "$trace_id" "$trace_log" "$trace_log.1" 2>/dev/null || true) |
        grep -oE '\\"detail\\": \\"[^\\]*' | head -1 | sed 's/^.*\\"detail\\": \\"//' || true)"
      [[ -z "$detail" ]] || break
      sleep 1
    done
    if [[ -n "$detail" ]]; then
      echo "Reason: $detail" >&2
    else
      echo "traceId: $trace_id (see $trace_log)" >&2
    fi
  fi
  return 1
}

# t3_print_thread_state THREAD_ID — settle/snooze state after a mutation.
t3_print_thread_state() {
  printf '%s' "$(t3_thread_snapshot "$1")" | jq -r \
    '"Thread: \(.id)\nTitle: \(.title)\nSettled override: \(.settledOverride // "none")\nSettled at: \(.settledAt // "-")\nSnoozed until: \(.snoozedUntil // "-")"'
}

# --- detached workers --------------------------------------------------------
# t3_supervise LABEL LOG_FILE ARGV... — run ARGV under the OS supervisor and
# print which one was used. A calling harness reaps nohup/disown descendants
# when a tool call completes (verified 2026-08-28), so launchd / systemd --user
# must own the detached process.
t3_supervise() {
  local label="$1" log_file="$2"
  shift 2
  if command -v launchctl >/dev/null; then
    # Not `launchctl submit`: that runs the job at Background QoS, where every
    # step crawls (t3 --version 26s instead of 0.9s, keeper start 40-50s late;
    # measured 2026-09-09). A bootstrapped plist with ProcessType=Interactive
    # runs at normal speed. `launchctl remove LABEL` still stops it.
    local plist
    plist="$(mktemp "${TMPDIR:-/tmp}/$label.XXXXXX.plist")"
    {
      printf '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>\n'
      printf '<key>Label</key><string>%s</string>\n' "$label"
      printf '<key>ProcessType</key><string>Interactive</string>\n<key>RunAtLoad</key><true/>\n'
      printf '<key>StandardOutPath</key><string>%s</string>\n' "$log_file"
      printf '<key>StandardErrorPath</key><string>%s</string>\n' "$log_file"
      printf '<key>ProgramArguments</key><array>\n'
      printf '%s\n' "$@" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/^/<string>/' -e 's/$/<\/string>/'
      printf '</array></dict></plist>\n'
    } >"$plist"
    launchctl bootstrap "gui/$(id -u)" "$plist"
    rm -f -- "$plist"
    printf '%s' "launchd"
  elif command -v systemd-run >/dev/null; then
    # --collect reaps the transient unit itself, so the worker needs no self-cleanup.
    systemd-run --user --collect --quiet --unit "$label" \
      --property="StandardOutput=append:$log_file" \
      --property="StandardError=append:$log_file" \
      -- "$@"
    printf '%s' "systemd"
  else
    echo "warning: neither launchctl nor systemd-run is available; falling back to setsid nohup — the calling harness may reap the worker." >&2
    setsid nohup "$@" >>"$log_file" 2>&1 &
    printf '%s' "setsid"
  fi
}

# t3_iso_in SECONDS — ISO-8601 UTC timestamp N seconds from now.
t3_iso_in() {
  local epoch=$(( $(date -u +%s) + $1 ))
  date -u -r "$epoch" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null ||
    date -u -d "@$epoch" '+%Y-%m-%dT%H:%M:%SZ'
}
