# Matching scope

`--host H` means the actual destination, `https://H` on port 443. Candidate selection can cover its registrable
domain; delivery never expands to that domain. Both `bw_once.py:match_scope` and `broker.swift:matchScope` enforce:

| Saved URI rule | Host-only request |
| --- | --- |
| Default / null | bw-once's per-vault default, normally Base domain |
| Base domain (0) | Same registrable domain, using ICANN **and PRIVATE** public suffix rules |
| Host (1) | Same DNS hostname; absent port or 443 only |
| StartsWith (2), Exact (3), Regex (4) | Excluded: hostname cannot prove full URL/path/query restrictions |
| Never (5), unknown/malformed rule | Excluded URI; another eligible URI on that item can still match |

HTTP(S) and scheme-less saved URIs only. ASCII DNS / punycode supported; literal Unicode hosts, userinfo,
backslashes, malformed ports and control characters fail closed. Base domain excludes IPs, local/unknown TLDs,
single-label hosts and bare public suffixes; an explicit Host rule can match a validated local hostname/IP.
This is a conservative subset of Bitwarden, not full browser-autofill parity.

Examples: `google.com` → `accounts.google.com`; `example.co.uk` → `login.example.co.uk`.
`google.com.evil.com`, `evilgoogle.com`, and another tenant on `github.io`, `pages.dev` or `vercel.app` do not match.
A saved Host rule on `google.com` excludes `accounts.google.com`; Exact on any URL is unavailable through this
host-only interface. `--id` and username filtering never bypass URI rules. Usernames keep existing full-value,
case-insensitive equality, not substring matching.

## Defaults and equivalent domains

Bitwarden's default is client/account state, separate from saved URI overrides; organization policy can supply
another default. Its CLI item responses do **not** include the resolved default. bw-once does not read browser
storage, CLI databases or organization policies. In `~/.config/bw-once/vaults.json`, each account may set
`"default_match": "host"`, `"exact"` or `"never"`; omitted/`"base_domain"` means Base domain. Invalid values stop
before unlock. Mirror any stricter client or organization default here **before using bw-once**; otherwise it
explicitly assumes Base domain. Explicit saved URI overrides still win, as in Bitwarden.

`doctor` and the Touch ID panel disclose that setting and the lack of browser-default import. Equivalent-domain
aliases (user-defined and Bitwarden's global list) are unsupported; bw-once never expands to another registrable
domain such as `apple.com` → `icloud.com`, even if the extension offers it.

## Approval and retained grants

The pre-touch green box shows actual destination, registrable domain, defaults and excluded rule types. Decrypted
item rules are available only after the touch: the result, pick candidates and release notice show `match_rule`
and `matched_uri_host` (never raw URI paths/queries). Multiple matches retain the existing explicit pick flow.
All vaults lock before delivery; account/email checks and vault selection remain independent of login usernames.

Session allowlists and re-copy sockets use the **exact destination host**, not its base domain. Same-domain
siblings require their own approval. A retained re-copy is the already-approved field for that destination,
login, vault and thread, for at most 15 minutes; it does not re-read rules after edits while vaults are locked.
Stop/restart sessions after changing defaults; wait out retained re-copy grants after changing URI rules.
The matching update uses v2 socket names: old grants cannot answer new copy requests. Old sessions can still be
queried/stopped with `session status` / `session stop`; stop them before starting a replacement.

## Public suffix snapshot and verification

`scripts/public_suffix_list.dat`: official snapshot **2026-10-22**, MPL-2.0 (notice retained), including PRIVATE,
wildcards and exceptions. Submitter-contact comments are omitted; rules and license notices are unchanged. Python reads it; `build_broker.py` embeds the same rules into the Swift binary before
signing. No online lookup or mutable runtime list affects the compiled broker. Refresh from
[publicsuffix.org](https://publicsuffix.org/list/public_suffix_list.dat), review the diff, run the shared
`tests/matching_cases.json` contract in both paths plus delivery tests, then reinstall. The installer compares
source/data/build script and rebuilds; the next use may need the normal update touch.

A stale list may miss newly delegated/private suffix boundaries. Refresh with releases; no TTL/network fallback
silently broadens matching. The tests use synthetic credentials and cover sibling boundaries, private suffixes,
PSL wildcards/exceptions, rule overrides, ambiguity, locking and origin rejection. Do not retrieve a real password
just to verify this behavior. Full-URL support is a separate extension requiring URL-bound approval and delivery.

Verified 2026-10-26 against [official URI semantics](https://bitwarden.com/help/uri-match-detection/),
[rule enum values](https://bitwarden.com/help/cli/#enums),
[per-URI matching](https://github.com/bitwarden/clients/blob/main/libs/common/src/vault/models/view/login-uri.view.ts),
[private-domain parsing](https://github.com/bitwarden/clients/blob/main/libs/common/src/platform/misc/utils.ts), and
[client defaults and policies](https://github.com/bitwarden/clients/blob/main/libs/common/src/autofill/services/domain-settings.service.ts).
