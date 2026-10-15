"""Run: uv run --with pytest pytest skills/recording-watcher -q"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import recording_owner as ro  # noqa: E402

ROSTER = {
    "people": {
        "ana": {"identities": ["ana@example.com", "leexi:desk@beta.example"]},
        "ben": {"identities": ["fathom:office@alpha.example"]},   # shared recorder account = Ben's voice
        "cleo": {"identities": ["cleo@alpha.example", "cleo.home@example.org"]},
        "dan": {"identities": ["dan@example.net"]},
        "eve": {"identities": []},
    },
    "teams": {
        "alpha": {"recorders": ["fathom:office@alpha.example"], "priority": ["ana", "ben", "cleo"]},
        "beta": {"recorders": ["leexi:desk@beta.example"], "priority": ["ana", "dan"], "fallback": "dan"},
        "gamma": {"recorders": ["fathom:office@gamma.example"], "priority": ["ana", "eve"], "enabled": False},
    },
}


@pytest.fixture
def roster(tmp_path):
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(ROSTER))
    return ro.load_roster(path)


def alpha(roster, me, *speakers):
    return ro.elect(roster, me, "fathom", "office@alpha.example", speakers)


def test_priority_with_and_without_top_person(roster):
    full = [("ana@example.com", 300), ("office@alpha.example", 900), ("cleo@alpha.example", 100)]
    assert [alpha(roster, me, *full).action for me in ("ana", "ben", "cleo")] == ["process", "skip", "skip"]
    d = alpha(roster, "ben", *full)
    assert (d.owner, d.reason, list(d.present)) == ("ana", "other-owner", ["ana", "ben", "cleo"])
    no_ana = [("office@alpha.example", 900), ("cleo@alpha.example", 100)]
    assert alpha(roster, "ben", *no_ana).action == "process" and alpha(roster, "ana", *no_ana).reason == "other-owner"
    assert alpha(roster, "cleo", ("cleo.home@example.org", 50), ("x@customer.example", 900)).reason == "owner"
    beta = ro.elect(roster, "dan", "leexi", "desk@beta.example", [("dan@example.net", 400)])
    assert (beta.team, beta.owner, beta.action) == ("beta", "dan", "process")


def test_presence_needs_verified_speech_not_invites_names_or_share(roster):
    # invitees and display names are not inputs; word share is irrelevant: any verified speech keeps priority
    d = alpha(roster, "ben", ("ana@example.com", 5), ("office@alpha.example", 4000), ("", 5000))
    assert (d.owner, d.unidentified_words) == ("ana", 5000)
    assert alpha(roster, "ana", ("", 900), ("x@customer.example", 900)).reason == "no-verified-attendee"
    # the shared recorder identity is scoped to its provider: the same address on Leexi is nobody
    assert ro.person_of(roster, "leexi", "office@alpha.example") is None


def test_order_and_repeats_do_not_matter(roster):
    a = [("cleo@alpha.example", 10), ("ana@example.com", 15), ("cleo@alpha.example", 15), ("ana@example.com", 10)]
    assert alpha(roster, "ana", *a) == alpha(roster, "ana", *reversed(a))
    assert alpha(roster, "ana", *a).present == {"ana": 25, "cleo": 25}


def test_unknown_ambiguous_and_disabled_teams(roster):
    assert ro.elect(roster, "ana", "fathom", "other@example.com", [("ana@example.com", 500)]).reason == "unknown-team"
    assert ro.elect(roster, "ana", "fathom", "office@gamma.example", [("ana@example.com", 500)]).reason == "team-disabled"
    roster["teams"]["clash"] = {"recorders": ["office@alpha.example"], "priority": ["cleo"]}
    assert alpha(roster, "ana", ("ana@example.com", 500)).reason == "ambiguous-team"


def test_config_errors_fail_loudly(roster, tmp_path):
    with pytest.raises(ValueError, match="self"):
        alpha(roster, "zed", ("ana@example.com", 500))
    bad = json.loads(json.dumps(ROSTER))
    bad["people"]["dan"]["identities"].append("ANA@example.com")
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="both"):
        ro.load_roster(tmp_path / "bad.json")
    bad = json.loads(json.dumps(ROSTER))
    bad["teams"]["alpha"]["priority"].append("zed")
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="unknown people"):
        ro.load_roster(tmp_path / "bad.json")


def test_declared_fallback_only_when_nobody_verified(roster):
    beta = lambda me, *sp: ro.elect(roster, me, "leexi", "desk@beta.example", sp)  # noqa: E731
    d = beta("dan", ("", 900), ("client@example.com", 300))           # unlabelled speakers only
    assert (d.action, d.owner, d.reason) == ("process", "dan", "fallback")
    assert beta("ana", ("", 900)).action == "skip"
    assert beta("dan", ("desk@beta.example", 10), ("", 900)).owner == "ana"   # verified top priority still wins
    assert alpha(roster, "ana", ("", 900)).reason == "no-verified-attendee"   # no fallback declared
