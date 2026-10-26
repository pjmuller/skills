#!/usr/bin/env bash
# Read-only: which trust stores on this Mac still trust a distrusted CA, and which clients
# actually accept a certificate from it. Measures only; prints suggested remediation, runs none.
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
do_docker=true
do_probe=true
do_sweep=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --advisory) advisory="$2"; shift 2 ;;
    --no-docker) do_docker=false; shift ;;
    --no-probe) do_probe=false; shift ;;   # offline: classify bundles only
    --quick) do_docker=false; do_sweep=false; shift ;;
    -h|--help)
      sed -n '2,4p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      echo; echo "Usage: tls_trust_audit.sh [--advisory FILE] [--no-docker] [--no-probe] [--quick]"
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -r "$advisory" ]] || { echo "cannot read advisory: $advisory" >&2; exit 2; }
# shellcheck source=/dev/null
. "$advisory"

affected_total=0
exposed_clients=0
suggestions=""
suggest() { suggestions="${suggestions}$1"$'\n'; }
hdr() { printf '\n== %s\n' "$1"; }

# ---------------------------------------------------------------- bundle classification
# A bundle is AFFECTED if it anchors any distrusted root. Enumerate subjects via openssl rather
# than grepping base64: PEM line wrapping differs between producers.
classify() {   # classify FILE -> prints "AFFECTED <roots>" / "safe" / "unreadable"
  local file="$1" subjects root hits=""
  [[ -r "$file" ]] || { echo unreadable; return; }
  subjects="$(openssl crl2pkcs7 -nocrl -certfile "$file" 2>/dev/null \
            | openssl pkcs7 -print_certs -noout 2>/dev/null)"
  [[ -n "$subjects" ]] || { echo unreadable; return; }
  while IFS= read -r root; do
    [[ -n "$root" ]] || continue
    case "$subjects" in *"$root"*) hits="${hits}${hits:+, }${root}" ;; esac
  done <<< "$AFFECTED_ROOTS"
  if [[ -n "$hits" ]]; then echo "AFFECTED $hits"; else echo safe; fi
}

report_bundle() {   # report_bundle FILE
  local file="$1" verdict certs
  verdict="$(classify "$file")"
  certs="$(grep -c 'BEGIN CERTIFICATE' "$file" 2>/dev/null || echo '?')"
  case "$verdict" in
    AFFECTED*) affected_total=$((affected_total + 1))
               printf '  AFFECTED  %-5s certs  %s\n              anchors: %s\n' \
                      "$certs" "$file" "${verdict#AFFECTED }" ;;
    safe)      printf '  safe      %-5s certs  %s\n' "$certs" "$file" ;;
    *)         printf '  ?         unreadable    %s\n' "$file" ;;
  esac
}

# ---------------------------------------------------------------- live probe
# Version numbers are evidence, not proof: a "patched" package can still ship a stale bundle.
# A protected client rejects every test host AND still reaches the control host.
probe() {   # probe LABEL CMD... -- command receives the URL as its last argument
  local label="$1"; shift
  $do_probe || { printf '  %-34s (probe skipped)\n' "$label"; return; }
  local host accepted=0
  while IFS= read -r host; do
    [[ -n "$host" ]] || continue
    "$@" "https://${host}/" >/dev/null 2>&1 && accepted=1
  done <<< "$TEST_HOSTS"
  if [[ $accepted == 1 ]]; then
    exposed_clients=$((exposed_clients + 1))
    printf '  EXPOSED   %-34s accepts a forged chain\n' "$label"
  elif "$@" "https://${CONTROL_HOST}/" >/dev/null 2>&1; then
    printf '  ok        %-34s rejects both, control reachable\n' "$label"
  else
    printf '  BROKEN    %-34s rejects the control host too; investigate\n' "$label"
  fi
}

