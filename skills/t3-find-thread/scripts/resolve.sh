# Sourced by the deprecated stubs: print the installed t3-manage-thread scripts dir that ships "$1".
# Order: sibling copy, the skill behind its commands on PATH (another scope), the global homes.
manage_scripts() { # command
  local here dir helper path
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  local dirs=("$here/../../t3-manage-thread/scripts")
  for helper in t3-relay t3-pick-instance; do
    path="$(command -v "$helper" 2>/dev/null)" && dirs+=("$(dirname "$(readlink -f "$path")")")
  done
  dirs+=("$HOME/.agents/skills/t3-manage-thread/scripts" "$HOME/.claude/skills/t3-manage-thread/scripts"
         "${CODEX_HOME:-$HOME/.codex}/skills/t3-manage-thread/scripts")
  for dir in "${dirs[@]}"; do
    [[ -x "$dir/$1" && "$(cd "$dir" && pwd -P)" != "$here" ]] && { cd "$dir" && pwd -P; return 0; }
  done
  return 1
}
