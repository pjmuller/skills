#!/usr/bin/env bash
# Read-only disk usage audit for this macbook. Safe to rerun (monthly).
# Nothing is deleted; cleanup commands are only PRINTED at the end.
#
# Strategy: ONE `du` pass over $HOME into a temp snapshot, every section is
# then just awk over that file. Second (pruned) pass only for big loose files.
set -uo pipefail

HOME_DIR="$HOME"
CODE_DIR="$HOME_DIR/code"
DEPTH=5
SNAP=$(mktemp -t diskaudit)
trap 'rm -f "$SNAP"' EXIT
SUGGESTIONS=()

hr() { printf '\n=== %s ===\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }
short() { case "$1" in "$HOME_DIR"*) printf '~%s\n' "${1#$HOME_DIR}";; *) printf '%s\n' "$1";; esac; }
human() { awk -v b="${1:-0}" 'BEGIN{
  split("B K M G T",u," "); i=1; while(b>=1024 && i<5){b/=1024;i++}
  printf (i==1?"%.0f%s":"%.1f%s"), b, u[i]}'; }

# bytes <path> — from the snapshot; falls back to du for paths outside/deeper.
bytes() {
  local p=${1:-} v
  [ -n "$p" ] && [ -e "$p" ] || { echo 0; return; }
  v=$(awk -F'\t' -v p="$p" '$2==p{print $1; exit}' "$SNAP")
  [ -z "$v" ] && v=$(du -sxk "$p" 2>/dev/null | awk '{print $1; exit}')
  echo $(( ${v:-0} * 1024 ))
}

# children <dir> <n> — direct subdirs of dir, biggest first
children() {
  awk -F'\t' -v p="$1/" '
    index($2,p)==1 && substr($2,length(p)+1) !~ /\// {printf "%d\t%s\n", $1, $2}' "$SNAP" |
  sort -nr | head -"${2:-15}" |
  while IFS=$'\t' read -r k p; do printf '  %8s  %s\n' "$(human $((k*1024)))" "$(short "$p")"; done
}

# list <paths...> — sized list, desc, skipping < 100M
list() {
  local p b out=""
  for p in "$@"; do b=$(bytes "$p"); [ "$b" -ge 104857600 ] && out+="$b|$p"$'\n'; done
  [ -z "$out" ] && { echo "  (nothing above 100M)"; return; }
  printf '%s' "$out" | sort -t'|' -k2 -u | sort -t'|' -k1,1nr | while IFS='|' read -r b p; do
    printf '  %8s  %s\n' "$(human "$b")" "$(short "$p")"; done
}

# dirs_named <name-expr...> — sized list of matching dirs under ~/code
top_dirs() {
  local n=$1; shift
  find "$CODE_DIR" -maxdepth "$DEPTH" -name .git -prune -o -type d \( "$@" \) -print 2>/dev/null |
  while read -r d; do printf '%s\t%s\n' "$(bytes "$d")" "$d"; done |
  sort -nr | head -"$n" |
  while IFS=$'\t' read -r b p; do
    [ "$b" -ge 52428800 ] && printf '  %8s  %s\n' "$(human "$b")" "$(short "$p")"; done
}

suggest() { # <bytes> <min_gb> <cmd> <why>
  awk -v b="$1" -v m="$2" 'BEGIN{exit !(b/1073741824 >= m)}' || return 0
  SUGGESTIONS+=("$(printf '%9s  %s\n             %s' "$(human "$1")" "$3" "$4")")
}

echo "Disk audit — $(date '+%Y-%m-%d %H:%M')  host $(hostname -s)"
echo "scanning \$HOME (one du pass; minutes if caches are huge)..."
START=$(date +%s)
du -xk -d "$DEPTH" "$HOME_DIR" 2>/dev/null > "$SNAP"
echo "scan done in $(( $(date +%s) - START ))s"

hr "OVERALL"
df -h / /System/Volumes/Data 2>/dev/null | grep -v '^map'
printf '  home total: %s\n' "$(human "$(bytes "$HOME_DIR")")"

hr "HOME TOP-LEVEL"
children "$HOME_DIR" 20

hr "~/Library"
children "$HOME_DIR/Library" 12

hr "DEVELOPER CACHES"
CACHES=("$HOME_DIR/.cache" "$HOME_DIR/.npm" "$HOME_DIR/.yarn" "$HOME_DIR/.bun"
        "$HOME_DIR/.gem" "$HOME_DIR/.bundle" "$HOME_DIR/.cargo" "$HOME_DIR/.rustup"
        "$HOME_DIR/Library/Caches/go-build" "$HOME_DIR/Library/Caches/golangci-lint"
        "$HOME_DIR/.local/pipx" "$HOME_DIR/.local/share/mise"
        "$HOME_DIR/Library/Developer/Xcode/DerivedData"
        "$HOME_DIR/Library/Developer/CoreSimulator")
