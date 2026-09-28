#!/usr/bin/env bash
# Read-only CPU/RAM snapshot for this Mac. Safe to rerun; nothing is stopped.
# Follow-up commands are only PRINTED at the end.
#
# Usage: resource_snapshot.sh [seconds]   (paging/CPU sample window, default 5)
# Prints executable names, never full command lines (those can carry secrets).
set -uo pipefail

INTERVAL=${1:-5}
[[ "$INTERVAL" =~ ^[1-9][0-9]*$ ]] || { echo "usage: resource_snapshot.sh [seconds]" >&2; exit 2; }
SUGGESTIONS=()

hr() { printf '\n=== %s ===\n' "$1"; }
suggest() { SUGGESTIONS+=("$(printf '  %s\n      %s' "$1" "$2")"); } # <cmd> <why>
comm_of() { # executable basename; pid 0 is kernel_task; short-lived pids may be gone
  [ "$1" = 0 ] && { echo kernel_task; return; }
  local c; c=$(ps -p "$1" -o comm= 2>/dev/null | awk '{sub(/^.*\//,""); print}')
  echo "${c:-(exited)}"
}
# top prints 2061M / 1.2G / 512K, sometimes with a trailing +/-; normalise to MiB.
to_mib() { awk -v v="$1" 'BEGIN{sub(/[+-]$/,"",v); u=substr(v,length(v)); n=v+0
  if(u=="G")n*=1024; else if(u=="K")n/=1024; else if(u=="B")n/=1048576; else if(u=="T")n*=1048576
  printf "%d", n}'; }
vm_counter() { awk -v k="$2" -F: '$1==k{gsub(/[ .]/,"",$2); print $2; exit}' <<<"$1"; }

RAM_BYTES=$(sysctl -n hw.memsize)
RAM_MIB=$(( RAM_BYTES / 1048576 ))
echo "Resource snapshot — $(date '+%Y-%m-%d %H:%M:%S')  host $(hostname -s)"
echo "  $(sysctl -n hw.ncpu) cores, $(( RAM_MIB / 1024 )) GiB RAM, load avg $(sysctl -n vm.loadavg | tr -d '{}' | xargs)"
echo "  sampling ${INTERVAL}s..."

VM0=$(vm_stat); T0=$(date +%s)
# ps %cpu is a decaying average; top's second sample is the current load.
TOP_CPU_OUT=$(top -l 2 -s "$INTERVAL" -o cpu -n 15 -stats pid,ppid,cpu | awk '/^CPU usage/{n++} n==2')
CPU_LINE=$(grep 'CPU usage' <<<"$TOP_CPU_OUT")
CPU_ROWS=$(awk '$1 ~ /^[0-9]+$/' <<<"$TOP_CPU_OUT")
VM1=$(vm_stat); ELAPSED=$(( $(date +%s) - T0 )); [ "$ELAPSED" -gt 0 ] || ELAPSED=1
PAGE=$(sed -n 's/.*page size of \([0-9]*\) bytes.*/\1/p' <<<"$VM1" | head -1)

hr "CPU (second top sample = current)"
echo "  ${CPU_LINE#CPU usage: }"
IDLE=$(sed -n 's/.* \([0-9.]*\)% idle.*/\1/p' <<<"$CPU_LINE")
printf '      PID    PPID     CPU      ELAPSED  COMMAND\n'
while read -r pid ppid cpu; do
  printf '  %7s %7s %6s%% %12s  %s\n' "$pid" "$ppid" "$cpu" "$(ps -p "$pid" -o etime= 2>/dev/null | xargs)" "$(comm_of "$pid")"
done <<<"$CPU_ROWS"
TOP_CPU_PID=$(awk 'NR==1{print $1}' <<<"$CPU_ROWS"); TOP_CPU_PCT=$(awk 'NR==1{printf "%d",$3}' <<<"$CPU_ROWS")

hr "MEMORY"
LEVEL=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null || echo 0)
case "$LEVEL" in 1) LEVEL_NAME=normal;; 2) LEVEL_NAME=WARN;; 4) LEVEL_NAME=CRITICAL;; *) LEVEL_NAME="unknown ($LEVEL)";; esac
echo "  pressure: $LEVEL_NAME   $(memory_pressure 2>/dev/null | grep -i 'free percentage' | sed 's/^System-wide memory //')"
top -l 1 -n 0 | grep PhysMem | sed 's/^/  /'
echo "  swap: $(sysctl -n vm.swapusage)   (allocated swap is history; PAGING shows current activity)"