version_ge() { [[ "$1" == "$2" ]] || [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" == "$2" ]]; }

# Compare against the release line the current version belongs to, not against any line that
# happens to be satisfied: Electron 43.2.0 is NOT fixed by the 42.11.16 build, and Go 1.26.10 is
# not outdated just because a 1.27 line exists. Narrow major.minor -> major -> newer-than-all.
check_version() {   # check_version TOOL CURRENT
  local tool="$1" current="$2" candidates line best="" newest="" cur_major cur_minor
  [[ -n "$current" ]] || return 0
  candidates="$(printf '%s\n' "$PATCHED_VERSIONS" | awk -v t="$tool" '$1==t{print $2}' | tr '|' '\n')"
  [[ -n "$candidates" ]] || return 0
  cur_major="${current%%.*}"
  cur_minor="$(printf '%s' "$current" | cut -d. -f1-2)"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    [[ "$(printf '%s' "$line" | cut -d. -f1-2)" == "$cur_minor" ]] && best="$line"
    newest="$line"
  done <<< "$candidates"
  if [[ -z "$best" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      [[ "${line%%.*}" == "$cur_major" ]] && { [[ -z "$best" ]] || version_ge "$line" "$best"; } && best="$line"
    done <<< "$candidates"
  fi
  if [[ -z "$best" ]]; then
    # No line for this major at all: only a major newer than every published line is acceptable.
    local max_major=0
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      [[ "${line%%.*}" -gt "$max_major" ]] 2>/dev/null && max_major="${line%%.*}"
    done <<< "$candidates"
    if [[ "$cur_major" -gt "$max_major" ]] 2>/dev/null; then
      printf '  ok        %-22s %s\n' "$tool" "$current"; return 0
    fi
    printf '  NO FIX    %-22s %s  (no patched build on this release line; move to %s)\n' \
           "$tool" "$current" "$(printf '%s' "$candidates" | paste -sd'|' -)"
    return 1
  fi
  if version_ge "$current" "$best"; then
    printf '  ok        %-22s %s\n' "$tool" "$current"; return 0
  fi
  printf '  OUTDATED  %-22s %s  (patched: %s)\n' "$tool" "$current" "$best"
  return 1
}

echo "======================================================================"
echo " TLS trust audit - read-only"
echo " advisory : $ADVISORY_NAME"
echo " machine  : $(uname -s) $(sw_vers -productVersion 2>/dev/null || uname -r) ($(sw_vers -buildVersion 2>/dev/null || echo n/a))"
echo " date     : $(date '+%Y-%m-%d %H:%M %Z')"
echo "======================================================================"

# ---------------------------------------------------------------- OS trust state
hdr "Operating system trust"
if [[ "$(uname -s)" == Darwin ]]; then
  while IFS= read -r root; do
    [[ -n "$root" ]] || continue
    if security find-certificate -a -c "$root" \
         /System/Library/Keychains/SystemRootCertificates.keychain 2>/dev/null | grep -q labl; then
      printf '  present   system root keychain: %s\n' "$root"
    fi
  done <<< "$AFFECTED_ROOTS"

  # Apple ships blocklist updates out of band, separately from the OS and from /etc/ssl/cert.pem.
  supplemental=/System/Library/AssetsV2/com_apple_MobileAsset_PKITrustSupplementals
  [[ -d "$supplemental" ]] && printf '  info      trust supplementals asset last changed %s\n' \
      "$(stat -f '%Sm' -t '%Y-%m-%d' "$supplemental")"

  # /etc/ssl/cert.pem is NOT the keychain. Apple's curl/git/python3/ruby/php read this file, and
  # an out-of-band trust update does not touch it.
  printf '  --- /etc/ssl/cert.pem (used by Apple curl, git, python3, ruby, php)\n'
  report_bundle /etc/ssl/cert.pem

  # A pending OS update only helps if its build postdates the advisory. Check, never assume:
  # we nearly waited on an update first offered three weeks before the keys went public.
  offers="$(defaults read /Library/Preferences/com.apple.SoftwareUpdate FirstOfferDateDictionary 2>/dev/null)"
  pending="$(softwareupdate -l 2>/dev/null | awk -F'[:,]' '
    /^\* Label:/ { label = $2; sub(/^ /, "", label) }
    /Title:.*Version:/ { for (i = 1; i <= NF; i++) if ($i ~ /Version/) { v = $(i+1); gsub(/ /, "", v);
                         if (label != "") print label "|" v; label = "" } }')"
  if [[ -n "$pending" ]]; then
    printf '  --- pending OS updates (a build first offered before the advisory cannot carry the fix)\n'
    while IFS='|' read -r label version; do
      [[ -n "$label" ]] || continue
      offered="$(printf '%s\n' "$offers" \
                 | sed -n "s/.*_patch_${version}_[a-z]*\" = \"\([0-9][0-9-]*\).*/\1/p" | head -1)"
      printf '  info      %-44s first offered %s\n' "$label" "${offered:-unknown}"
    done <<< "$pending"
  fi
  printf '  --- manual trust overrides\n'
  security dump-trust-settings 2>/dev/null | sed -n 's/^Cert [0-9]*: /  info      user-trusted root: /p'
else
  for f in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt; do
    [[ -e "$f" ]] && report_bundle "$f"
  done
fi

# ---------------------------------------------------------------- bundles on disk
if $do_sweep; then
  hdr "CA bundles on disk"
  brew_prefix="$(brew --prefix 2>/dev/null || echo /opt/homebrew)"
  # One pass: classifying is the slow part (an openssl fork per bundle), and a `while` loop fed by
  # a pipe runs in a subshell whose counter increments would be lost. Collect to a file instead.
  sweep_out="$(mktemp -t tlssweep)"
  find "$brew_prefix" /usr/local /Library/Frameworks "$HOME" \
       \( -name node_modules -o -name .git -o -name .Trash -o -name '*.app' \) -prune -o \
       -type f \( -name cert.pem -o -name cacert.pem -o -name ca-bundle.crt \
                  -o -name ca-certificates.crt \) -print 2>/dev/null \
    | grep -vE '/(testdata|test|fixtures|dummyserver)/' | sort -u > "$sweep_out"
  while IFS= read -r f; do
    report_bundle "$f"
  done < "$sweep_out"
  rm -f "$sweep_out"
fi

# ---------------------------------------------------------------- clients
hdr "HTTPS clients (live)"
for curl_bin in $(printf '%s\n' /usr/bin/curl "$(command -v curl)" | sort -u); do
  [[ -x "$curl_bin" ]] || continue
  probe "curl $curl_bin" "$curl_bin" -sS -o /dev/null --max-time 12
done
command -v wget >/dev/null && probe "wget" wget -q -O /dev/null --timeout=12

# A tool can use a different store than its runtime: git reads the OS bundle even where the
# package manager's curl is already patched. Probe the tool, not the language.
probe_git() {   # git reaches the HTTP layer on a non-repository URL, so "it failed" is not
  local git_bin="$1" host out accepted=0   # evidence of a TLS rejection. Read the error text.
  $do_probe || { printf '  %-34s (probe skipped)\n' "git $git_bin"; return; }
  while IFS= read -r host; do
    [[ -n "$host" ]] || continue
    out="$(GIT_TERMINAL_PROMPT=0 "$git_bin" ls-remote "https://${host}/probe.git" 2>&1)"
    case "$out" in
      *"SSL certificate problem"*|*"certificate verify failed"*|*"unable to get local issuer"*|\
      *"certificate has expired"*|*"self-signed certificate"*) ;;
      *) accepted=1 ;;   # handshake completed; whatever failed next was not the certificate
    esac
  done <<< "$TEST_HOSTS"
  if [[ $accepted == 1 ]]; then
    exposed_clients=$((exposed_clients + 1))
    printf '  EXPOSED   %-34s completes the handshake on a forged chain\n' "git $git_bin"
  else
    printf '  ok        %-34s rejects both at the certificate\n' "git $git_bin"
  fi
}
for git_bin in $(printf '%s\n' /usr/bin/git "$(command -v git)" | sort -u); do
  [[ -x "$git_bin" ]] || continue
  probe_git "$git_bin"
done

if [[ "$(uname -s)" == Darwin ]] && $do_probe; then
  # Native trust (Safari and every Cocoa app) is evaluated by the OS, not by any bundle.
  first_host="$(printf '%s\n' "$TEST_HOSTS" | head -1)"
  if osascript -l JavaScript -e 'ObjC.import("Foundation");
      var u=$.NSURL.URLWithString("https://'"$first_host"'/");
      var r=$.NSString.stringWithContentsOfURLEncodingError(u,4,null);
      if(!r.isNil()){throw "accepted"}' >/dev/null 2>&1; then
    printf '  ok        %-34s rejects (OS verifier)\n' "macOS native trust"
  else
    exposed_clients=$((exposed_clients + 1))
    printf '  EXPOSED   %-34s accepts a forged chain\n' "macOS native trust"
  fi
fi

hdr "Runtimes (live, every install found)"
$do_probe || echo "  (probes skipped: --no-probe)"
# Python: the default ssl context and certifi are different stores; test both.
py_probe="$(mktemp -t tlsprobe)" || py_probe=""
if [[ -n "$py_probe" ]]; then
  cat > "$py_probe" <<'PY'
import socket, ssl, sys
hosts = sys.argv[1].split(',')
stores = [('ssl-default', ssl.create_default_context())]
try:
    import certifi
    stores.append(('certifi ' + certifi.__version__, ssl.create_default_context(cafile=certifi.where())))
except Exception:
    pass
for label, ctx in stores:
    verdict = 'ok'
    for host in hosts:
        try:
            with socket.create_connection((host, 443), timeout=12) as sock:
                ctx.wrap_socket(sock, server_hostname=host)
            verdict = 'EXPOSED'
        except ssl.SSLError:
            pass
        except Exception:
            verdict = verdict if verdict == 'EXPOSED' else 'unknown'
    print(label, verdict)
PY
fi
hosts_csv="$(printf '%s\n' "$TEST_HOSTS" | paste -sd, -)"
for py in /usr/bin/python3 "$(command -v python3)" \
          "$(brew --prefix 2>/dev/null || echo /opt/homebrew)"/bin/python3.1[0-9]; do
  { $do_probe && [[ -x "$py" && -n "$py_probe" ]]; } || continue
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    case "$line" in
      *EXPOSED) exposed_clients=$((exposed_clients + 1))
                printf '  EXPOSED   %-34s %s\n' "$($py -V 2>&1) ${line% *}" "accepts a forged chain" ;;
      *ok)      printf '  ok        %-34s rejects both\n' "$($py -V 2>&1) ${line% *}" ;;
      *)        printf '  ?         %-34s inconclusive\n' "$($py -V 2>&1) ${line% *}" ;;
    esac
  done <<< "$($py -I "$py_probe" "$hosts_csv" 2>/dev/null)"
