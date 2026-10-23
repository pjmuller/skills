"""t3_redact rules + the archive paths that must apply them (write, import, scrub).

  uv run --with pytest pytest test_t3_redact.py

Every secret here is synthetic and assembled at runtime (prefix + seeded random body): the repo never
holds a token-shaped literal for push protection or a scanner to trip on.
"""

from __future__ import annotations

import random
import sqlite3
import stat
import string
import subprocess
import sys
import time
from pathlib import Path

import pytest
import t3_archive
import t3_redact
from t3_redact import redact
from v2_fixture import Store

rng = random.Random(7)
B62 = string.ascii_letters + string.digits


def rand(n: int, alphabet: str = B62) -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


# (category, text, secret that must disappear)
def positives() -> list[tuple[str, str, str]]:
    cases = []
    def add(category: str, template: str, secret: str) -> None:
        cases.append((category, template.format(secret), secret))
    add("github-token", "export GITHUB_TOKEN={}", "gh" + "p_" + rand(36))
    add("github-token", "remote: https://x-access-token:{}@github.com/o/r.git", "gh" + "s_" + rand(36))
    add("ai-api-key", "using key {} for the call", "sk-" + "ant-api03-" + rand(80))
    add("stripe-key", "STRIPE_KEY: {}", "sk_" + "live_" + rand(24))
    add("google-credential", "maps key {}", "AI" + "za" + rand(35))
    add("aws-key-id", "aws_access_key_id = {}", "AK" + "IA" + rand(16, string.ascii_uppercase + string.digits))
    add("slack-token", "SLACK={}", "xo" + "xb-" + rand(12, string.digits) + "-" + rand(24))
    add("clickup-token", "clickup {}", "pk" + "_" + rand(8, string.digits) + "_" + rand(32, string.ascii_uppercase + string.digits))
    add("jwt", "id_token {}", "ey" + "J" + rand(20) + ".ey" + "J" + rand(40) + "." + rand(43))
    add("secret-assignment", "API_TOKEN={}", rand(40))
    add("secret-assignment", '{{"password": "{}", "user": "pj"}}', rand(14))
    add("secret-assignment", "client_secret: '{}'", rand(32))
    add("secret-assignment", "rc login --token {}", rand(28))
    add("secret-assignment", "MAPBOX_KEY={}", rand(30))
    add("secret-assignment", "API_KEY={}", "".join(rng.choice("aA") and rng.choice(string.ascii_letters) for _ in range(24)) + "Qx")  # letters only
    add("secret-assignment", 'DB_PASSWORD="{}"', "aB1! cD2@ eF3#")  # passphrase with spaces
    add("secret-assignment", "password = '{}'", 'it"s-' + rand(8))  # the other quote inside
    add("secret-assignment", 'secret: "{}"', 'x\\"y' + rand(8))  # escaped quote inside
    add("secret-assignment", '{{\\"db\\": {{\\"password\\": \\"{}\\"}}}}', rand(12))  # JSON inside a JSON string
    add("secret-assignment", "PASSWORD={}", rand(9, string.digits))  # short, all digits: the key decides
    add("secret-assignment", "+  api_secret: {}", rand(24, "0123456789abcdef"))  # diff line, hex value
    add("secret-assignment", "accessToken = \"{}\"", rand(30))
    add("auth-header", "curl -H 'Authorization: Bearer {}' https://api.example.com", rand(40))
    add("auth-header", "Authorization: Basic {}", rand(28) + "==")
    add("auth-header", "Authorization: Bearer {}", rand(10, string.ascii_letters) + "." + rand(10, string.ascii_letters))  # code-shaped
    add("auth-header", "-H 'authorization: token {}'", rand(16, string.ascii_letters))  # letters only
    add("cookie", "Cookie: {}", "session=" + rand(30) + "; theme=dark")
    add("cookie", "Cookie: {}; theme=dark", 'session="' + rand(24) + '"')  # quoted value
    add("cookie", "Set-Cookie: {}; Path=/; HttpOnly", 'sid="' + rand(24) + '"')
    add("cookie", "curl -H 'Cookie: {}' https://example.com", "a=1; session=" + rand(24))  # stops at the quote
    add("cookie", 'curl -H "Cookie: {}" x', 'session=\\"' + rand(24) + '\\"')  # escaped quotes
    add("basic-auth", "curl -u admin:{} https://example.com", rand(12))
    add("url-password", "DATABASE_URL=postgres://app:{}@db.example.com:5432/app", rand(18))
    add("url-param", "GET https://example.com/cb?state=1&code={}", rand(24))
    add("url-password", "sed -i 's#DB=postgres://a:b@h/x#DB=postgres://app_rw:{}@#' .env", rand(12))  # 2 URLs, 1 match
    add("url-param", "https://bucket.s3.amazonaws.com/f.pdf?X-Amz-Signature={}", rand(64, "0123456789abcdef"))
    add("slack-webhook", "post to https://hooks.slack.com/services/{}", "T" + rand(10) + "/B" + rand(10) + "/" + rand(24))
    add("private-key", "{}", "-----BEGIN OPENSSH PRIVATE KEY-----\n" + rand(70) + "\n" + rand(70) + "\n-----END OPENSSH PRIVATE KEY-----")
    add("private-key", 'key = "{}"', "-----BEGIN RSA PRIVATE KEY-----\\n" + rand(64) + "\\n" + rand(40) + " …[+900 chars]")
    add("high-entropy", "the value {} was printed", rand(40))
    add("high-entropy", "aws secret {}", rand(30) + "/" + rand(9) + "+")
    return cases


