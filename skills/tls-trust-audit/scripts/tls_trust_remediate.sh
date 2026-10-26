#!/usr/bin/env bash
# Package upgrades that replace stale trust bundles. Deliberately separate from the audit:
# everything here changes installed software. Confirms once, then runs; -y for agents after "go".
# Never edits a system trust file, never touches a third-party app, never weakens verification.
set -uo pipefail

# Resolve through the symlink scripts/install puts on PATH: the advisory data sits next to
# the real script, not next to the link.
source_path="${BASH_SOURCE[0]}"
while [[ -L "$source_path" ]]; do
  link_target="$(readlink "$source_path")"
  case "$link_target" in
    /*) source_path="$link_target" ;;
    *)  source_path="$(cd "$(dirname "$source_path")" && pwd -P)/$link_target" ;;
  esac
done
script_dir="$(cd "$(dirname "$source_path")" && pwd -P)"
advisory="${script_dir}/../advisories/emudhra-2026-10.conf"
assume_yes=false
do_packages=true
do_venvs=true
do_node=true
do_git=true
do_docker=false   # opt-in: re-pulling every base image is slow and bandwidth-heavy

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) assume_yes=true; shift ;;
    --advisory) advisory="$2"; shift 2 ;;
    --docker) do_docker=true; shift ;;
    --only)
      do_packages=false; do_venvs=false; do_node=false; do_git=false
      case "$2" in
        packages) do_packages=true ;; venvs) do_venvs=true ;;
        node) do_node=true ;; git) do_git=true ;; docker) do_docker=true ;;
        *) echo "--only expects packages|venvs|node|git|docker" >&2; exit 2 ;;
      esac
      shift 2 ;;
    -h|--help)
      sed -n '2,4p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      echo; echo "Usage: tls_trust_remediate.sh [-y] [--docker] [--only STEP] [--advisory FILE]"
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -r "$advisory" ]] || { echo "cannot read advisory: $advisory" >&2; exit 2; }
# shellcheck source=/dev/null
. "$advisory"

plan=""
$do_packages && plan="${plan}  - upgrade all packages from the system package manager"$'\n'
$do_venvs    && plan="${plan}  - upgrade certifi in every virtualenv found under \$HOME"$'\n'
$do_node     && plan="${plan}  - report Node installs needing a patched release (no silent version switch)"$'\n'
$do_git      && plan="${plan}  - point git at the package manager's patched CA bundle"$'\n'
$do_docker   && plan="${plan}  - re-pull every local container base image"$'\n'

printf 'Planned changes on %s:\n%s\n' "$(hostname -s)" "$plan"
if ! $assume_yes; then
  printf 'Proceed? [y/N] '
  read -r reply
  [[ "$reply" == y || "$reply" == Y ]] || { echo 'aborted; nothing changed'; exit 0; }
fi

step() { printf '\n== %s\n' "$1"; }

if $do_packages; then
  step "Package manager"
  if command -v brew >/dev/null; then
    # Full upgrade on purpose: trust bundles ride along inside unrelated formulae, so a
    # hand-picked subset leaves stragglers that only surface months later.
    brew update && brew upgrade
  elif command -v apt-get >/dev/null; then
    sudo apt-get update && sudo apt-get install --only-upgrade -y ca-certificates && sudo apt-get upgrade -y
  elif command -v dnf >/dev/null; then
    sudo dnf -y upgrade ca-certificates && sudo dnf -y upgrade
  else
    echo "  no supported package manager found; upgrade ca-certificates by hand"
  fi
fi

if $do_venvs; then
  step "Virtualenvs"
  want="$(printf '%s\n' "$PATCHED_VERSIONS" | awk '$1=="certifi"{print $2}')"
  find "$HOME" \( -name node_modules -o -name .git -o -name .Trash \) -prune -o \
       -type d -name site-packages -print 2>/dev/null \
    | while IFS= read -r sp; do
        ls -d "$sp"/certifi-*.dist-info >/dev/null 2>&1 || continue
        root="${sp%%/lib/*}"
        py="${root}/bin/python"; [[ -x "$py" ]] || py="${root}/bin/python3"
        [[ -x "$py" ]] || continue
        before="$("$py" -c 'import certifi;print(certifi.__version__)' 2>/dev/null)"
        # uv-created venvs ship no pip, so python -m pip fails; uv installs into them by path.
        if "$py" -c 'import pip' >/dev/null 2>&1; then
          "$py" -m pip install -q --upgrade "certifi>=${want}" >/dev/null 2>&1
        elif command -v uv >/dev/null; then
          uv pip install -q --python "$py" --upgrade "certifi>=${want}" >/dev/null 2>&1
        fi
        after="$("$py" -c 'import certifi;print(certifi.__version__)' 2>/dev/null)"
        printf '  %-11s -> %-11s %s\n' "${before:-?}" "${after:-FAILED}" "$root"
      done
  echo "  note: a project lockfile still pinning the old certifi will reintroduce it; that is a PR, not a local fix"
fi

if $do_node; then
  step "Node"
  # Reported, not switched: changing someone's default Node major breaks their projects.
  want="$(printf '%s\n' "$PATCHED_VERSIONS" | awk '$1=="node"{print $2}' | tr '|' ' ')"
  for node in $(ls -1 "$(brew --prefix 2>/dev/null || echo /opt/homebrew)"/opt/node*/bin/node \
                      "$HOME"/.nvm/versions/node/*/bin/node \
                      "$HOME"/.local/share/mise/installs/node/*/bin/node 2>/dev/null | sort -u); do
    [[ -x "$node" ]] || continue
    current="$("$node" --version 2>/dev/null | tr -d v)"
    major="${current%%.*}"
    target=""
    for candidate in $want; do [[ "${candidate%%.*}" == "$major" ]] && target="$candidate"; done
    if [[ -z "$target" ]]; then
      printf '  NO FIX    %-10s %s\n' "$current" "$node"
      echo "            this release line has no patched build; move to a patched LTS and remove it"
    elif [[ "$current" == "$target" ]] || \
         [[ "$(printf '%s\n%s\n' "$current" "$target" | sort -V | head -1)" == "$target" ]]; then
      printf '  ok        %-10s %s\n' "$current" "$node"
    else
      printf '  UPGRADE   %-10s -> %-10s %s\n' "$current" "$target" "$node"
    fi
  done
  echo "  upgrade within the major your projects pin, e.g. nvm install <patched>; mise use node@<major>"
