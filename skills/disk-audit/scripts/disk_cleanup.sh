#!/usr/bin/env bash
# Runs ONLY the always-safe cache prunes (everything here regenerates itself).
# Anything needing judgment (Downloads, docker volumes, colima recreate,
# node_modules) is intentionally NOT here — see scripts/disk_audit.sh output.
set -uo pipefail

have() { command -v "$1" >/dev/null 2>&1; }
size() { [ -e "${1:-}" ] && du -sxh "$1" 2>/dev/null | awk '{print $1}' || echo "-"; }

echo "Safe cache cleanup: go build cache, pnpm store prune + dlx, uv cache,"
echo "brew cleanup, golangci-lint/gopls caches, stale pnpm store versions."
if [ "${1:-}" = "-y" ] || [ "${1:-}" = "--yes" ]; then
  echo "(-y: skipping confirm)"
else
  printf 'Proceed? [y/N] '; read -r ans
  [ "$ans" = "y" ] || { echo "aborted"; exit 0; }
fi

step() { # <label> <path-to-measure> <command...>
  local label=$1 path=$2; shift 2
  local before; before=$(size "$path")
  "$@" >/dev/null 2>&1
  printf '  %-28s %6s -> %s\n' "$label" "$before" "$(size "$path")"
}

have go && step "go build cache" "$(go env GOCACHE)" go clean -cache
have pnpm && step "pnpm store prune" "$(pnpm store path)" pnpm store prune
step "pnpm dlx cache" "$HOME/Library/Caches/pnpm/dlx" rm -rf "$HOME/Library/Caches/pnpm/dlx"
have uv && step "uv cache" "$(uv cache dir)" uv cache clean
have brew && step "homebrew cache" "$(brew --cache)" brew cleanup --prune=all
step "golangci-lint cache" "$HOME/Library/Caches/golangci-lint" rm -rf "$HOME/Library/Caches/golangci-lint"
step "gopls cache" "$HOME/Library/Caches/gopls" rm -rf "$HOME/Library/Caches/gopls"

# stale pnpm store versions (keep the one pnpm reports)
if have pnpm; then
  keep=$(pnpm store path 2>/dev/null)
  for v in "$HOME"/Library/pnpm/store/v*; do
    [ -d "$v" ] && [ "$v" != "$keep" ] && step "stale store $(basename "$v")" "$v" rm -rf "$v"
  done
fi

echo "done — rerun scripts/disk_audit.sh to confirm"
