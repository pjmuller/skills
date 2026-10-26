---
name: mailbox-review-core
description: "Review a ReplyPen-watched Google mailbox from a developer machine: research every unsent ReplyPen draft, replace weak ones with a better version, open a fix thread per confirmed product bug, and hand the operator an inline Markdown report (Gmail links, folded evidence) plus a ledger. Read the project's mailbox-review wrapper first; it binds mailbox, accounts, repos and policy."
---

# Mailbox review (core)

Scope: every thread holding an unsent ReplyPen draft. ReplyPen's triage of undrafted mail is trusted;
the rest of the inbox is not rechecked. Gmail supplies drafts, public `rp` supplies per-thread run
evidence. A successful run is evidence, never proof the answer is right.

Needs authenticated `rp`, `uv`, and a [google-workspace-core](../google-workspace-core/SKILL.md) account
wrapper. **The project wrapper owns:** `--project`, Google mailbox UUID, GWS wrapper path, output dir,
grounding commands and repos, team/personas, whether draft corrections are switched off, how to tell
which operator runs it (developer vs product owner), where bug threads go. Never put those here.

```mermaid
flowchart LR
  C[collect] --> R[research per case<br/>Opus reviewers]
  R -->|wrong / obsolete draft| F[correct draft]
  R -->|misunderstanding / setup| F
  R -->|confirmed bug, sized| T[own T3 thread<br/>in the owning repo]
  T -->|fix proposal| G{operator go?} -->|go| S[ship, verify live, tell customer]
  R -->|lesson clear| P[propose now:<br/>exact diff, generic?] -->|go| B[land in batches:<br/>brain · help article · code PR]
  F --> L[fresh collect → ledger]
```

1. `scripts/cockpit.py collect`; read **only `index.json`** first ([commands](references/commands.md):
   inputs, bounds, artifacts). It verifies mailbox UUID/provider/email against the GWS identity.
   Title the coordinating T3 thread `🧭 <mailbox> review <date>`: it touches many cases, owns none.
2. **Continue earlier cases before researching anew** ([continuity](references/continuity.md)):
   `continuation --history <earlier bundles>` says per Gmail thread new / unchanged / changed and
   carries back earlier cases that got new mail; `t3-mail-link find` names an existing case owner.
   Read earlier 🧭 threads to their end: the operator's replies there are evidence of decisions, never
   fresh authorization. Never duplicate running work; never message an old reviewer: seed a new one.
3. **This week's mail first.** The cockpit answers "what do I send, fix or decide today", not a backlog
   audit. `index.json` marks a thread `stale` when no person has written for 14 days (`customer_at`:
   our own mail, tool notifications, auto-replies and bounces don't count). A stale case gets no reviewer
   and no deep research: a short finding with one action (usually "discard the draft", or the open debt
   we owe: money, a promised document, an unanswered data-loss report) that the report folds into "old
   cases". Only new customer mail, or a dated promise of ours due within 7 days (`due_by`), brings it
   back to the top; a renewal date recurs and never counts. Among fresh threads, leave answered,
   no-inbound and confident simple drafts alone; pick uncertain or consequential ones. Health flags help
   prioritize; keywords or a green run never decide answer quality.
4. `detail` for every thread you will write a finding for. **Delegate generously, after routing**:
   step 3's age rule and continuity's routing (unchanged → carry, existing owner → its thread) run
   first; each remaining uncertain or consequential customer gets its own `delegate_task` (Claude Opus,
   high effort, async; a Codex coordinator does the same), at most `8` per run, most consequential
   first, the rest listed as deferred. Its brief file `<bundle>/briefs/<customer>.md` holds
   [the reviewer recipe](references/reviewer.md), the wrapper's grounding brief, that customer's detail
   paths and, when carried, the prior brief file, the prior reviewer's result JSON and the
   coordinator's objections to it. Reviewers write their JSON next to the brief; keep both in the
   bundle and put the `childThreadId` in the finding's `reviewer_thread` (the latest completed
   reviewer; carry it forward on days without one). The coordinator orchestrates and verifies; it
   never researches ten cases serially. In-harness sub-agents only for quick single-fact checks. Never
   silently substitute a model. Opus unavailable → report it, leave corrections pending. As each
   reviewer returns, propose its lessons right away ("Persist the lesson" below), not at the end.