done
[[ -n "$py_probe" ]] && rm -f "$py_probe"

# Node, across every version manager, not just the one on PATH.
node_probe="$(mktemp -t tlsprobe).js" || node_probe=""
if [[ -n "$node_probe" ]]; then
  cat > "$node_probe" <<'JS'
const https = require('https');
(async () => {
  let exposed = false;
  for (const host of process.argv.slice(2)) {
    await new Promise((done) => {
      const req = https.get({ host, path: '/', timeout: 12000 }, (res) => { exposed = true; res.destroy(); done(); });
      req.on('error', () => done());
      req.on('timeout', () => { req.destroy(); done(); });
    });
  }
  console.log(exposed ? 'EXPOSED' : 'ok');
})();
JS
fi
for node in $(ls -1 "$(brew --prefix 2>/dev/null || echo /opt/homebrew)"/opt/node*/bin/node \
                    "$HOME"/.nvm/versions/node/*/bin/node \
                    "$HOME"/.local/share/mise/installs/node/*/bin/node \
                    "$HOME"/.volta/tools/image/node/*/bin/node \
                    "$HOME"/.fnm/node-versions/*/installation/bin/node 2>/dev/null \
              | while IFS= read -r candidate; do readlink -f "$candidate" 2>/dev/null || echo "$candidate"; done \
              | sort -u); do
  { $do_probe && [[ -x "$node" && -n "$node_probe" ]]; } || continue
  verdict="$("$node" "$node_probe" $(printf '%s ' $TEST_HOSTS) 2>/dev/null)"
  if [[ "$verdict" == EXPOSED ]]; then
    exposed_clients=$((exposed_clients + 1))
    printf '  EXPOSED   %-34s %s\n' "node $("$node" --version) " "$node"
  else
    printf '  ok        %-34s rejects both\n' "node $("$node" --version) "
  fi