fi

if $do_git; then
  step "git"
  # git reads the OS bundle, so it stays exposed even once the package manager's curl is fixed.
  # A global sslCAInfo is reversible, survives OS updates and touches no system file.
  patched_bundle=""
  for candidate in "$(brew --prefix 2>/dev/null)/etc/ca-certificates/cert.pem" \
                   /etc/ssl/certs/ca-certificates.crt; do
    [[ -r "$candidate" ]] || continue
    if ! openssl crl2pkcs7 -nocrl -certfile "$candidate" 2>/dev/null \
         | openssl pkcs7 -print_certs -noout 2>/dev/null \
         | grep -qF "$(printf '%s\n' "$AFFECTED_ROOTS" | head -1)"; then
      patched_bundle="$candidate"; break
    fi
  done
  if [[ -z "$patched_bundle" ]]; then
    echo "  skipped: found no patched bundle to point at; run the package step first"
  else
    existing="$(git config --global --get http.sslCAInfo || true)"
    if [[ "$existing" == "$patched_bundle" ]]; then
      echo "  ok        already pointed at $patched_bundle"
    elif [[ -n "$existing" ]]; then
      echo "  skipped: http.sslCAInfo already set to $existing; leaving your setting alone"
    else
      git config --global http.sslCAInfo "$patched_bundle"
      echo "  set       http.sslCAInfo=$patched_bundle  (undo: git config --global --unset http.sslCAInfo)"
    fi
  fi
fi

if $do_docker; then
  step "Container base images"
  for img in $(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
               | grep -v '<none>' | grep -vE '^(localhost|.*\.local)' | sort -u); do
    echo "  pulling $img"
    docker pull -q "$img" >/dev/null 2>&1 || echo "    not pullable (locally built or private); rebuild it from source"
  done
  echo "  rebuild local images with --no-cache: a cached package-install layer reuses the old bundle"
  echo "  then recreate running containers; a fixed image does not fix a container already started"
fi

cat <<'NOTE'

Done. Re-run `tls_trust_audit.sh` to confirm behaviour changed, not just version numbers.
Not handled here, by design:
  - system trust files (e.g. /etc/ssl/cert.pem) - operator decision, often fleet-wide
  - self-updating desktop apps and Electron bundles - use each app's own updater
  - upstream images/packages with no patched release yet - track, do not hand-patch
NOTE