have pnpm && PNPM_STORE=$(pnpm store path 2>/dev/null)
have uv   && UV_CACHE=$(uv cache dir 2>/dev/null)
have brew && BREW_CACHE=$(brew --cache 2>/dev/null)
have go   && { GOCACHE=$(go env GOCACHE 2>/dev/null); GOMODCACHE=$(go env GOMODCACHE 2>/dev/null); }
for extra in "${PNPM_STORE:-}" "${UV_CACHE:-}" "${BREW_CACHE:-}" "${GOCACHE:-}" "${GOMODCACHE:-}"; do
  [ -n "$extra" ] && CACHES+=("$extra")
done
list "${CACHES[@]}"

hr "~/Library/Caches"
children "$HOME_DIR/Library/Caches" 15

hr "~/Library/Application Support"
children "$HOME_DIR/Library/Application Support" 12

hr "~/Library/Containers"
children "$HOME_DIR/Library/Containers" 8

hr "DOCKER / COLIMA"
COLIMA_BYTES=0
if [ -d "$HOME_DIR/.colima" ]; then
  COLIMA_BYTES=$(bytes "$HOME_DIR/.colima")
  echo "  ~/.colima on-disk: $(human "$COLIMA_BYTES")   (VM disks are sparse; apparent size can be larger)"
  find "$HOME_DIR/.colima" -type f -size +500M 2>/dev/null |
    while read -r f; do printf '    %8s  %s\n' "$(human "$(stat -f %z "$f")")" "$(short "$f")"; done
else
  echo "  no ~/.colima"
fi
if have docker && docker info >/dev/null 2>&1; then
  docker system df 2>/dev/null | sed 's/^/  /'
else
  echo "  docker daemon unreachable (colima stopped?) — skipped docker system df"
fi

hr "node_modules UNDER ~/code"
NM_TOTAL=0
if [ -d "$CODE_DIR" ]; then
  NM=$(find "$CODE_DIR" -maxdepth "$DEPTH" -type d -name node_modules -prune 2>/dev/null |
       while read -r d; do printf '%s\t%s\n' "$(bytes "$d")" "$d"; done)
  if [ -n "$NM" ]; then
    NM_TOTAL=$(printf '%s\n' "$NM" | awk -F'\t' '{s+=$1} END{print s+0}')
    echo "  count: $(printf '%s\n' "$NM" | wc -l | tr -d ' ')   total: $(human "$NM_TOTAL")"
    printf '%s\n' "$NM" | sort -nr | head -15 |
      while IFS=$'\t' read -r b p; do printf '  %8s  %s\n' "$(human "$b")" "$(short "$p")"; done
  else echo "  none"; fi
else echo "  no ~/code"; fi

hr "OTHER BUILD ARTIFACTS UNDER ~/code"
if [ -d "$CODE_DIR" ]; then
  top_dirs 20 -name target -o -name dist -o -name .next -o -name build \
              -o -name .venv -o -name .turbo -o -name coverage -o -path '*/tmp/cache'
fi

hr "USER DIRS"
list "$HOME_DIR/Downloads" "$HOME_DIR/Desktop" "$HOME_DIR/Movies" "$HOME_DIR/Documents" \
     "$HOME_DIR/Pictures" "$HOME_DIR/Music" "$HOME_DIR/.Trash" \
     "$HOME_DIR/Library/Mail" "$HOME_DIR/Library/Messages"

hr "LOOSE FILES > 500M"
find "$HOME_DIR" -xdev \( -path "$HOME_DIR/Library/Caches" -o -path "$HOME_DIR/.cache" \
     -o -path "$HOME_DIR/.colima" -o -path "$HOME_DIR/go/pkg" \
     -o -name node_modules -o -name .git \) -prune -o -type f -size +500M -print 2>/dev/null |
  while read -r f; do printf '%s\t%s\n' "$(stat -f %z "$f" 2>/dev/null)" "$f"; done |
  sort -nr | head -20 |
  while IFS=$'\t' read -r b p; do printf '  %8s  %s\n' "$(human "$b")" "$(short "$p")"; done

hr "/Applications"
du -xhd1 /Applications 2>/dev/null | sort -hr | head -11

hr "LOCAL SNAPSHOTS"
tmutil listlocalsnapshots / 2>/dev/null | sed 's/^/  /' | head -10
echo "  (purgeable space: Finder > About This Mac > Storage)"