5. **Research first.** Most "it's broken" mails are misunderstanding or setup: the draft answers them.
   A bug needs evidence (logs, rows, a live reproduction) and a count of affected customers. A
   confirmed bug, above all one hitting several customers, gets its own T3 thread (`t3_thread_launch`
   in the owning repo, its brief carrying the case's `Mail-ref` line; second opinion inside it via
   `delegate_task`) that finds the fix; shipping per
   "Go deep" below. Explain at the operator's level (the wrapper says who is who).
6. Save the merged findings as `<bundle>/findings.json` (the next run's history), `validate`, then
   `apply --allow-draft-corrections` wherever you have a **better version** of an untouched ReplyPen
   draft (wrong, obsolete, incomplete, or just clearer): no operator go needed, unless the wrapper
   switches corrections off. A claim that depends on a human step (pay, refund, setting) gets a leading
   `[[✏️ Before sending: …]]` note in the draft. `render --out <bundle>/report.md`, read it and **paste it
   verbatim as the body of your final T3 reply** (T3 renders Markdown, `<details>` accordions and
   Gmail links inline; no HTML page, no `html_render`); the file stays in the bundle as the archive.
   It holds up to seven prioritized cards (subject link + one action, a closed "Why · evidence"
   accordion), the rest as one-line links in a closed accordion, then bugs, review limits and lessons
   with their status ([optional fields](references/optional-fields.md)).
   No raw mail or tokenized URLs.
7. End with a fresh `collect` and a ≤10-bullet ledger: send · decide · discard. Sending and deleting
   need the operator's explicit go in that conversation; verify in Gmail afterwards. Lessons still
   waiting for a go are a "decide" bullet. A new reply where no draft is left: GWS
   `gmail-draft --reply-to-message <last id> --from "<Name> <mailbox>"` (without `--from` the display
   name is lost), HTML from `rp dev tools draft-render`, then send.

## Go deep, whoever runs it

- Developer or product owner at the keyboard, the agent debugs as far as this machine allows: product
  code, every project repo and doc on disk, the brain, read-only production data/logs/traces, a live
  reproduction. A draft that says "we're following up with our developers/engineering" is a research
  gap, not an answer: get to the bottom first (one `delegate_task` per deep case), then reply with the
  cause and a step the customer can take today. Only facts that stay unknowable go to the developer:
  one ticket of one-line questions, drafted reply attached.
- **Say what limited you.** A missing env var, credential, CLI, repo or access, or a query that timed
  out → `dx_gaps` on the finding (report section "What limited this review"), naming who can grant it
  (wrapper), so the operator asks for it and the next run goes deeper. Never settle silently for a
  shallower answer.
- **Escalate only what research cannot settle** (rare; each names the exact question):
  1. *Decisions, not facts:* money (refund, discount, void), contract or legal commitments, commercial
     offers, a policy change customers will see.
  2. *Writes beyond a scoped one-customer fix:* infra, bulk data, irreversible deletion, deploys, publishing.
  3. *Facts outside every system this machine reaches:* a call or chat nobody logged, an admin console
     without access (then also a `dx_gaps` line), a vendor's private state, why code was deliberately
     disabled when git history does not say.
  4. *Human hands:* login, phone, eID, payment, signature; sending or deleting mail.
  Missing access is a `dx_gaps` line, not a reason to stop: answer with what is reachable and say what
  the rest needs.
- **Shipping a found fix:** a PR with tests on the critical path. Product-owner operator → the PR stays
  open for the developer. Developer operator → merge and ship when confident, verify live. A data fix
  scoped to one customer (one account or backup, reversible, regression risk rated low by the agent)
  may run on the operator's explicit go through an audited action or the repo's documented write path,
  read back afterwards; anything broader is a PR.
- **Local actions for one-offs, ReplyPen actions for the routine.** A write that is rare or ad hoc
  (a billing switch, a vendor API call, a one-customer fix) runs from the developer machine, not as a
  new ReplyPen action: a small script in the wrapper's local-actions dir, reading the credential at
  runtime from the store the wrapper names (never printed, copied or committed), dry-run by default
  (exact planned calls + before-state), `--execute` with an idempotency key, read back, and a private
  audit record (go, before/after, request ids). Example: switching a subscription to yearly
  pay-by-invoice through the payment provider's API with the app's own key. Only what recurs becomes
  a ReplyPen action. The operator's explicit go still gates every write; the wrapper says which
  credentials and writes are in bounds.

## Persist the lesson per case: you are ReplyPen's teacher

Solving today's case by hand is half the job. The other half: next time ReplyPen's own draft gets it
right without a coding agent. Do it **per case, while you answer**: at the end it is forgotten.
- **Spot it.** For every draft you corrected or had to deepen, ask what ReplyPen lacked: a fact or
  policy, a case runbook, routing (the symptom table pointed elsewhere), grounding (a script hid the
  deciding fact), an action (the fix needed hands), a wrong or missing help article, a product gap (a
  screen or error that caused the mail). If the brain already said the right thing, it is a model/host
  issue for `replypen`, not a brain edit.
- **Propose as soon as it is clear,** to the operator, before the next case (a question tool where the
  harness has one; keep researching while it waits). Concrete: file + section (article id or slug,
  repo path) + the text to add or replace as a short diff or quote block, never "improve the brain".
  Target where the fact lives: the brain (policy, runbook, routing, script, action); a help article
  (customers and ReplyPen's KB both read it: fix it there, not in the brain); product code. Ask two
  things: green light? Truly a generic rule (name the class of cases; never this customer) or a one-off
  that stays out?
- **Land on the green light, in batches.** Track each in the finding's `brain_proposal.status`.
  - *Brain:* one brain thread per run (`t3_thread_launch` in the brain checkout the wrapper names),
    started at the first go, fed later batches by `t3_thread_send`, keyed to the run ids it fixes. It
    reads the brain's `AGENTS.md` and repo-local brain-dev skills (`<brain>/.agents/skills/`, copies
    of `replypen-brain-skills`; `local-brain-work` first), writes the approved rule, proves it on the
    real case through `brain-simulate`/`brain-ask` against a `dev/*` ref (simulation only, never a
    rerun of the customer thread): before wrong, after right. Then `brain-publish`. The go on that
    exact text is the publish go; a failed proof or a materially different text returns to the
    operator with the simulated before/after.
  - *Help article:* the wrapper's edit and publish path, then sync ReplyPen's KB and verify live.
  - *Product code:* its own `t3_thread_launch` in the owning repo, a PR per "Go deep" shipping.
- **Fix facts at their source.** A product fact the brain reads from a mirrored repo (wrapper lists the
  mirrors) is fixed in that repo's docs, not copied into the brain.

Reviewers stay read-only: no `rp ask`, retry, process-thread, sending, deletion, labels, archive or
customer actions. A needed mutation becomes an audited action or its own thread. Draft correction
needs the current draft to be the untouched AI body (leading `[[✏️ …]]` notes and Gmail re-wrapping
tolerated, any word change refused), a unique draft, unchanged thread/run/message and independent
evidence; recipients, attachments and quotes are preserved, the original saved and read back. Gmail
cannot lock thread and draft together: a residual race exists, never call it race-free.

Schedule only when asked: a repo job each machine opts into, one fresh 🧭 thread per workday
([schedule](references/schedule.md)).
Never borrow a colleague's credentials.