hr "PAGING over ${ELAPSED}s (counters are cumulative; deltas show current activity)"
SWAPOUT_MIB=0
for key in Pageouts Swapouts Swapins; do
  d=$(( $(vm_counter "$VM1" "$key") - $(vm_counter "$VM0" "$key") ))
  mib=$(( d * ${PAGE:-16384} / 1048576 ))
  printf '  %-9s %8d pages  %6d MiB  (%d MiB/s)\n' "$key" "$d" "$mib" $(( mib / ELAPSED ))
  [ "$key" = Swapouts ] && SWAPOUT_MIB=$mib
done

hr "TOP PHYSICAL FOOTPRINT (top MEM incl. compressed; better than RSS)"
MEM_ROWS=$(top -l 1 -o mem -n 15 -stats pid,ppid,mem,cmprs | awk '$1 ~ /^[0-9]+$/')
printf '      PID    PPID      MEM    CMPRS  COMMAND\n'
while read -r pid ppid mem cmprs; do
  printf '  %7s %7s %8s %8s  %s\n' "$pid" "$ppid" "$mem" "$cmprs" "$(comm_of "$pid")"
done <<<"$MEM_ROWS"
TOP_MEM_PID=$(awk 'NR==1{print $1}' <<<"$MEM_ROWS")
TOP_MEM_MIB=$(to_mib "$(awk 'NR==1{print $3}' <<<"$MEM_ROWS")")

hr "PROCESS SWARMS (parents by direct child count; PPID 1 = launchd, mixed)"
SWARM=$(ps -axo ppid= | sort | uniq -c | sort -nr | awk '$2!=1 && $2!=0' | head -8)
while read -r count ppid; do
  printf '  %5d children  ppid %-7s %s\n' "$count" "$ppid" "$(comm_of "$ppid")"
done <<<"$SWARM"
echo "  -- same executable name --"
ps -axo comm= | awk '{sub(/^.*\//,""); print}' | sort | uniq -c | sort -nr | head -8 | sed 's/^/  /'
TOP_SWARM_COUNT=$(awk 'NR==1{print $1}' <<<"$SWARM"); TOP_SWARM_PPID=$(awk 'NR==1{print $2}' <<<"$SWARM")

# ---------------- suggestions (thresholds live here) ----------------
IDLE_MIN=20          # % idle below which the machine counts as CPU-bound
PROC_CPU_MAX=90      # one process near a full core
MEM_SHARE_MAX=25     # % of RAM for a single footprint
SWAPOUT_MAX=100      # MiB swapped out during the sample = active thrashing
SWARM_MAX=50         # direct children of one non-launchd parent

owner="ps -ww -p PID -o pid,ppid,pgid,pcpu,etime,args; lsof -a -p PID -d cwd"
if awk -v i="${IDLE:-100}" -v m="$IDLE_MIN" 'BEGIN{exit !(i<m)}'; then
  suggest "${owner//PID/$TOP_CPU_PID}" "CPU-bound (${IDLE}% idle); top CPU is $(comm_of "$TOP_CPU_PID") — find its owner"
fi
if [ "${TOP_CPU_PCT:-0}" -ge "$PROC_CPU_MAX" ]; then
  suggest "sample $TOP_CPU_PID 3 -file \$(mktemp /tmp/cpu-sample.XXXXXX)" \
    "$(comm_of "$TOP_CPU_PID") at ${TOP_CPU_PCT}% — stack sample shows loop/poll/retry (rerun snapshot first; spikes are transient)"
fi
if [ "$LEVEL" -ge 2 ] 2>/dev/null; then
  suggest "${owner//PID/$TOP_MEM_PID}" "memory pressure $LEVEL_NAME; biggest footprint is $(comm_of "$TOP_MEM_PID")"
fi
if [ "${TOP_MEM_MIB:-0}" -ge $(( RAM_MIB * MEM_SHARE_MAX / 100 )) ]; then
  suggest "vmmap -summary $TOP_MEM_PID" \
    "$(comm_of "$TOP_MEM_PID") holds >${MEM_SHARE_MAX}% of RAM; rerun snapshot to tell growth from a stable allocation"
fi
if [ "$SWAPOUT_MIB" -ge "$SWAPOUT_MAX" ]; then
  suggest "resource_snapshot.sh 10" "swapping out ${SWAPOUT_MIB} MiB in ${ELAPSED}s = active thrashing; confirm it persists"
fi
if [ "${TOP_SWARM_COUNT:-0}" -ge "$SWARM_MAX" ]; then
  suggest "ps -ww -o pid,etime,args -g \$(ps -p $TOP_SWARM_PPID -o pgid=)" \
    "$(comm_of "$TOP_SWARM_PPID") ($TOP_SWARM_PPID) has $TOP_SWARM_COUNT children; young, growing workers = spawn loop"
fi

hr "SUGGESTED FOLLOW-UPS (nothing was executed)"
if [ ${#SUGGESTIONS[@]} -eq 0 ]; then echo "  nothing above thresholds — CPU and RAM look healthy"
else printf '%s\n' "${SUGGESTIONS[@]}"; fi