# ---------------- suggestions ----------------
suggest "$(bytes "${GOCACHE:-$HOME_DIR/Library/Caches/go-build}")" 2 \
  "go clean -cache" "Go build cache — regenerated on next build"
suggest "$(bytes "${GOMODCACHE:-$HOME_DIR/go/pkg/mod}")" 5 \
  "go clean -modcache" "Go module cache — re-downloaded on next build (slow first build)"
suggest "$(bytes "$HOME_DIR/Library/Caches/golangci-lint")" 1 \
  "rm -rf ~/Library/Caches/golangci-lint" "lint cache"
suggest "$(bytes "${PNPM_STORE:-/nonexistent}")" 2 \
  "pnpm store prune" "pnpm store — drops packages no project references"
suggest "$(bytes "$HOME_DIR/Library/Caches/pnpm/dlx")" 1 \
  "rm -rf ~/Library/Caches/pnpm/dlx" "pnpm dlx one-off package cache"
# stale pnpm store versions (only the version pnpm reports is in use)
if [ -d "$HOME_DIR/Library/pnpm/store" ]; then
  for v in "$HOME_DIR"/Library/pnpm/store/v*; do
    [ "$v" = "${PNPM_STORE:-}" ] && continue
    suggest "$(bytes "$v")" 0.5 "rm -rf $(short "$v")" "stale pnpm store version (in use: $(short "${PNPM_STORE:-?}"))"
  done
fi
suggest "$(bytes "$HOME_DIR/.cache/huggingface")" 1 \
  "rm -rf ~/.cache/huggingface" "downloaded HF models — re-downloaded on demand"
suggest "$(bytes "$HOME_DIR/.cache/puppeteer")" 0.5 \
  "rm -rf ~/.cache/puppeteer" "puppeteer browsers"
suggest "$(bytes "$HOME_DIR/.codex/logs_2.sqlite")" 1 \
  "rm -f ~/.codex/logs_2.sqlite   # codex regenerates" "codex log DB"
suggest "$(bytes "${UV_CACHE:-/nonexistent}")" 2 "uv cache clean" "uv wheel/source cache"
suggest "$(bytes "${BREW_CACHE:-/nonexistent}")" 1 "brew cleanup --prune=all" "old Homebrew downloads"
suggest "$(bytes "$HOME_DIR/.npm")" 1 "npm cache clean --force" "legacy npm cache (pnpm is the standard here)"
suggest "$(bytes "$HOME_DIR/.yarn")" 1 "rm -rf ~/.yarn/berry/cache" "legacy yarn cache"
suggest "$(bytes "$HOME_DIR/Library/Caches/ms-playwright")" 1 \
  "rm -rf ~/Library/Caches/ms-playwright" "playwright browsers — re-downloaded on next install"
suggest "$(bytes "$HOME_DIR/Library/Developer/Xcode/DerivedData")" 1 \
  "rm -rf ~/Library/Developer/Xcode/DerivedData/*" "Xcode derived data"
suggest "$(bytes "$HOME_DIR/Library/Developer/CoreSimulator")" 3 \
  "xcrun simctl delete unavailable" "unused iOS simulators"
suggest "$(bytes "$HOME_DIR/.cargo/registry")" 1 "rm -rf ~/.cargo/registry/cache" "cargo registry cache"
suggest "$(bytes "$HOME_DIR/.Trash")" 1 "rm -rf ~/.Trash/*" "Trash"
suggest "$NM_TOTAL" 5 \
  "find ~/code -maxdepth 5 -type d -name node_modules -prune -exec du -sh {} + | sort -hr" \
  "PJ judgment: delete node_modules of dormant repos, 'pnpm i' restores them"
suggest "$(bytes "$HOME_DIR/Downloads")" 3 "open ~/Downloads" "PJ judgment: old downloads"
suggest "$COLIMA_BYTES" 20 \
  "docker image prune -a -f && docker builder prune -a -f && colima ssh -- sudo fstrim -av" \
  "unused images/build cache are regenerated; trim returns freed VM blocks to macOS; volumes/containers stay"
if have docker && docker info >/dev/null 2>&1; then
  SUGGESTIONS+=("$(printf '%9s  %s\n             %s' "see above" \
    "docker system df -v" \
    "PJ judgment: inspect volumes separately; never prune DB volumes as part of routine cleanup")")
fi

hr "SUGGESTED CLEANUPS (nothing was executed)"
if [ ${#SUGGESTIONS[@]} -eq 0 ]; then echo "  nothing above thresholds — disk is tidy"
else printf '%s\n' "${SUGGESTIONS[@]}"; fi
echo
echo "Companion: scripts/disk_cleanup.sh runs only the always-safe prunes (with confirm)."
