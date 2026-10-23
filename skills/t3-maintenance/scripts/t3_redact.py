"""Deterministic secret redaction for text kept long-term (the T3 thread archive).

`redact(text)` → (text, Counter of categories). Two passes:
1. secret-named assignments: `API_TOKEN=…`, `"password": "…"`, `--token …`, `STRIPE_KEY: …`. The key
   stays; keys that name *where* a secret lives (`TOKEN_FILE`, `password_reset_url`, `session_id`)
   and values that are code, placeholders or plain words stay too. Plain config
   (`RAILS_ENV=production`, `PORT=3000`) is never touched.
2. one combined regex, first match wins at each position: private-key blocks · URLs (password in
   `scheme://user:pass@`, secret-named query params, vendor tokens inside; path segments stay so
   links keep working) · `Authorization:` / `Bearer` / `Cookie:` · `curl -u user:pass` · vendor
   tokens with a known prefix · a long random-looking run with no context (≥ 32 chars, letters and
   digits interleaved, not hex). Commit hashes, UUIDs, paths, `profile_…` ids, Message-IDs, ssh
   public keys and runs named as ids (`id: …`, `sha256:`, `drive-get …`) survive.

Values become `[redacted:<category>]`; markers never match again (idempotent). Known misses: hex /
UUID-shaped keys and short passwords outside a secret-named key, secrets in prose, capability URLs
(share links). Redaction never replaces rotating a leaked credential. Bump VERSION when the rules
change; `t3-thread-archive scrub` rewrites rows redacted under an older version.
"""

from __future__ import annotations

import math
import re
from collections import Counter

VERSION = 1


def mark(category: str) -> str:
    return f"[redacted:{category}]"


def _skip(value: str) -> bool:
    return value.startswith(("[redacted", "$", "<", "{", "%"))


# --- vendor tokens: known prefixes, near-zero false positives --------------------------------

