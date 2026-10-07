# Evidence before routing

Read only the relevant branch. Explicit intent and current repository policy win
over routing heuristics; source metadata may establish ownership, not authorization.

## Ticket link

- Read the selected project's ClickUp wrapper before its shared core. Use its
  explicit config; do not borrow another person's token when access fails.
- An explicit repo chooses the target; metadata still establishes ticket context.
  Company/workspace hints narrow candidates, never prove a particular list or repo.
  `/t/<workspace>/<task>` contains a workspace ID, not a list ID.
- Fetch a compact preview: task ID, title, actual workspace/list and a short excerpt.
  Read more body/comments only when needed to distinguish sibling ownership.
  Return factual evidence separately from the proposed workflow.
- Worker gets the exact URL, task text and selected wrapper path, then reads the full
  ticket under that wrapper's workflow. A routing read authorizes no ticket writes.
- Missing integration/inaccessible ticket → continue with available evidence where
  useful; if ownership cannot be established, ask one focused question.

## Gmail link

- Select the user's own Workspace wrapper for the intended mailbox. Read its
  `workspace.json`, actual `scopes` and account policy; authenticated Drive access
  does not imply Gmail access. Account-specific requests forbid token substitution.
- Verify identity read-only with that wrapper's `whoami`. Mismatch or unknown
  identity → stop mailbox reads until resolved. Browser access likewise requires a
  verified signed-in account, using the user's browser-routing instructions.
- Exact hex/`thread-f:` IDs and **Print all** `permthid=thread-f:…` URLs can use
  `GWS_CORE=<selected core> t3-mail-link --config <wrapper>/workspace.json resolve '<url|id>'`.
  The read-only helper returns account and Gmail thread ID without linking, spawning
  or scheduling. Locate the actual Workspace core from the selected wrapper;
  do not assume it is installed beside the global thread helpers. Read helper docs.
- `#inbox/FMfcg…` tokens need resolution, not hex guessing. Prefer native T3 browser
  tools where supported, with verified identity, to obtain the exact Print-all URL
  or subject; a closed preview alone is not reason to switch browsers. Then resolve
  the exact reference or use the helper's `--search`. Subject matches require checks
  against sender/date/content; several matches remain ambiguous. Follow the user's
  browser fallback policy if native tools cannot handle it; otherwise request the
  exact Print-all URL/minimum subject clue. Never silently use another account.
- Fetch relevant context using that account's configured CLI. State likely workflow
  as inference. A draft in chat is low-risk; a Gmail draft or inbound monitoring
  needs specific authorization. Never use `t3-mail-link add`/`new` just to resolve.

## Screenshot or short text

Preserve the image/path and exact user text. Mark extracted text as agent
transcription; do not invent cropped IDs, dates or account identity. A URL visible
in an image can guide a read-only lookup under the same integration checks. When
the image is unavailable to the worker, arrange accessible local attachment context
or identify the gap before dispatch. Use the catalog and recent relevant conversation
to distinguish an investigation, explanation, implementation or reply request.

## Existing task

For mail, inspect existing `t3-mail-link list` entries where available, matching both
account and resolved Gmail ID. Then use `t3-find-thread` on exact ticket/thread IDs
or URLs, followed by topic search if needed. Follow its search/peek/read guidance.
Exclude the current dispatch conversation and other intake-only mentions.

Read the candidate's initial task and recent progress: verify artifact, account,
project and intended outcome. A keyword hit or recent timestamp is not proof.
Matching execution threads can be pinged even when settled; avoid parallel duplicate
execution if one is already working. Preserve explicit account/model overrides;
if the verified target cannot honor them, explain and choose an authorized route.
No verified match → spawn. User explicitly asks for new → spawn with prior context
as evidence. Missing search capability → disclose the reuse check limit, use any
available read-only thread lookup, and avoid claiming that no thread exists.
