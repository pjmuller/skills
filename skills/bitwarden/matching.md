# Matching scope

`--host H` means the actual destination, `https://H` on port 443. Candidate selection can cover its registrable
domain; delivery never expands to that domain. `bw_once.py:match_scope` and `broker.swift:matchScope` enforce the
same contract (`tests/matching_cases.json`). Candidates come from an unfiltered `bw list items` inside the helper
(bw's `--url`/`--search` use other semantics), then this per-URI filter.

| Saved URI rule | Host-only request |
| --- | --- |
| Default / null | bw-once's per-vault default, normally Base domain |
| Base domain (0) | Same registrable domain, using ICANN **and PRIVATE** public suffix rules |
| Host (1) | Same DNS hostname; absent port or 443 only |
| StartsWith (2), Exact (3), Regex (4) | Excluded: a hostname cannot prove full URL/path/query restrictions |
| Never (5), unknown/malformed rule | Excluded URI; another eligible URI on that item can still match |

HTTP(S) and scheme-less saved URIs only. ASCII DNS / punycode; literal Unicode hosts, userinfo, backslashes,
malformed ports and control characters fail closed. Base domain excludes IPs, local/unknown TLDs, single-label
hosts and bare public suffixes; an explicit Host rule can match a validated local hostname/IP. A conservative
subset of Bitwarden, not browser-autofill parity. A host with an `xn--` label is accepted but flagged as a
possible lookalike in the approval window and Terminal (shown raw: decoding would hide the imitation).

Examples: `google.com` → `accounts.google.com`; `example.co.uk` → `login.example.co.uk`. No match:
`google.com.evil.com`, `evilgoogle.com`, another tenant on `github.io`/`pages.dev`/`vercel.app`; a saved Host rule
on `google.com` excludes `accounts.google.com`. `--id` and username filtering never bypass URI rules; usernames
match full-value, case-insensitive.

## Defaults and equivalent domains

Bitwarden's default match is client/account state (or organization policy), and CLI item responses do **not**
include it. bw-once reads no browser storage, CLI database or policy: in `~/.config/bw-once/vaults.json` each
account may set `"default_match": "host"`, `"exact"` or `"never"` (omitted/`"base_domain"` = Base domain; invalid
stops before unlock). Mirror any stricter client or organization default **before using bw-once**. Explicit
per-URI rules still win. Equivalent-domain aliases (user or global list) are unsupported: never `apple.com` →
`icloud.com`.

## Approval and retained grants

The green box shows destination, registrable domain, defaults and excluded rule types; rules are decrypted only
after the touch, so results, pick candidates and the release notice carry `match_rule` and `matched_uri_host`
(never URI paths/queries). Session allowlists and re-copy sockets use the **exact destination host**: same-domain
siblings need their own approval. A re-copy grant does not re-read rules: after editing URI rules wait out the
15 min; after changing defaults restart sessions. Sockets are `-v2` names; a pre-v2 session can only be
`session status`/`stop`ped: stop it before starting a replacement.

## Public suffix snapshot

`scripts/public_suffix_list.dat`: official snapshot **2026-10-22**, MPL-2.0 (notice retained), PRIVATE section,
wildcards and exceptions; submitter-contact comments omitted. Python reads it; `build_broker.py` embeds it in the
Swift binary before signing; no online lookup. A stale list may miss new suffix boundaries; no TTL/network
fallback silently broadens matching.

Refresh with releases: download from [publicsuffix.org](https://publicsuffix.org/list/public_suffix_list.dat),
review the diff, run `tests/matching_cases.json` in both paths plus delivery tests, reinstall (the installer
rebuilds on change; the next use may need the update touch). Tests use synthetic credentials: never retrieve a
real password to verify matching. Full-URL support would need URL-bound approval and delivery.

Verified 2026-10-26 against [URI semantics](https://bitwarden.com/help/uri-match-detection/),
[rule enums](https://bitwarden.com/help/cli/#enums),
[per-URI matching](https://github.com/bitwarden/clients/blob/main/libs/common/src/vault/models/view/login-uri.view.ts),
[private-domain parsing](https://github.com/bitwarden/clients/blob/main/libs/common/src/platform/misc/utils.ts),
[defaults and policies](https://github.com/bitwarden/clients/blob/main/libs/common/src/autofill/services/domain-settings.service.ts).