NEGATIVES = [
    "commit 3f2a9c1e5b7d8f0a1b2c3d4e5f60718293a4b5c6 on main",
    "thread mcp:5d870b61-6945-4f60-a1b2-d74ecce0b54d and sha256:" + "ab" * 32,
    "/Users/pjmuller/code/pjmuller/skills/skills/t3-maintenance/scripts/test_t3_archive.py",
    "RAILS_ENV=production PORT=3000 LOG_LEVEL=debug max_tokens: 4096 tokenizer: unicode61",
    "token = request.headers['X-Token']; api_key = os.environ.get('API_KEY'); password: ENV.fetch('PW')",
    "GITHUB_TOKEN=$GITHUB_TOKEN TOKEN=${TOKEN} PASSWORD=<your password> SECRET=*** api_key: changeme",
    "TOKEN_FILE=/Users/pj/.config/token password_reset_url: https://example.com/reset session_id: 1234-5678",
    "pjgitsync-2026-10-23-macbook_setup-r1-attempt-2 test_user_authentication_service_handler_v2_spec",
    "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCDEFG/edit?authuser=1",
    "integrity sha512-" + "A1b2C3d4" * 11 + "==",
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK" + "q7Zr4XpL2m9Wn3Vb8Yc1Td5Ue6Sf0Rg" + " pj@mac",
    "Message-ID: <CAOm" + "x7Yk2Pq9Lr4Wn8Vb3Zc6Td1Uf5Sg0Ah2Bj7Ck" + "@mail.gmail.com>",
    "profile_" + "y7Jw641RIFXIpeUcfikk6InrWvMG1qxv" + " tab-" + "vhsp38MX9T4FiLJXgucAey3Yj1ivhNLY",
    "piitoken.go:42: func Detokenize(x string) error; docker run -u 1000:1000 img",
    "token: accessTokenValueForUser password: getIdFromUrlForUserName",
    "The token usage was high; the password is in Bitwarden; rotate the secret monthly.",
    'parser.add_argument("--token", help="the API token to use")  "description": "Personal access token"',
    "Authorization: required for every call; Bearer authentication is described below",
    "drive-get 1" + "Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk2Ji1Hg0FeDcBa" + " --out a.md",
]


POSITIVES = positives()