done
[[ -n "$node_probe" ]] && rm -f "$node_probe"

# Java: check what java_home actually resolves to, plus each JDK's blocked.certs.
if [[ "$(uname -s)" == Darwin ]] && command -v /usr/libexec/java_home >/dev/null; then
  default_jdk="$(/usr/libexec/java_home 2>/dev/null)"
  [[ -n "$default_jdk" ]] && printf '  info      default JDK: %s\n' "$default_jdk"
  /usr/libexec/java_home -V 2>&1 | sed -n 's/^ *\([0-9][^ ]*\) .*" \(\/.*\)$/  info      JDK \1 at \2/p'
  for ks in $(/usr/libexec/java_home -V 2>&1 | sed -n 's/^.*" \(\/.*\)$/\1\/lib\/security/p'); do
    blocked="${ks}/blocked.certs"
    [[ -r "$blocked" ]] || continue
    n=0
    while IFS= read -r fp; do
      [[ -n "$fp" ]] || continue
      grep -qi "$fp" "$blocked" && n=$((n + 1))
    done <<< "$AFFECTED_SHA256"
    printf '  %-9s %s blocks %s/16 compromised intermediates\n' \
           "$([[ $n -gt 0 ]] && echo info || echo NOTE)" "$blocked" "$n"
  done