_VENDOR = [
    ("aws-key-id", r"(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|AIPA)[A-Z0-9]{16}"),
    ("github-token", r"gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{40,255}"),
    ("gitlab-token", r"glpat-[A-Za-z0-9_-]{20,}"),
    ("slack-token", r"xox[abposr]-[A-Za-z0-9-]{10,}|xapp-\d-[A-Za-z0-9-]{10,}"),
    ("ai-api-key", r"sk-(?:ant-|proj-|svcacct-|admin-|or-v1-)?[A-Za-z0-9_-]{20,}"
                   r"|(?:xai|pplx)-[A-Za-z0-9]{32,}|gsk_[A-Za-z0-9]{40,}|hf_[A-Za-z0-9]{30,}"),
    ("stripe-key", r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}|whsec_[A-Za-z0-9]{20,}"),
    ("google-credential", r"AIza[0-9A-Za-z_-]{35}|ya29\.[0-9A-Za-z_-]{20,}|1//0[0-9A-Za-z_-]{20,}"
                          r"|4/0A[0-9A-Za-z_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,}"),
    ("jwt", r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("mapbox-secret", r"sk\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("clickup-token", r"pk_\d{3,}_[A-Z0-9]{20,}"),
    ("sendgrid-key", r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
    ("package-token", r"npm_[A-Za-z0-9]{36}|pypi-[A-Za-z0-9_-]{50,}"),
    ("cloud-token", r"HRKU-[A-Za-z0-9_-]{20,}|do[por]_v1_[a-f0-9]{64}|shp(?:at|ss|ca|pa)_[a-fA-F0-9]{32}"
                    r"|dp\.(?:st|ct|sa|scim)\.[A-Za-z0-9_.-]{20,}"),
    ("telegram-bot-token", r"\d{8,10}:AA[A-Za-z0-9_-]{33}"),
    ("rootcause-token", r"rc_[a-z]+_[A-Za-z0-9]{24,}"),
    ("prefixed-secret", r"[a-z]{2,10}_(?:live|prod|secret)_[A-Za-z0-9]{16,}"),
]
_VENDOR_ALT = "|".join(f"(?P<vnd{i}>{p})" for i, (_, p) in enumerate(_VENDOR))
VENDOR = re.compile(rf"(?<![A-Za-z0-9_])(?:{_VENDOR_ALT})(?![A-Za-z0-9_])")


def _vendor(m: re.Match) -> str:
    return _VENDOR[int(m.lastgroup[3:])][0]


def vendor_of(value: str) -> str | None:
    m = VENDOR.fullmatch(value)
    return _vendor(m) if m else None


# --- pass 1: secret-named assignments -----------------------------------------------------------

# Lowercase-led words must not run on into another word (`tokenizer`, `tokens`, `salted`);
# a bare `_KEY` suffix counts only in SHOUTING env style (`MAPBOX_KEY`, not `cache_key`).
# Searched in `text.lower()` (5x faster than re.I); the original text decides `(?![a-z])`.
_SECRET_WORD = re.compile(
    r"token|secret|passw(?:or)?d|passwd|pwd|api[_-]?key|apikey|access[_-]?key|private[_-]?key"
    r"|credential|auth[_-]?key|signing[_-]?key|session[_-]?(?:key|token)|dsn|salt|encryption[_-]?key"
    r"|master[_-]?key|license[_-]?key|bearer")
_ENV_KEY = re.compile(r"(?<=[_-])KEY(?![A-Za-z])")
_KEY_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
# last word of a key that names where/what a secret is, not the secret itself
_KEY_META = frozenset(
    "url uri urls file path dir env name names id ids count length len type ttl expires expiry at in limit max "
    "min budget usage header prefix ref arn policy rotation field param column label hint help reset confirm "
    "confirmation required enabled kind format endpoint host scope scopes version mode source provider".split())
_ASSIGN = re.compile(  # value: JSON-escaped quotes (`\"password\": \"…\"`) · quoted (spaces, escapes) · bare
    r"(?P<sep>(?:\\?[\"'])?[ \t]*(?:=>|:=|=|:)[ \t]*|[ \t]+)"
    r"(?:\\(?P<eq>[\"'])(?P<eqval>(?:(?!\\(?P=eq)).){6,500}?)\\(?P=eq)"
    r"|(?P<q>[\"'])(?P<qval>(?:\\.|(?!(?P=q))[^\\\n]){6,500}?)(?P=q)"
    r"|(?P<val>[^\s\"'`,;&)}\]\\]{8,500}))")
_PLACEHOLDER = re.compile(
    r"^(?:\*{3}|x{3,}|\.{3}|…|op://|env:|vault:|arn:|/|~/|\./|\.\./|https?://|\\"
    r"|true$|false$|null$|nil$|none$|undefined$|changeme|example|your[_-]|my[_-]|dummy|redacted|placeholder"
    r"|fake|sample|test$|secret$|password$|token$)", re.I)
_CODE = re.compile(r"[()\[\]{}]|^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$|^[A-Za-z_-]+$|^\d+(?:\.\d+)+$")
# a quoted literal is code only when it reads as a word or constant; mixed-case letters are a password
_WORD = re.compile(r"^(?:[a-z_-]+|[A-Z_]+|[A-Z][a-z]+(?:[_-][a-z]+)*|\d+(?:\.\d+)+)$")


def _key_words(key: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", key)]


_CAMEL = re.compile(r"[A-Z]?[a-z]+(?:[A-Z][a-z]{2,}|Id|Of|To|By|At|On|In|Is|Or|Up|[A-Z]{2,4}(?![a-z]))*")  # accessTokenValue, parseHTTPHeader
_CODE_SPAN = re.compile(r"[|&;(){}\[\]<>+=`]|~/|\b(?:and|or|if|then|else|echo|grep)\b")  # between two literals


def secret_value(value: str, quoted: bool = False) -> bool:
    if _skip(value) or _PLACEHOLDER.match(value):
        return False
    if not quoted:  # letters only = an identifier, unless the case flips like a random token
        return not _CODE.search(value) or (value.isalpha() and len(value) >= 16 and not _CAMEL.fullmatch(value)
                                            and _switches(value) >= 0.3 * len(value))
    words = value.split()
    if value != value.strip():
        return False  # `" + token, "`: the gap between two literals
    if len(words) > 1:  # "aB1! cD2@" is a passphrase; "the API token to use" is not
        if _CODE_SPAN.search(value):
            return False
        return sum(word.strip(".,:;!?'\"").isalpha() for word in words) < len(words) * 2 / 3
    return not _WORD.match(value)


def _secret_words(text: str) -> list[tuple[int, int]]:
    lower = text.lower()
    if len(lower) != len(text):  # a few non-ASCII letters lowercase to two chars
        lower = "".join(ch if len(ch.lower()) != 1 else ch.lower() for ch in text)
    found = [(m.start(), m.end()) for m in _SECRET_WORD.finditer(lower)
             if not (m.end() < len(text) and text[m.end()].islower() and text[m.end()].isascii())]
    return sorted(found + [(m.start(), m.end()) for m in _ENV_KEY.finditer(text)])


def _assignments(text: str, hits: Counter) -> str:
    out, done = [], 0
    for word_start, word_end in _secret_words(text):
        if word_start < done:
            continue
        start, end = word_start, word_end
        while start > max(done, word_start - 60) and text[start - 1] in _KEY_CHARS:
            start -= 1
        while end < min(len(text), word_end + 30) and text[end] in _KEY_CHARS:
            end += 1
        key = text[start:end]
        if text[max(0, start - 3):start] == "://":
            continue  # URL userinfo: pass 2 keeps the user, redacts the password
        m = _ASSIGN.match(text, end)
        if not m or (m["sep"].strip() == "" and not key.startswith("--")):
            continue
        group = next(g for g in ("eqval", "qval", "val") if m[g])
        value = m[group]
        words = _key_words(key)
        if words and words[-1] in _KEY_META or not secret_value(value, quoted=group != "val"):
            continue  # the value still goes through pass 2
        category = vendor_of(value) or "secret-assignment"
        hits[category] += 1
        out.append(text[done:m.start(group)] + mark(category))
        done = m.end(group)
    return "".join(out) + text[done:] if out else text


# --- pass 2: one combined regex ---------------------------------------------------------------

PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----(?:[A-Za-z0-9+/=\s:,-]|\\[nr])*?"
                r"(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|(?=[^A-Za-z0-9+/=\s:,\\-])|\Z)")
_URL = r"(?P<url>\b[a-z][a-z0-9+.-]{1,20}://(?:\[redacted:[a-z-]+\]|[^\s\"'<>`)\]])+)"  # a marker doesn't end it
AUTH = re.compile(r"(?P<auth>(?i:\b(?:proxy-)?authorization[\"']?[ \t]*[:=][ \t]*[\"']?(?:(?:bearer|basic|token|bot|digest"
         r"|apikey|key)[ \t]+)?)|(?i:\bbearer[ \t]+))(?P<authval>[A-Za-z0-9._~+/=:-]{8,})")
# The rest of the line, quoted values included; inside `-H 'Cookie: …'` up to that closing quote.
COOKIE = re.compile(r"(?P<cookie>(?:^|(?<=[\s>])|(?P<cq>[\"']))(?i:(?:set-)?cookie)[ \t]*:[ \t]*)"
                    r"(?P<cookieval>(?(cq)(?:\\.|(?!(?P=cq))[^\r\n\\])+|[^\r\n]+))")
CURL_USER = re.compile(r"(?P<curlu>(?:\s-u|\s--user)[ \t]+[\"']?[^\s:\"']+:)(?P<curlpw>[^\s\"']+)")
_GENERIC = r"(?P<gen>(?<![A-Za-z0-9_+/.-])[A-Za-z0-9_+/-]{32,}={0,2}(?![A-Za-z0-9_+/=]))"
URL_OR_RUN = re.compile(f"{_URL}|{_GENERIC}")  # one regex: a URL's path segments never count as runs
# a cheap literal pre-check before the full vendor regex (most texts hold no vendor prefix at all)
_VENDOR_HINT = re.compile(r"AKIA|ASIA|AGPA|AIDA|AROA|ANPA|AIPA|gh[pousr]_|github_pat_|glpat-|xox|xapp-|sk-|xai-|pplx-"
                          r"|gsk_|hf_|sk_|rk_|whsec_|AIza|ya29\.|1//0|4/0A|GOCSPX-|eyJ|pk_|SG\.|npm_|pypi-|HRKU-"
                          r"|_v1_|shp|dp\.|:AA|rc_|_live_|_prod_|_secret_")

# not anchored: one match can hold several URLs (`sed "s#pg://a:b@h#pg://c:d@h#"`)
_URL_USERINFO = re.compile(r"(?<![A-Za-z0-9+.-])([a-z][a-z0-9+.-]*://)([^\s:/@?#]*):([^\s/@?#]+)@", re.I)
_URL_TOKEN_USER = re.compile(r"(?<![A-Za-z0-9+.-])([a-z][a-z0-9+.-]*://)([A-Za-z0-9_-]{16,})@", re.I)
_URL_QUERY = re.compile(
    r"([?&;#](?:[A-Za-z0-9_.-]*(?:token|secret|passw(?:or)?d|pwd|api[_-]?key|apikey|sig|signature|credential"
    r"|session|auth)[A-Za-z0-9_.-]*|key|code|x-amz-(?:signature|credential|security-token))=)([^&\s#]{6,})", re.I)
_URL_PARAM_PLAIN = frozenset({"authuser", "token_name", "session_redirect", "session_id", "auth_type"})
_URL_SECRET_PATH = [
    ("slack-webhook", re.compile(r"(hooks\.slack\.com/(?:services|workflows|triggers)/)(?!\[redacted)[A-Za-z0-9/]+")),
    ("telegram-bot-token", re.compile(r"(api\.telegram\.org/(?:file/)?bot)(?!\[redacted)[^/\s]+")),
]

# `profile_…` / `tab-…` ids carry a label; these labels mean the run itself is a credential
_SECRET_LABELS = frozenset("key api token secret sess session pat auth live prod access refresh bearer private "
                           "pass pw pwd sk rk ak cred creds sig".split())
# a run right after `id: ` / `sha256:` / `ref=` names something, it does not unlock it
_ID_CONTEXT = re.compile(
    r"(?i:(?:\b|_|-)(?:\w*id|ids|ref|sha\d*|hash|digest|checksum|etag|nonce|guid|ssh-\w+|ecdsa-[\w-]+"
    r"|site-verification|drive[\w-]*|sheets?[\w-]*|slides[\w-]*|deck|docs?|documents?|folders?|spreadsheets?"
    r"|presentations?))[\"']?[ \t]*[:=]?[ \t]*[\"']?$")


def entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _char_class(ch: str) -> int:
    return 0 if ch.islower() else 1 if ch.isupper() else 2 if ch.isdigit() else 3


def _switches(s: str) -> int:
    classes = [_char_class(ch) for ch in s]
    return sum(1 for a, b in zip(classes, classes[1:]) if a != b and a < 3 and b < 3)


def looks_random(run: str) -> bool:
    """A context-free run worth redacting: letters and digits interleaved, not hex, high entropy."""
    body = run.rstrip("=")
    if re.fullmatch(r"[0-9a-fA-F-]+", body) or re.match(r"sha(?:1|256|384|512)-", body):
        return False  # commit / content hashes, UUIDs, SRI integrity
    if (label := re.match(r"([a-z]{2,12})[_-]", body)) and label[1] not in _SECRET_LABELS:
        return False  # typed ids: profile_…, tab-…, msg_…
    if sum(ch.isdigit() for ch in body) < 2 or sum(ch.isalpha() for ch in body) < 8:
        return False
    return _switches(body) >= 0.2 * len(body) and entropy(body) >= 4.0


def _url(url: str, hits: Counter) -> str:
    def userinfo(m: re.Match) -> str:
        if _skip(m[3]):
            return m[0]
        hits["url-password"] += 1
        return f"{m[1]}{m[2]}:{mark('url-password')}@"

    def token_user(m: re.Match) -> str:
        if not looks_random(m[2]) and not re.fullmatch(r"[0-9a-f]{32}", m[2]):
            return m[0]
        hits["url-token"] += 1
        return m[1] + mark("url-token") + "@"

    def query(m: re.Match) -> str:
        if _skip(m[2]) or m[1][1:-1].lower() in _URL_PARAM_PLAIN:
            return m[0]
        hits["url-param"] += 1
        return m[1] + mark("url-param")

    def path(m: re.Match, category: str) -> str:
        hits[category] += 1
        return m[1] + mark(category)

    def vendor(m: re.Match) -> str:
        hits[_vendor(m)] += 1
        return mark(_vendor(m))

    url = _URL_USERINFO.sub(userinfo, url)
    url = _URL_TOKEN_USER.sub(token_user, url)
    url = _URL_QUERY.sub(query, url)
    for category, rx in _URL_SECRET_PATH:
        url = rx.sub(lambda m, c=category: path(m, c), url)
    return VENDOR.sub(vendor, url)


def redact(text: str) -> tuple[str, Counter]:
    hits: Counter = Counter()

    def count(category: str, replacement: str) -> str:
        hits[category] += 1
        return replacement

    def auth(m: re.Match) -> str:
        value = m["authval"]  # a recognized header: only placeholders and plain words stay
        if _skip(value) or _PLACEHOLDER.match(value) or _WORD.match(value):
            return m[0]
        return count("auth-header", m["auth"] + mark("auth-header"))

    def cookie(m: re.Match) -> str:
        if _skip(m["cookieval"]) or not m["cookieval"].strip():
            return m[0]
        return count("cookie", m["cookie"] + mark("cookie"))

    def curl_user(m: re.Match) -> str:
        if _skip(m["curlpw"]) or m["curlpw"].isdigit():
            return m[0]
        return count("basic-auth", m["curlu"] + mark("basic-auth"))

    def url_or_run(m: re.Match) -> str:
        if m["url"]:
            return _url(m["url"], hits)
        run, after = m["gen"], text[m.end():m.end() + 1]
        if run.startswith("/") or after == "@" or _ID_CONTEXT.search(text[max(0, m.start() - 24):m.start()]):
            return m[0]  # absolute paths, mail Message-IDs, named ids / public keys / Drive file ids
        if not looks_random(run):
            return m[0]
        return count("high-entropy", mark("high-entropy"))

    # Order matters: a key block first (its body would otherwise be cut by a later marker), vendor
    # tokens before headers and URLs so those see a marker, URLs and runs last in one regex.
    if "PRIVATE KEY" in text:
        text = PRIVATE_KEY.sub(lambda m: count("private-key", mark("private-key")), text)
    text = _assignments(text, hits)
    if _VENDOR_HINT.search(text):
        text = VENDOR.sub(lambda m: count(_vendor(m), mark(_vendor(m))), text)
    lower = text.lower()
    if "author" in lower or "bearer" in lower:
        text = AUTH.sub(auth, text)
    if "cookie" in lower:
        text = COOKIE.sub(cookie, text)
    if " -u" in text or "--user" in text:
        text = CURL_USER.sub(curl_user, text)
    return URL_OR_RUN.sub(url_or_run, text), hits
