# Reviewing a ticket another agent wrote

Developer side, counterpart of [triage.md](triage.md): a reporter's coding agent (less capable,
less architecture context) filed or fixed a ticket and hands it over for review. Who reviews whom,
review header, statuses and the verdict's language: the wrapper's `[policy]`.

## Mindset

- Trust symptoms, repro steps, screenshots, recordings and domain observations as primary
  evidence. Treat root-cause claims, proposed fixes, scope estimates, "tests passed" and the
  agent's code as unverified: re-derive the cause from the code and the repo's skill docs, don't
  anchor on its hypotheses. Its diff likely ignores house conventions.
- Check the ask against the product's mission; a well-meant request can still fail it. Say so and
  propose the version that doesn't.
- Change only what moves the needle: a wrong fix, a missed symptom, a real regression, security or
  tenant-isolation risk. Style and nice-to-haves are at most one wrap-up line.
- Scope = the ticket. Adjacent problems go in the wrap-up or a new ticket, not the diff.

## Flow

1. `task ID --download-attachments` (body + full discussion); open the screenshots and recordings. Extract
   symptoms, claimed cause, claimed changes (PRs, SHAs, deploys) and claimed verification.
2. Verify in the real code: read the diff, check the cause explains **all** symptoms, check the fix
   is deployed where the ticket says, run the tests/greps yourself.
3. Wrong or missing and it matters: smallest fix, the repo's lint/tests, commit per its conventions.
4. Close with exactly one verdict; it is appended to the description (under `review_header`, with a
   real mention), not posted as a comment; `--comment` adds an inbox ping. Assignee stays.
   - `review ID --verdict ok`: everything holds (trivial fixes included) → closed status.
   - `review ID --verdict to-test --text $'- …\n- …'`: you changed something the reporter must
     test → `to test`. Functional bullets (what changed for the user), no implementation details.

Report the URL plus one paragraph: verdict, which claims held, which didn't, what you changed.
