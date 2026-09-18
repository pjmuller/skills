"""Snooze lifecycle regressions against the keeper's actual jq decision."""
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("t3-hide-thread").read_text()
DECISION = SCRIPT.split("--argjson now \"$(date -u +%s)\" '\n", 1)[1].split("')\"", 1)[0]


def decide(**updates):
    snapshot = {
        "session": {"status": "ready"},
        "snoozedUntil": "2026-01-08T10:00:00Z",
        "snoozedAt": "2026-01-01T10:00:00.304Z",
        "latestTurn": {"state": "completed", "completedAt": "2026-01-01T10:00:00.373Z"},
    }
    snapshot.update(updates)
    return subprocess.check_output(
        ["jq", "-r", "--argjson", "now", "1767261610", DECISION],
        input=json.dumps(snapshot), text=True,
    ).strip()


def test_completion_after_snooze_in_same_second_resnoozes():
    assert decide() == "snooze"
    assert decide(snoozedAt="2026-01-01T10:00:00Z") == "snooze"


@pytest.mark.parametrize("completion", ["2026-01-01T10:00:00.304Z", "2026-01-01T10:00:00Z"])
def test_completion_at_or_before_snooze_stays_hidden(completion):
    assert decide(latestTurn={"state": "completed", "completedAt": completion}) == "hold:snoozed"


def test_ping_after_turn_in_same_second_waits_for_adoption():
    assert decide(latestUserMessageAt="2026-01-01T10:00:00.400Z") == "hold:queued-turn"
    assert decide(latestUserMessageAt="2026-01-01T09:57:00Z") == "snooze"


@pytest.mark.parametrize("field", ["hasPendingApprovals", "hasPendingUserInput"])
def test_real_attention_request_is_never_resnoozed(field):
    assert decide(**{field: True}) == "hold:needs-user"


def test_failed_session_exits():
    assert decide(session={"status": "error"}) == "exit:session-error"