fi

# Go on macOS defers to the OS verifier, so a local probe says nothing about the toolchain.
# Judge the version instead: binaries it builds for Linux/containers carry their own behaviour.
# Version managers keep an alias directory per channel (1.26, 1, latest) holding a real copy, so
# deduplicate on the reported version: the verdict depends on the version, not the path.
seen_go=""
for go in $(ls -1 "$(command -v go)" "$HOME"/.local/share/mise/installs/go/*/bin/go \
                  /usr/local/go/bin/go 2>/dev/null | sort -u); do
  [[ -x "$go" ]] || continue
  go_version="$("$go" version 2>/dev/null | awk '{print $3}' | sed 's/^go//')"
  [[ -n "$go_version" ]] || continue
  case " $seen_go " in *" $go_version "*) continue ;; esac
  seen_go="$seen_go $go_version"
  check_version go "$go_version" || true
done

hdr "Tool versions"
check_version certifi  "$(python3 -c 'import certifi;print(certifi.__version__)' 2>/dev/null)" || true
check_version pip      "$(python3 -m pip --version 2>/dev/null | awk '{print $2}')" || true
for tool in uv mise deno bun rustup pixi conda gh; do
  command -v "$tool" >/dev/null || continue
  check_version "$tool" "$("$tool" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)" || true
done
if command -v brew >/dev/null; then
  check_version homebrew-ca-certificates \
    "$(brew list --versions ca-certificates 2>/dev/null | awk '{print $2}')" || true
fi

# Electron reports its real version in the framework binary, not in the app's Info.plist.
if [[ "$(uname -s)" == Darwin ]]; then
  hdr "Electron apps"
  for app in /Applications/*.app; do
    fw="${app}/Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework"
    [[ -f "$fw" ]] || continue
    ev="$(strings "$fw" 2>/dev/null | grep -m1 -oE 'Electron/[0-9.]+' | cut -d/ -f2)"
    [[ -n "$ev" ]] || continue
    name="$(basename "$app" .app)"
    check_version electron "$ev" >/dev/null 2>&1 \
      && printf '  ok        %-34s electron %s\n' "$name" "$ev" \
      || { printf '  OUTDATED  %-34s electron %s\n' "$name" "$ev"
           suggest "  # ${name}: update via its own updater (Electron ${ev} is below the patched build)"; }
  done
fi

# Containers do no revocation checking, and a fixed image does not fix a container already running.
if $do_docker && command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  hdr "Container images and running containers"
  tmp_pem="$(mktemp -t tlsimg)"
  inspect_container() {   # inspect_container NAME_OR_ID LABEL
    local ref="$1" label="$2" f
    for f in /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem /etc/pki/tls/certs/ca-bundle.crt; do
      if docker cp "${ref}:${f}" "$tmp_pem" >/dev/null 2>&1; then
        case "$(classify "$tmp_pem")" in
          AFFECTED*) printf '  AFFECTED  %s\n' "$label"; return 1 ;;
          safe)      printf '  safe      %s\n' "$label"; return 0 ;;
        esac
      fi
    done
    printf '  none      %-52s no system CA bundle\n' "$label"; return 0
  }
  for img in $(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -v '<none>' | sort -u); do
    cid="$(docker create --entrypoint /bin/true "$img" 2>/dev/null)" || cid="$(docker create "$img" 2>/dev/null)"
    if [[ -z "$cid" ]]; then printf '  ?         %-52s cannot inspect (no shell)\n' "$img"; continue; fi
    inspect_container "$cid" "image $img" || suggest "  docker pull $img   # then rebuild anything FROM it"
    docker rm -f "$cid" >/dev/null 2>&1
  done
  for name in $(docker ps --format '{{.Names}}' 2>/dev/null); do
    inspect_container "$name" "running $name" \
      || suggest "  # recreate running container $name after its image is fixed"
  done
  rm -f "$tmp_pem"
fi

# ---------------------------------------------------------------- overrides
hdr "TLS overrides in the environment"
env | grep -E '^(SSL_CERT_(FILE|DIR)|REQUESTS_CA_BUNDLE|CURL_CA_BUNDLE|NODE_EXTRA_CA_CERTS|NODE_TLS_REJECT_UNAUTHORIZED|GIT_SSL_[A-Z]+|PIP_CERT)=' \
  | sed 's/^/  info      /' || echo "  none      no TLS environment overrides"
for f in "$HOME/.curlrc" "$HOME/.npmrc" "$HOME/.gitconfig" "$HOME/.config/pip/pip.conf"; do
  [[ -f "$f" ]] || continue
  grep -nEi 'cert|cafile|ca_bundle|insecure|sslverify|strict-ssl' "$f" 2>/dev/null \
    | sed "s|^|  info      $f:|"
done

# ---------------------------------------------------------------- summary
echo
echo "======================================================================"
printf ' affected CA bundles on disk : %s\n' "${affected_total:-0}"
printf ' clients accepting a forgery : %s\n' "$exposed_clients"
echo "======================================================================"

if [[ -n "$suggestions" ]]; then
  cat <<'NOTE'

SUGGESTED REMEDIATION - printed, never run by this script.
Run `tls_trust_remediate.sh` for the package upgrades, or copy individual lines.
Operator judgment: anything below that edits a system file or a third-party app.
NOTE
  printf '%s' "$suggestions"
fi

cat <<'NOTE'

Reminder for the interpreting agent:
  - Never resolve a certificate error by disabling verification.
  - OUTDATED is a version comparison; EXPOSED is measured behaviour. Trust the measurement.
  - An EOL base image or OS release will never receive a fixed bundle; it has to be replaced.
NOTE