@pytest.mark.parametrize("category,text,secret", POSITIVES, ids=[case[0] for case in POSITIVES])
def test_redacts_and_keeps_context(category: str, text: str, secret: str) -> None:
    out, hits = redact(text)
    assert hits[category] >= 1, (category, hits)
    assert secret not in out and f"[redacted:{category}]" in out
    assert redact(out) == (out, {})  # idempotent: markers never match again


@pytest.mark.parametrize("text", NEGATIVES)
def test_leaves_useful_text_alone(text: str) -> None:
    assert redact(text) == (text, {})


def test_url_with_a_marker_stays_one_url() -> None:
    """Pass 2 must see the same URL as pass 1: a `]` from an earlier marker does not end it."""
    text = f"https://example.com/cb?auth={rand(20)}&page={rand(40)}"
    out, hits = redact(text)
    assert hits == {"url-param": 1} and redact(out) == (out, {})


def test_recall_and_false_positive_rates() -> None:
    """Context-free random tokens get caught; the ids and hashes an archive search needs don't."""
    tokens = [rand(rng.randint(32, 64), alphabet) for alphabet in (B62, string.ascii_lowercase + string.digits,
              B62 + "+/", B62 + "-_") for _ in range(250)]
    caught = sum(bool(redact(f"value {t} end")[1]) for t in tokens)
    ids = [rand(40, "0123456789abcdef") for _ in range(300)] + [
        f"{rand(8, 'abcdef0123456789')}-{rand(4, 'abcdef0123456789')}-4{rand(3, 'abcdef0123456789')}-a{rand(3, 'abcdef0123456789')}-{rand(12, 'abcdef0123456789')}"
        for _ in range(300)]
    flagged = sum(bool(redact(f"see {i} here")[1]) for i in ids)
    assert caught / len(tokens) >= 0.95, caught / len(tokens)
    assert flagged == 0


# --- archive paths ---------------------------------------------------------------------------

SECRET = "gh" + "p_" + rand(36)
PASSWORD = rand(16)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    s = Store(tmp_path / "statev2.sqlite")
    s.thread("t1", "Rotate " + SECRET, minutes=60, settled=True)
    s.message("t1", "user", f"my token is {SECRET}, deploy please", 59)
    s.message("t1", "assistant", "Deploying with the new GITHUB_TOKEN now.", 58)
    s.item("t1", "command_execution", {"input": "cat .env", "output": f"DB_PASSWORD={PASSWORD}\nRAILS_ENV=production", "exitCode": 0}, 57)
    return s.close()


def raw_bytes_hold(path: Path, *needles: str) -> bool:
    """Look in the file itself: FTS shadow tables, free pages and leftovers included."""
    blob = b"".join(p.read_bytes() for p in path.parent.glob(path.name + "*") if p.suffix != ".lock")
    return any(n.encode() in blob for n in needles)


def test_every_write_path_redacts(store: Path, tmp_path: Path) -> None:
    path = tmp_path / "a.sqlite"
    db = t3_archive.open_archive(path)
    hits = __import__("collections").Counter()
    with sqlite3.connect(store) as src, db:
        assert t3_archive.archive_threads(src, db, hits=hits) == 1
    old = tmp_path / "purged-threads-old.sqlite"
    with sqlite3.connect(old) as b:
        b.executescript(f"""
            CREATE TABLE projection_threads (thread_id, project_id, title, branch, worktree_path, created_at,
              updated_at, deleted_at, archived_at, model_selection_json, settled_override);
            CREATE TABLE projection_thread_messages (message_id, thread_id, role, text, created_at, attachments_json);
            INSERT INTO projection_threads VALUES ('v1', 'p', 'Old', NULL, NULL, '2026-04-01T00:00:00Z',
              '2026-04-02T00:00:00Z', NULL, NULL, '{{}}', NULL);
            INSERT INTO projection_thread_messages VALUES ('m', 'v1', 'user', 'password: "{PASSWORD}"', '2026-04-01T00:00:01Z', '[]');
        """)
    with db:
        assert t3_archive.import_backup(old, db, store, hits) == 1
    assert hits["github-token"] == 2 and hits["secret-assignment"] == 2
    assert {r[0] for r in db.execute("SELECT redaction FROM threads")} == {t3_redact.VERSION}
    assert db.execute("SELECT title FROM threads WHERE thread_id = 't1'").fetchone()[0] == "Rotate [redacted:github-token]"
    # the conversation stays searchable, the secret does not
    assert db.execute("SELECT thread_id FROM entries WHERE entries MATCH 'deploy'").fetchone()[0] == "t1"
    assert db.execute("SELECT COUNT(*) FROM entries WHERE entries MATCH 'RAILS_ENV'").fetchone()[0] == 1
    db.close()
    assert not raw_bytes_hold(path, SECRET, PASSWORD)


