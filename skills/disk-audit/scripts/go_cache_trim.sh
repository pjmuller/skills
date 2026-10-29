#!/usr/bin/env bash
# LRU size cap for the Go build cache. Go has no size limit and only drops entries unused for
# 5 days; agents building many worktrees fill tens of GB per day. Go refreshes an entry's mtime
# when it uses it (hourly granularity), so oldest mtime first = least recently used. Entries used
# in the last hour are never touched, and a missing output is a cache miss, so running builds
# survive (unlike `go clean -cache`). Deletes are batched and paced to spare fseventsd.
# Also fits golangci-lint's cache (a fork of Go's cache, same layout and mtime refresh).
# 12G: a busy agent fleet's measured 6-hour working set is ~9G once GOFLAGS=-trimpath lets worktrees
# share entries.
# Usage: go_cache_trim.sh [CAP_GB] [GOCACHE_DIR...]   defaults: 12, $(go env GOCACHE)
set -uo pipefail

cap_gb=${1:-12}
[ $# -gt 0 ] && shift
dirs=("$@")
[ ${#dirs[@]} -gt 0 ] || dirs=("$(go env GOCACHE)")

for dir in "${dirs[@]}"; do
  [ -d "$dir/ff" ] || { echo "skip $dir: not a Go build cache"; continue; }
  victims=$(mktemp -t gotrim)
  read -r before after count < <(
    find "$dir" -mindepth 2 -type f -print0 | xargs -0 stat -f '%m%t%b%t%N' 2>/dev/null | sort -n |
    awk -F'\t' -v cap="$cap_gb" -v cutoff="$(( $(date +%s) - 3600 ))" -v out="$victims" '
      { m[NR]=$1; s[NR]=$2*512; p[NR]=$3; total+=s[NR] }   # allocated blocks, not apparent size
      END {
        before=total; limit=cap*1024^3; n=0
        for (i=1; i<=NR && total>limit && m[i]<cutoff; i++) { print p[i] > out; total-=s[i]; n++ }
        printf "%.1f %.1f %d\n", before/1024^3, total/1024^3, n
      }')
  tr '\n' '\0' < "$victims" | xargs -0 -n 2000 sh -c 'rm -f "$@"; sleep 0.3' _
  rm -f "$victims"
  printf '%s  %s  %sG -> %sG (cap %sG, %s files)\n' "$(date '+%F %H:%M')" "$dir" "$before" "$after" "$cap_gb" "$count"
done

# Killed `go build/test/run` (agent timeouts) leave their $TMPDIR/go-build* work dir behind until
# reboot, ~10/day at up to 1G each. Go never reuses one, so a day-old dir is garbage.
gone=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'go-build*' -type d -mtime +0 -print -exec rm -rf {} + 2>/dev/null | wc -l)
[ "$gone" -eq 0 ] || printf '%s  removed %s stale go-build work dirs\n' "$(date '+%F %H:%M')" "$gone"
