# Who processes this recording?

Several teammates' machines may poll the same recorder account. [`scripts/recording_owner.py`](scripts/recording_owner.py)
elects exactly one of them per recording, before any expensive step (media, LLM, thread spawn). Each
machine calls `elect(roster, self_id, provider, recorder, speakers)`: `process` only when it is the owner,
else `skip` with owner, reason and `Decision.evidence()`. Keep local per-recording-ID dedupe beside it.

- **Team** = the one roster team whose `recorders` lists this provider account (Fathom `recorded_by.email`,
  Leexi `owner.email`). None → `unknown-team`; several → `ambiguous-team`; `"enabled": false` → `team-disabled`.
- **Owner** = first person in the team's `priority` who spoke ≥ `MIN_SPEAKER_WORDS` under a **verified
  identity**: the vendor's speaker-to-email match (Fathom `speaker.matched_calendar_invitee_email`,
  Leexi `speakers[].email_address`) equal to one of that person's roster identities.
- Never evidence: calendar invitees/organizer, display-name substrings, who holds the API token,
  most words. Silent attendance is invisible to both vendors, so a silent higher-priority person does not own.
- No verified team member → `no-verified-attendee`: every machine skips and records it visibly. No guessing.
- An elected owner whose machine is offline stays owner: no failover, no leases, no distributed lock.

**Same facts, same answer.** Uniqueness holds only when every machine of a team reads the recording
through the team's recorder account and uses an identical roster. Calls seen through any other
account fall to `unknown-team`. Missing self identity or roster conflicts raise instead of skipping.

## Roster (private, outside installed skills)

```json
{"people": {"ana": {"identities": ["ana@example.com", "leexi:desk@beta.example"]},
            "ben": {"identities": ["fathom:office@alpha.example"]}},
 "teams":  {"alpha": {"recorders": ["fathom:office@alpha.example"], "priority": ["ana", "ben"]},
            "beta":  {"recorders": ["leexi:desk@beta.example"], "priority": ["ana"], "enabled": false}}}
```

`provider:email` scopes an identity to one vendor; use it for shared accounts (a recorder login that
is one person's voice). Bare emails match on every provider. Each identity belongs to one person.
Self identity is per machine, also outside the skill (e.g. `~/.config/recording-owner/self`).

## Processing host ≠ action owner

The elected machine processes the whole call. A teammate's own requests in it become a handoff in
that teammate's queue (e.g. their ClickUp list); never run their work on the processing machine.
