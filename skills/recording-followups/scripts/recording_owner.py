"""Deterministic recording-owner election: which team member's machine processes a recording.

Stdlib only, no I/O beyond reading the roster. Every machine of a team runs the same election on the
same recorder account's data with the same roster, so exactly one of them processes each recording.
Roster and self identity are the operator's private configuration, never part of this skill.
Contract and roster schema: ../owner-election.md
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

MIN_SPEAKER_WORDS = 20      # fewer words under a verified identity = diarization noise, not presence


@dataclass(frozen=True)
class Decision:
    action: str                 # "process" | "skip"
    reason: str                 # owner | other-owner | no-verified-attendee | unknown-team | ambiguous-team | team-disabled
    owner: str | None
    team: str | None
    present: dict = field(default_factory=dict)   # verified roster person -> words, roster priority order
    unidentified_words: int = 0                    # words of speakers without a roster identity

    def evidence(self):
        people = ", ".join(f"{p} {w}w" for p, w in self.present.items()) or "no verified team speaker"
        return f"team={self.team or '-'} owner={self.owner or '-'} ({self.reason}); {people}; unidentified {self.unidentified_words}w"


def key(provider, email):
    return f"{provider}:{email}".lower() if provider else (email or "").lower()


def load_roster(path):
    """Read and validate a roster JSON (schema in owner-election.md). Raises ValueError on conflicts."""
    roster = json.loads(Path(path).expanduser().read_text())
    people, teams = roster.get("people") or {}, roster.get("teams") or {}
    owners = {}
    for person, spec in people.items():
        for ident in spec.get("identities") or []:
            if owners.setdefault(ident.lower(), person) != person:
                raise ValueError(f"identity {ident} belongs to both {owners[ident.lower()]} and {person}")
    for team, spec in teams.items():
        unknown = [p for p in spec.get("priority") or [] if p not in people]
        if unknown:
            raise ValueError(f"team {team}: unknown people in priority {unknown}")
    return roster


def person_of(roster, provider, email):
    """Roster person for a verified speaker email: a provider-scoped identity beats a bare email."""
    if not email:
        return None
    wanted = (key(provider, email), key(None, email))
    for ident in wanted:
        for person, spec in roster["people"].items():
            if ident in (i.lower() for i in spec.get("identities") or []):
                return person
    return None


def elect(roster, self_id, provider, recorder, speakers):
    """speakers: iterable of (verified_email_or_empty, words), any order, repeats allowed.

    Team = the team whose `recorders` contain this provider account. Owner = first person in the team's
    priority with >= MIN_SPEAKER_WORDS under a verified identity. Invitees, organizer, display names,
    token holder and word share never count. No owner -> every machine skips; nobody guesses.
    """
    if self_id not in roster["people"]:
        raise ValueError(f"self {self_id!r} is not a roster person: configure this machine's identity first")
    teams = [t for t, spec in roster["teams"].items()
             if {key(provider, recorder), key(None, recorder)} & {r.lower() for r in spec.get("recorders") or []}]
    if len(teams) != 1:
        return Decision("skip", "ambiguous-team" if teams else "unknown-team", None, None)
    team, spec = teams[0], roster["teams"][teams[0]]
    if spec.get("enabled") is False:
        return Decision("skip", "team-disabled", None, team)
    words, unidentified = {}, 0
    for email, n in speakers:
        person = person_of(roster, provider, (email or "").lower())
        if person:
            words[person] = words.get(person, 0) + n
        else:
            unidentified += n
    present = {p: words[p] for p in spec["priority"] if words.get(p, 0) >= MIN_SPEAKER_WORDS}
    owner = next(iter(present), None)
    if owner is None:
        return Decision("skip", "no-verified-attendee", None, team, present, unidentified)
    return Decision("process" if owner == self_id else "skip", "owner" if owner == self_id else "other-owner",
                    owner, team, present, unidentified)