def legacy_archive(store: Path, path: Path) -> None:
    """An archive written before redaction: raw text, `redaction` column absent, rows re-archived
    once (so old text also sits in FTS segments and free pages)."""
    db = sqlite3.connect(path)
    db.executescript(t3_archive.SCHEMA.split("-- Writers without")[0])
    original = t3_redact.redact
    t3_redact.redact = lambda text: (text, {})
    try:
        with sqlite3.connect(store) as src, db:
            t3_archive.archive_threads(src, db)
            t3_archive.archive_threads(src, db)
        db.execute("ALTER TABLE threads DROP COLUMN redaction")  # the pre-redaction schema
    finally:
        t3_redact.redact = original
    db.close()
    path.chmod(0o600)


def test_scrub_rebuilds_without_a_trace(store: Path, tmp_path: Path) -> None:
    path = tmp_path / "a.sqlite"
    legacy_archive(store, path)
    assert raw_bytes_hold(path, SECRET, PASSWORD)
    before = sqlite3.connect(path)
    rows = before.execute("SELECT rowid, thread_id, seq, role FROM entries ORDER BY rowid").fetchall()
    ranges = before.execute("SELECT thread_id, first_entry, last_entry, root_thread_id FROM threads").fetchall()
    before.close()
    assert t3_archive.scan(path)[0]["github-token"] == 2

    hits = t3_archive.scrub(path, step=lambda msg: None)
    assert hits["github-token"] == 2 and hits["secret-assignment"] == 1
    assert not raw_bytes_hold(path, SECRET, PASSWORD)
    assert not (tmp_path / "a.sqlite.scrub-tmp").exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    db = t3_archive.open_archive(path)
    assert list(map(tuple, db.execute("SELECT rowid, thread_id, seq, role FROM entries ORDER BY rowid").fetchall())) == rows
    assert list(map(tuple, db.execute("SELECT thread_id, first_entry, last_entry, root_thread_id FROM threads").fetchall())) == ranges
    assert t3_archive.stale_threads(db) == 0
    assert db.execute("SELECT COUNT(*) FROM entries WHERE entries MATCH 'deploy'").fetchone()[0] == 1
    # unchanged source + changed_only: nothing re-imported; forced re-archive stays redacted
    with sqlite3.connect(store) as src, db:
        assert t3_archive.archive_threads(src, db, changed_only=True) == 0
        assert t3_archive.archive_threads(src, db) == 1
    db.close()
    assert not raw_bytes_hold(path, SECRET, PASSWORD)
    assert t3_archive.scrub(path, step=lambda msg: None) == {}  # second scrub: nothing left


def test_failed_scrub_leaves_archive_untouched(store: Path, tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "a.sqlite"
    legacy_archive(store, path)
    t3_archive.open_archive(path).close()  # schema migration happens before the rebuild anyway
    def content() -> list:
        with sqlite3.connect(path) as db:
            return db.execute("SELECT * FROM entries ORDER BY rowid").fetchall() + db.execute("SELECT * FROM threads").fetchall()
    original = content()
    monkeypatch.setattr(t3_archive, "verify_scrub", lambda db: (_ for _ in ()).throw(SystemExit("boom")))
    with pytest.raises(SystemExit):
        t3_archive.scrub(path, step=lambda msg: None)
    assert content() == original and raw_bytes_hold(path, SECRET)
    assert not (tmp_path / "a.sqlite.scrub-tmp").exists()


def test_writers_wait_for_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "a.sqlite"
    t3_archive.open_archive(path).close()  # this process now holds the writer lock
    child = subprocess.Popen(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(Path(__file__).parent)!r}); import t3_archive, pathlib; "
         f"t3_archive.open_archive(pathlib.Path({str(path)!r})).close(); print('got it')"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.0)
    assert child.poll() is None  # blocked behind us
    child.kill()
    _, err = child.communicate()
    assert "waiting for another archive writer" in err


def test_old_writer_code_cannot_write(store: Path, tmp_path: Path) -> None:
    """A stale copy of the archiver (no redaction, no registered function) aborts instead of
    writing raw text into an archive that has been redacted."""
    path = tmp_path / "a.sqlite"
    t3_archive.open_archive(path).close()
    old = sqlite3.connect(path)
    with pytest.raises(sqlite3.OperationalError, match="t3_redaction_version"):
        with old:
            old.execute("INSERT INTO threads (thread_id, id_key, project_id, project_title, workspace_root, "
                        "workspace_name, title, created_at, updated_at, source, backed_up_at) "
                        "VALUES ('x', 'x', 'p', 'p', '', '', 't', '', '', 'statev2', '')")
    assert old.execute("SELECT COUNT(*) FROM threads").fetchone()[0] == 0
    assert old.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0  # readers are unaffected


def test_clipping_never_splits_a_token() -> None:
    """A cut landing inside a token moves to whitespace, or (inside a long run) redacts first:
    no unmatchable half-token survives either way."""
    token = "gh" + "p_" + rand(36)
    long_run = "k=" + "v," * 150 + token + ",w" * 150  # no whitespace for > 200 chars around the token
    cases = [("x " * 990 + token + " " + "y " * 3000, t3_archive.head_tail),
             ("y " * 3000 + token + " " + "x " * 480, t3_archive.head_tail),
             ("x " * 900 + long_run + " " + "y " * 3000, t3_archive.head_tail),
             ("x\t" * 990 + token + "\t" + "y " * 30, lambda t: t3_archive.clip(t, 2000)),
             (long_run, lambda t: t3_archive.clip(t, 400))]
    for text, cut in cases:
        clipped = cut(text)
        assert token not in clipped  # every case cuts at or inside the token
        assert not any(token[i:i + 8] in clipped for i in range(len(token) - 7)), clipped[:80]


def test_a_cut_never_separates_value_from_key() -> None:
    password, phrase = rand(14, string.ascii_lowercase + string.digits), "aB1! cD2@ eF3# gH4$ iJ5%"
    assert password not in t3_archive.head_tail("x " * 4000 + f"PASSWORD = {password} " + "y " * 490)
    clipped = t3_archive.clip("x " * 990 + f'password: "{phrase}" and more', 2000)
    assert not any(word in clipped for word in phrase.split())


def test_rearchiving_a_stale_thread_keeps_asking_for_a_scrub(store: Path, tmp_path: Path) -> None:
    """Re-archived rows are redacted, but FTS5 keeps the deleted tokens: only a rebuild clears them."""
    path = tmp_path / "a.sqlite"
    legacy_archive(store, path)
    db = t3_archive.open_archive(path)
    with sqlite3.connect(store) as src, db:
        assert t3_archive.archive_threads(src, db, changed_only=True) == 1  # stale version → rewritten
    assert t3_archive.stale_threads(db) == 1  # rows current, index residue flagged
    db.close()  # (whether residue is still in this tiny file depends on FTS5 merges; real archives keep it)
    t3_archive.scrub(path, step=lambda msg: None)
    assert not raw_bytes_hold(path, SECRET, PASSWORD)
    with sqlite3.connect(path) as db:
        assert t3_archive.stale_threads(db) == 0
