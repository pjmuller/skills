# Changelog

## 2026-10-29 — pr-review: PRs state their evidence per commit and reach a named approver

- New global skill `pr-review`: a 120–200-word PR description (problem → result, behaviour bullets, Evidence block with model provenance, review rounds and every check at the commit it ran on, stubs and not-run checks named, deviations/deliberate quirks/risk), a notify step (GitHub review request plus, where the team works in a tracker, one native mention; never "in review" prose), and `review.md` for the consuming reviewer: authority first, triage evidence against the head, depth by what is touched, re-run only what adds independence, one disposition tied to the head sha. Why: on a real PR the description's checks predated the head commit, CI was absent so every check was a claim, the review provenance sat in a comment without its commit, and the ticket's "in review, needs X's approval" comment notified nobody.
- `agents-md/global-template.md` Git section: one pointer line (opening or reviewing a PR → skill `pr-review`; repo rules still decide; no PR where direct commits are allowed). Why: product owners open most PRs and their agents need the format and the ping step without a per-repo copy.
- `agents-md/roles.md` product-owner line: a PR carries its evidence and reaches a named approver. `t3-manage-thread/code-review.md`: the report line carries the reviewed sha; "skip what CI catches" only when CI ran. `clickup-core/review.md`: no "less capable"/"ignores house conventions" presumption; screenshots may show a stubbed environment. Why: review by evidence, not by the author's role.

## 2026-10-29 — clickup-core / agents-md / t3-schedule: colleague agents report back into the ticket body; the requester chases with daily follow-ups

- `clickup-core` ("Report back into the ticket"), `agents-md/handoff.md` step 5, `t3-schedule` Continuation: a ticket asking someone's coding agent to run steps ends with the exact CLI line to append a dated report section to the ticket body plus one mention ping; the requesting agent arms a `--once` continuation for the next workday that verifies the report or re-arms itself (nudge after 3 empty days, ask the user after 5). Why: reports landed as long comments the requester had to find by hand, and "check tomorrow" was forgotten; body sections stay the record and the chase needs no recurring job.

## 2026-10-29 — agents-md global template: label several decisions D1, D2…

- Asks with more than one decision label them D1, D2… and request replies like "D1: A, D2: B". Why: a bare "A" or "B" was ambiguous when one message carried two questions.

## 2026-10-28 — clickup-core: a comment link reads like a conversation; extract-keyframes accepts "Key Frames"

- `clickup-core` `comments --thread <URL>` prints root + replies as readable rows (author, date, text, images, like `task`'s discussion) and marks the link's `?threadedComment=` reply `selected`; `--raw` keeps ClickUp's API objects. Why: a pasted reply link returned ~10 KB of rich-text parts and no hint which reply the sender meant.
- `video-shrink-for-gemini` `extract-keyframes`: the `## Key frames` heading match is case-insensitive. Why: Gemini wrote `## Key Frames` and the stills were refused (reported from a colleague's machine).

## 2026-10-28 — t3-route, mailbox-review-core: north star states the value

- Both intros now say why to use the skill and how a user gets value: the router is one intake that finds the owning repo, reuses the thread that owns the task and spreads account load, then steps aside; the mailbox review is expert prep before the operator opens drafts (teacher/apprentice), with the 🧭 thread as the place to settle decisions and lessons. Why: a colleague got little value from either because the purpose was implicit; agents can now answer "what is this for" from the skill itself.

## 2026-10-28 — clickup-core: images inline in comments, images readable on demand

- Comments, replies, `handoff` and `review --comment` show local images, mermaid diagrams and `![[file:NAME]]` inline (the web app's `image` part on a task attachment, sized from the image header) instead of a bare attachment URL. Other image URLs stay links; a readback missing an image fails. Local image paths may contain spaces (they used to post a broken `!link`). Why: a colleague's handoff showed four screenshots as plain links, by core design, not their mistake.
- `task` now lists `images` (body, sidebar, comments, replies, with `sources`); `--download-images` fetches only those, from ClickUp's attachment host, no token, no redirects, ≤ 20 MB each, image bytes only. Why: a URL in the JSON let an agent think it had seen a screenshot; `--download-attachments` also pulled 200 MB videos.

## 2026-10-28 — clickup-core: full reply threads, paged

- `task` (and `comments --thread`) page threaded replies with the same `start` + `start_id` cursor as task comments until the root's `reply_count` is reached (the reply endpoint documents no paging but honours the cursor, checked live). Roots and replies sort by date, then id. Why: a ticket's full thread is part of reading it; one unpaged call could cut a long thread.

## 2026-10-28 — clickup-core: reading a task includes its discussion

- `task ID` now returns `{"task", "discussion"}`: every comment oldest first with threaded replies nested, each `{id, date (ISO UTC), author, text}`; text keeps mentions, link targets and tables. A thread the API returns short carries `replies_missing` plus a stderr warning instead of dropping replies. Why: agents read tickets without comments and missed decisions made there (a live ticket's latest comment said only one item remained).
- `--no-comments`: metadata only, no comment API call (routing previews, bulk scans; with `--download-looms` only the body is scanned). `--comments` still adds the raw API objects under `comments`; the two flags are mutually exclusive. Callers that passed `--comments` keep working.

## 2026-10-28 — agents-md template: deeper, not bigger

- `global-template.md`: the 80/20 line now asks for a top practitioner's methods (unfamiliar ground → look up current best practice, how others solved it) on the evidence that could change the answer, and lists what they'd add beyond the ask without building it. The verify line picks evidence outside the agent's or another model's judgment that could expose a wrong result (test, real run, primary source, reconciliation). Why: in one maintainer's last 30 days of prompts, "look up best practice" was typed 31×, "real data/runs" 8× and "did you actually…?" 6×, i.e. agents went for depth only when told to. Opus analysis plus an independent Astra check; wording merged from both.

## 2026-10-28 — whatsapp-voice-intake: transcriber knows the purpose and your vocabulary

- WhatsApp voice transcripts (bridge prompt, every caller) now leave out filler sounds (eh, ehm), stutters, repetitions and false starts; content stays verbatim, unsummarised and in order. Why: for an agent reading the transcript they are noise.
- The transcriber now gets the note's purpose (a note-to-self a dispatcher will route; still verbatim) and an optional `vocabulary` Markdown file from the wrapper (terms + how dictation mishears them), re-read per note. `whatsapp-bridge` `transcribe_audio(path, hint, context)` gains the `context` section. Why: on a synthetic Flemish clip with 10 product/model/people terms, no hint got 6 wrong ("Camp Compass", "Solveigh", "Mabox"), a one-line names hint 1, purpose + vocabulary 0.

## 2026-10-28 — bitwarden: Sends default to 14 days, still one view

- `bw-once send-text|send-file` default expiry 7 → 14 days (`--days 1-31` and `--views` unchanged; explicit values are kept). `receive.md` drops its `--days 1`. Why: a colleague may get to a handed-over link days later; the one-view limit, not a short expiry, is the protection.
- `receive.md`: "does not exist or is no longer available" before the returned `expiry` means the view was used or the Send deleted, not expiry; check the view count in the app before re-sending. Why: a 7-day Send died the same evening and expiry was suspected first.

## 2026-10-28 — whatsapp-voice-intake: voice notes to yourself land in your router thread

- New `whatsapp-voice-intake` (5-min launchd/systemd poll, configurable hours): voice notes in the paired account's own WhatsApp chat, with text sent within 120 s before/after as annotation, are transcribed once (`transcribe-gemini`) and queued into one T3 thread, found per delivery by exact title + pin (newest pin wins; none → one optional fallback launch). No model in the poller; the receiving thread interprets. Late annotations become one supplement, never a second task; transcription failures are delivered marked, not dropped; `seed` starts without backlog, `--include` adds exact earlier notes. Why: capturing an idea on the road should need nothing but a voice note.
- `t3-relay send|launch --request-id KEY`: the record is saved before the call, and a repeat with the same key never re-sends an accepted or still-unconfirmed request (a different payload under the same key exits 2). A T3 refusal now marks the record failed. Why: a caller that crashed between t3-relay's accept and its own save used to resend under a fresh id.
- `t3-relay find --project P --title T [--json]`: open root threads with that exact title, with `pinnedAt` read from T3's projection (no API exposes pins yet); unreadable pin state fails instead of reporting "unpinned".
- `whatsapp-bridge`: `read_chat(..., since=)` returns the oldest n messages at/after a Unix timestamp (forward paging; without `since` unchanged: newest n); messages keep WhatsApp's forwarded flag (`forwarded`: true/false, null for rows synced before today).

## 2026-10-28 — clickup-core: successor ticket instead of reply ping-pong

- `clickup-core` "Before creating work": a follow-up on an existing ticket either extends it (one dated body section + one ping, when it serves the ticket's current outcome) or opens a successor ticket that stands alone and links the predecessor, when the outcome is materially new or the ticket already went back and forth (cue: two or more rounds of replies or dated sections). Successors still pass the duplicate check, ownership policy and commitment gate; never one per reply. `recording-followups` points there. Why: tickets where agents on both sides each added several comments became unreadable for the humans reviewing them.

## 2026-10-28 — bitwarden: Touch ID sheet names the request, no release to a gone caller, lookalike warning, prior art

- macOS's Touch ID sheet now states the checked action (`release the password for H (alice)`, `list logins for H`, `create a one-view text Send in V`) instead of "approve the bw-once request shown on screen". Why: it is the one text no other app can draw, and a comparison of agent credential brokers showed the action belongs there.
- A copy whose front end ended between the touch and the release (Ctrl-C, tool timeout) releases nothing; the session holder re-checks its expiry before delivering. Why: an independent review found the clipboard was still written although nobody would paste (Sends already had this check).
- Hosts with an `xn--` label get a lookalike warning in the approval window and the Terminal, shown raw (decoding would hide the imitation).
- New `bitwarden/prior-art.md`: comparable agent credential brokers and Touch ID CLIs with the version reviewed, what is worth borrowing and when to revisit (Bitwarden agent-access, official CLI biometrics, secretive, grantpin, agent-secret, briefcred…). None replaces bw-once.

## 2026-10-28 — public-footprint-audit: field-level check for official records

- New `public-footprint-audit/official-records.md`, linked from SKILL.md and a per-field table in the report template. Before recommending anything for a gazette, filing or register entry, the auditor records the document type (original act vs published extract vs annual accounts), the jurisdiction and filing date, the person's role, and mandatory / optional / unknown per field, citing the provision it opened. A mandatory field is real exposure, not a removal finding. An optional one is a candidate for an erasure request to the publisher (C-231/22, C-200/23), with no promised outcome. Includes a verified Belgian worked table (WVV 2:8 §2, 2:7 §5, 3:12; notarial law art. 12) and a fictional example. Why: an audit flagged a whole company-incorporation extract as "high priority, ask the notary". The notary answered "identity is mandatory, publications never change". Both were too coarse: the law requires name and domicile, not the birth details, and an erasure route exists for fields the law doesn't require.

## 2026-10-28 — warm-ups: launcher-owned settlement, independent account retries

- `t3-relay launch --settle-after-run SECS` waits and settles completed, untouched first runs. Warm-ups use it with 90 seconds instead of relying on the model to call a tool: small models sometimes replied without calling settle or falsely said it was unavailable. Failed, unfinished or repurposed threads stay open; cleanup errors never trigger duplicate launches.
- Record each successful morning launch separately. One exhausted account previously failed the whole batch, relaunching the successful accounts every ten minutes.

## 2026-10-27 — bitwarden: Touch ID broker no longer mistakes a locked Mac for new fingerprints, shows progress, keeps slow Sends

- Renewal (type master passwords) only when the enclave refuses **and** the enrolled-fingerprint hash differs from the one now saved at sealing; cancel, a locked Mac, a closed lid or lockout → "Touch ID did not complete", nothing released, no password window. Why: a request on PJ's locked Mac (lid closed, away) was refused instantly (`errSecInteractionNotAllowed`, AKS `e00002e2`, hash unchanged) and asked for the master passwords as if fingerprints had changed: phishing practice. Older seals gain the hash after their next good touch.
- The window says "Approved · …" right after the touch. Why: a vault sync (3.7 MB, over a minute on a poor link) kept "Touch ID to approve…" on screen after a registered touch, and the human cancelled.
- `bw serve` connection: a timed-out call ends it (lock via a fresh one); sync budget 120 s, else that vault is unavailable (named in the error). Why: a sync answering after the 60 s timeout was read as the unlock's reply and the unlock's as the Send's, so the Send came back "answer unclear"; it was in fact never created (bw was stopped mid-call to lock the vault), which the unchanged `retry_safe: false` covers.
- Text Sends skip the sync and the create may wait until the front end gives up; failure JSON gains a debug-safe `reason` (error code, timeout, bw's message, never values). Why: each Send changes the vault so the next sync re-downloads it, and the swallowed bw reply left the cause unknown.

## 2026-10-27 — bitwarden: `bw-receive` hands secrets to a colleague's agent; owner commits directly

- New `bw-receive` (`bitwarden/receive.md`): installs a one-view text Send holding `{"NAME": "value"}` into a chmod-600 dotenv file (e.g. `~/.config/mise-env/<org>/<repo>.env`), printing statuses, names and lengths only. Fetches once with the official `bw` in a throwaway logged-out profile (no Bitwarden account), stages the payload so a failed install retries with `--from-stage` instead of a second fetch, keeps identical values, refuses a different existing value, rejects unexpected names. `scripts/install --receive-only` links just this command (uv + any bw, no Xcode); the full install links it too. Why: handing API keys to colleagues' agents was ad hoc, and a live test showed `bw receive --obj` burns the one view and prints the plaintext.
- `AGENTS.md`: the owner and agents working the owner's own request commit straight to `main`, any size; the PR rules are for collaborators. Why: the previous wording made the owner's agents open PRs for new commands in the owner's own repo.

## 2026-10-27 — bitwarden: unlock retries in the same Terminal, text Sends with Touch ID

- Terminal flow: a refused `bw unlock` gets up to 3 human-chosen attempts in the same window (CLI re-checked locked + same account between them; Return = again, n/Ctrl-C/EOF = cancel); the prompt names the vault's account email. Budget 5 min approval (was 6), 3 min for all attempts, 60 s operation; launcher waits the sum + 20 s (< 10 min tool call). Failure JSON gains `stage` and `retry_safe` (`false` after a possibly-created Send or an unverified lock); Ctrl-C, timeout and agent-side stop get distinct messages. Why: one mistyped password ended the whole request, and a "Cryptography error" looked like a dead end.
- "Cryptography error, The decryption operation failed" documented (SKILL.md#unlock-refused): current bw unlocks via the SDK and prints this raw when the typed password does not open the locally stored key; usually a typo or another account's password, rarely stale local CLI data (human-decided `bw logout` + `bw-once login`, never automatic).
- `send-text` goes to the Touch ID broker when the target vault is enrolled (`--thread`/`--why` claim): broker validates and freezes name/text/views/date before any window, rejects invisible/bidi/control characters, keeps the text behind **Show text** (screen recordings), creates once with no retry (ambiguous failures `retry_safe: false`), locks + verifies before returning the link. File Sends stay on the Terminal (`bw serve` refuses them). Why: enrolled users asked why a Send still needed the master password.

## 2026-10-27 — recording-followups: the overview lists only what is left to trigger

- `recording-followups/SKILL.md` Deliverables: `followup-prompts.md` holds only prompts the user still has to launch or approve, each identical to its prompt file. An item leaves once its launch, handoff or completion is verified (even while the worker runs); prompt files stay, ids/links go to the debrief or a manifest. Nothing pending → no overview, or one line "No follow-ups left to trigger". The debrief status splits decisions waiting on the user from follow-ups already running; decisions owned by another thread are linked, not requeued. Why: overviews kept every launched and finished item, so the user re-read done work to find the one decision still theirs.

## 2026-10-27 — screen-share detection from the video, with a benchmark

- `detect-screenshare` rewritten: 1 frame/s at 320x180; Meet layout (gutter + a real filmstrip) only gates, the big tile's content decides (2 of 4 votes: flat pixels, grey pixels, static tile, no skin; plus some text edges); 10 s minimum run, gaps bridged while the share layout stays, 2 s padding. Why: speaker view looks like a share to a gutter rule (a 30-min 2-person call without share was 29 min "shared", crop on a face). Share-second precision 0.86 → 0.99 on 17 labelled calls, 0.96 → 0.996 on 5 held-out calls, recall ≥ 0.99, boundaries ±3 s (were up to 24 s). `--step` default 15 → 1; output drops `gutters`.
- New `benchmark/` (`make-clips` synthetic Meet clips, `run` scorer for any labelled set; README with sets, numbers, limits); its synthetic set runs in pytest. Real-call sets stay private, outside git.
- `recording-watcher`: screen share comes from the video, not phrases. A qualifying call with video starts a detached `visual` job (download → `detect-screenshare`, ≤ 3 at once) and waits as `visual-pending`; the brief then names the share ranges, video and plan paths, says "no screen share" (video deleted), or "visual coverage not assessed" on failure or after 45 min, never "no share". Why: the phrase rule (≥ 2 hits) sent a standup with 25 min of slides and live demo to transcript-only; on 11 labelled calls it judged, it missed 7 of the 9 with shares; the detector found all 9 and flagged neither no-share call. Spawns come ~1–12 min later (download). Removed: `SCREEN_SHARE_PHRASES`, `screen_share()`.

## 2026-10-27 — video-shrink-for-gemini: concise prompt, honest provenance, opt-in key frames

- `prompt-template.md` rewritten (489 → 435 words; agent-only lines moved to `agy-route.md`): one-line `{{PURPOSE}}` (who reads it; no diagnoses or suggestions), `{{LOOK_FOR}}` caller hints, "words to listen for" instead of a spelling quota, context = reference never evidence, quote the pixels, `[cut? …]` only for jumps without action or loading, `[redacted: kind]` for personal fields, opt-in `{{KEYFRAMES}}`. Why: benchmark on 7 frozen-fact clips (3–6 reps per arm, $4.31): non-inferior to the old template on small text, URLs, speech and speakers; engineering-doc jargon leaks 15 → 0, invented items fewer, Meet-clip privacy traps 6/12 → 9/12. New placeholders: callers filling the template must add `{{PURPOSE}}`, `{{LOOK_FOR}}`, `{{KEYFRAMES}}`.
- `transcribe-gemini` header: "Gemini draft of … Verification: none yet." (was "Verified transcript of"); SKILL.md: corrections go into the transcript itself and replace that line. Why: drafts were labelled verified before anyone checked, and side-file corrections never reached downstream agents.
- New `extract-keyframes TRANSCRIPT ORIGINAL [--offset S]`: cuts the ≤4 `## Key frames` stills from the original and links them. Why: stills showed what the text misread (status icons, an unticked list) for ≈0 Gemini cost.
- SKILL.md: two caller-brief examples replace the "30–80 terms" guidance.

## 2026-10-27 — T3 0.1.3 merged MCP tools: new names in docs

- `t3-manage-thread` (browser, workers, permission-ceiling), `bitwarden`, `t3-route` test cases: `preview_click/type/press` → `preview_act {action}`, `t3_queue_list/cancel` → `t3_queue {action}`, `t3_thread_configuration` → `t3_thread_configure` without `modelSelection` (= read). Why: T3 0.1.3 ([#25423](https://github.com/pingdotgg/t3code/pull/25423)) merged 18 tools into action tools; agents following the old names hit "tool not found". Needs T3 ≥ 0.1.3 (older T3 still has only the old names).

## 2026-10-27 — slides: presenter notes only when asked

- `slides/SKILL.md`: presenter notes are skipped unless the user, a wrapper or the deck's own doc asks; slides and the exported PDF must stand on their own. Why: the same "skip unless asked" line sat in all 7 project-slides wrappers; it is the better default for decks shared as PDFs, and decks that need notes already say so.

## 2026-10-27 — review fixes on the moved lessons

- clickup-core: `handoff` posts its text as the comment (append substance first, ping second); `review` already appends to the body, `--comment` only when wanted. Assignees kept unless reassignment is requested; who gets a new task is wrapper policy. Date-only fields: compare the local day, ClickUp normalises the time. slides: static `src` stays the default (keeps `--base`), `:src` only when the import guard trips. Why: opposite-model review found the moved wording overgeneralised (subpath decks broke, standard commands violated the body/comment rule).

## 2026-10-27 — browser.md: T3 preview and CDP gotchas from a personal wrapper

- `t3-manage-thread/browser.md` gains a "T3 preview" section (own tab, explicit `profileId` + incognito for untrusted pages, session-gated downloads, hidden-tab screenshot stall, popups, print-view trap, cross-origin iframes, paste in unviewed tabs, local HTML, blank window), Google password route past T3's missing passkeys, CDP tab/cookie/daemon mechanics and ending idle computer-use sessions. `agents-md/global.md` port step includes uncommitted edits. Why: these lived in the owner's private browser notes; every T3 user hits them.

## 2026-10-27 — global template: wrappers hold DNA only

- `agents-md/global-template.md` Skill docs: "Wrapper of a copied core = DNA only (accounts, ids, policy); a generic lesson goes to the canonical core." Why: agents improving a skill inside a consumer repo edited the local wrapper, so lessons stayed in one company's repo while colleagues and public users of the core never got them; an audit found generic workflows restated in wrappers across 10 repos ([core and wrapper](README.md#core-and-wrapper)).

## 2026-10-27 — wrapper lessons moved into nine cores

- `clickup-core`: body-is-record/comment-is-ping, listing someone's work (`active_statuses`), assignee invariant, new-ticket body and "deleted stays deleted", MCP-connector ban, screenshots read; `reference.md` gains description-Markdown rewrites and "Workspace admin limits" (statuses add-only, dropdowns UI-only, no auto-number, date-field timezone); new `review.md` for reviewing a ticket another agent wrote.
- `video-shrink-for-gemini`: `transcribe-local` sets whisper's anti-loop thresholds and takes `--prompt` (vocabulary → `--initial-prompt`); measured seeding evidence in `exact-identifiers.md`; agy quota/log checks; paused-recording timing, Claude cloud sessions, signed URLs, untouched vendor transcript.
- `recording-followups` "Colleague handoffs"; `slides` (only requested edits, Slidev `:src` and UnoCSS collisions, shorter wrapper template); `mailbox-review-core` report "Operator level" + brain-dev setup; `whatsapp-bridge` group-name check and original-language voice transcripts; `t3-manage-thread/mail-link.md` what is worth a case, reply recipients; `t3-route` Gmail evidence, building a trigger lookup, `t3-pick-instance` stderr; `microphone-calibration` bilingual sessions; `yuki-core` per-row fetch loop.
- Why: these generic lessons sat in wrappers in 11 repos (ClickUp, video, mailbox, slides, Yuki, routing, personal), so only one team saw each; every core user now gets them and wrappers can link instead of restate.

## 2026-10-27 — google-workspace-core: generic lessons out of wrappers

- New `references/mymaps.md` (My Maps: Drive discovery, browser/Data Portability export, UI-only edits). `drafts.md`: wrapper signatures (once, before quoted history, both alternatives) and "draft vs send is wrapper policy, default draft". `rest.md`: raw `api` pagination/bounded reads, Calendar via `api`, `doc-read --out`. `integration.md`: runnable import example, `ws.session.http`, `scopes` is a minimum not a ceiling, wrappers link instead of restating. `troubleshooting.md`: token lifetime (Testing 7 days; Gmail tokens die on password change) and the unverified-app notice/100-user cap. `auth export-token` wording corrected (writes a file). Why: PJ's personal wrapper had grown to restate these; every core user should get them.

## 2026-10-27 — core and wrapper: generic lessons live in the core

- README "Core and wrapper" + AGENTS.md: a repo's wrapper skill holds only its DNA (accounts, ids, config, brand, approval policy); workflows, gotchas and lessons another user benefits from go in the core, which the wrapper links. Why: wrappers in 10 repos had grown to restate core workflows and carry lessons colleagues never saw.

## 2026-10-26 — audit follow-ups: shorter schedule list, skill usage, claude-swap removed

- `t3-schedule list` (text/markdown) hides finished one-shot jobs; `--all` shows them, `--json` stays complete. Why: 266 of 323 jobs were retired; "what's scheduled?" cost ~34k tokens per call (135 KB → 20 KB).
- `t3-my-prompts --skills` counts distinct threads per installed skill (SKILL.md read, Skill tool, or a shipped command; invocations only, never tool output), with maintenance threads in the skill's own repo apart and unused skills listed. Why: see which skills are used, over- or underused, on any machine.
- Removed: codexbar-setup's legacy claude-swap path (`codexbar-profiles`, `claude-swap.md`); `codexbar-claude-usage` (t3-limits stand-in) replaces it, and `scripts/install` drops the old link and `com.t3-skills.codexbar-profiles.{sync,expiry}` jobs.
- `agents-md/global-template.md`: the auto-mode repair line reads as one clause ("…; data loss, production data, credentials, spend or private data → propose instead"); the preamble's review-doc line is gone (global.md merge step 4 already says it). Why: same rules, the double parenthetical read as one garbled clause.

## 2026-10-26 — skills audit: trigger descriptions, progressive disclosure, safe code cleanup

- Every `description` rewritten as a when-to-invoke trigger with user phrases and a "not for → sibling" line (total 1790 → ~1450 words, loaded in every session). SKILL.md entrypoints −26% (most-used 13: −34%), all docs −14%; rare paths moved to focused files (`t3-maintenance/{purge,archive,fleet}.md`, `mailbox-review-core/references/{go-deep,lessons}.md`, `claude-cloud/protocol.md`, `data-enrichment/references/capture.md`, `codexbar-setup/claude-swap.md`); model/account policy owned only by `t3-manage-thread/routing.md`, titles/briefs only by `workers.md`. Why: skills grew organically; capable agents need trigger + map + hard rules, not restated `--help`.
- README skill table ordered most-used first; adds recording-followups, claude-auto-mode, ui-before-after.
- Code, no CLI change: dead helpers removed (`clickup.set_description`, `loom.find_loom_urls`, `profile_registry` `__main__`, unused constants), t3-schedule `add` reuses `write_artefacts`, topup `profile_rows`; clickup-core lock gains `websocket-client` (`chat session` failed under `uv run --locked`); `t3-open-thread --link` escapes `|`; `t3-find-thread --include-archived` (no-op) hidden from help; recording-watcher briefs name `transcribe-gemini` as the video route. Public docs no longer name individuals.

## 2026-10-26 — slides: paraphrase spoken quotes

- Dictated or spoken words go on a slide as a tight restatement without quote marks; the verbatim source stays in notes or source files. Why: PJ's speech-to-text quotes read poorly on a teaching slide.

## 2026-10-26 — code review: round budget, scope guard, verdict line; one review doc

- `t3-manage-thread/code-review.md`: max 3 review rounds (4–5 only while an evidence-backed security/auth/data/money blocker stays open), stop when a round returns only nits, budget end/silence ≠ approval; findings labelled `blocker`/`should`/`nit` with stable ids; builder re-grades severity, cuts diff growth, reworks or escalates a wrong approach instead of patching the symptom; a misread only warrants an edit when the code is genuinely misleading; final report carries `Review: <model>, <N> rounds, <verdict>`. Why: Theo's sol-loop (youtube 5Bmp9cz1JN8) plus 16–26 Oct T3 data: 12 of 327 reviews ran past 3 rounds, one ran 11; builders summarising away the reviewer's dissent.
- Doc made harness-neutral with an "In T3" section; `agents-md/code-review-template.md` removed and its links point at the one doc. Why: the copy drifted within 10 days (missing confidence/skip/YAGNI rules, stale reuse-and-settle advice) and had no known reader.

## 2026-10-26 — contributing: direct commits for small, clearly shared changes

- AGENTS.md "Direct commit or pull request": collaborators with write access push small, confident, broadly useful fixes straight to `main`; uncertain or consequential changes go to a PR left open for the owner's review; personal/company config stays out of the core. Why: the owner's company teams now contribute, and a PR per typo stalled on one reviewer.

## 2026-10-26 — tls-trust-audit: CA distrust exposure, measured not guessed

- New skill. `tls_trust_audit.sh` classifies every CA bundle on the machine, live-probes each HTTPS client (curl, wget, git, every Python/Node install, Java, Go, the macOS OS verifier), compares tool versions and prints suggested remediation without running it; `tls_trust_remediate.sh` does the package-only half behind one confirmation (`-y` for agents). Per-incident data lives in `advisories/*.conf`, so the next advisory is a data file rather than a code change; eMudhra/emSign 2026-10 ships as the first one. Why: during that incident version numbers disagreed with behaviour repeatedly — `stripe` 16.0.0 was current and still shipped an affected bundle, `git` stayed exposed after Homebrew's `curl` was fixed because it reads the OS bundle, and two pending macOS updates predated the advisory so waiting for them could never have helped.
- The audit reports a distrusted intermediate's **cross-signing** root alongside the obvious one. Why: eight eMudhra intermediates were each cross-signed by Sectigo's `AAA Certificate Services`, so removing only the emSign roots left the same keys trusted, and a bundle holding no emSign certificate at all was still exploitable.

## 2026-10-26 — slides: final reply ends with absolute file paths

- The final reply lists the absolute path of each delivered file, the exported PDF first. Why: PJ opens the result in one click instead of hunting for it.

## 2026-10-26 — claude-cloud: token refresh ignores user-settings OAuth env

- The pre-expiry refresh turn runs `claude … --setting-sources project,local`. Why: a profile whose `settings.json` env sets `CLAUDE_CODE_OAUTH_TOKEN` answered the Haiku turn with that token, so the Keychain login was never refreshed and every export failed with exit 3 (kampkompas, 150 h stale).

## 2026-10-26 — bitwarden: base-domain matching with URI restrictions

- Python and signed Swift broker match registrable domains using a vendored ICANN + PRIVATE Public Suffix List. Saved Host narrows; Never excludes; Exact/StartsWith/Regex fail closed for host-only requests. Destination-origin pinning and exact session/re-copy destination scope remain.
- Approval and metadata expose match scope; per-vault `default_match` supports stricter client defaults. Browser/organization defaults and equivalent-domain aliases are not imported (documented). Versioned sockets prevent older holders from bypassing the new rules.
- Removed: exact-host-only guidance and saved-parent-host clipboard workaround; request the actual destination host instead.

## 2026-10-25 — clickup-core: ✨ on AI-written comments

- clickup-core 0.2.3: `comment`, `handoff` and `review --comment` start the comment with `✨ ` (own line before a leading code block/table; never doubled); `--no-ai-label` for a human's own words. Why: every comment shows the token owner as author, so readers could not tell agent text from the operator's; ClickUp's comment API has no AI/author-badge field (unlike WhatsApp's native AI label).

## 2026-10-25 — google-workspace-core: account inventory and cross-mailbox Gmail lookup

- `gws.py accounts list [--check] | discover ROOT… | locate REF` over a per-user inventory (`~/.config/google-workspace/accounts.json` or `$GWS_ACCOUNTS`): wrapper config paths plus `gmail_lookup`, the user's standing permission to try exact references in that mailbox. Why: a pasted Gmail link rarely names its mailbox, and agents either stopped at the first token or improvised across credentials.
- Lookup is metadata-only (`format=minimal`), verifies each mailbox's Gmail identity first and stops at the first holder; 403/auth/identity errors and skipped mailboxes are unknown, never "not found". `--config` is refused: an explicit account never widens.
- Print-all links of a thread you started (`permthid=thread-a:r…&simpl=msg-f:…`) resolve through the `msg-f` refs; `thread-a` is never converted. `gmail-thread`/`gmail-url` accept Show-original and such links via the same lookup.
- t3-mail-link: `resolve|find --all-accounts` for links that name no account; its own Gmail-ref parser is replaced by the core's `gws_core.accounts` (needs a core copy that has it: refresh or unset `GWS_CORE`). t3-route intake/onboarding use it.

## 2026-10-25 — clickup-core: attach several files in reading order

- clickup-core 0.2.2: `attach ID a.png b.png c.png` uploads last-first, so ClickUp (newest first) shows and steps through them in the given order; SKILL.md: real screenshots beat mockups. Why: a 7-screenshot test ticket read backwards in the viewer, and the mockups confused the reader once real staging screens existed.

## 2026-10-25 — google-workspace-core: account-stable links

- google-workspace-core: `gws_core.links` (`gmail_url`, `gmail_thread_url`, `gmail_draft_url`, `with_account`) + [links.md](skills/google-workspace-core/references/links.md). Every link handed to a human names the account by `authuser=<email>`, never `/u/<N>/`. Why: N is sign-in order, so a sign-out/sign-in reshuffle opened the wrong mailbox; `thread_url` now delegates here.

## 2026-10-25 — WhatsApp attachments

- whatsapp-bridge: native `send-document` / `send-image` CLI and Python APIs, local file validation, short captions and acceptance receipts; existing allowlist, locking, pacing and AI badge policy preserved.
- Self-chat-only E2E policy and document-first guidance for long prompts/reports replace throwaway send scripts.

## 2026-10-25 — t3-route: router boundary and launch mechanics in the core

- t3-route: the routing thread does intake/dispatch only; multi-model research launches one execution lead that runs the independent `delegate_task` opinions and reconciles them (models: user choice, else wrapper default). Spawn preflight (finish lookup edits, fold in steering, match delivery to the target's remotes). Why: these lived only in one private wrapper, so other operators' routers missed them.
- t3-route intake: owner-absent checks (message timestamps, launch receipts) and `/u/N` ≠ mailbox identity; corrections: "would another operator's router need it?" decides core vs wrapper.
- t3-manage-thread: launches pass `runtimeMode` explicitly (omitted, it inherits the caller's mode, not the app default); replacing a live owner waits for its observed stop. Router reset titles keep `🧭`: `t3-mail-link` relies on it to keep routers from owning mail cases. dispatch-workers defers lead model and titles to the operator instead of naming models/projects.
- monologue: share-page UUID can differ from the API note id; on 404 scan the date and match.

## 2026-10-24 — t3-maintenance archive + secret check for every user

- Global template: one line "With skill `t3-maintenance`: a secret passed through a thread → `t3-thread-archive check` …; a miss → rule + synthetic test, PR to `pjmuller/skills`; settling redacts nothing". Why: every user's agent should test whether a credential that crossed a thread would survive the archive, and contribute the missing rule instead of shrugging.
- t3-maintenance: "A miss → PR upstream" steps; no local rule file, because `threads.redaction`, `scrub` and stale detection assume one rule set and a patched installed copy blocks every `skills-refresh` update. Optional weekly `t3-schedule` reminder that reports the purge cohort and asks; purge itself stays manual.
- Rule change → `sync --force` + `scrub` immediately, without asking. Why: both only read T3's store and rewrite the archive with verification, safe with T3 open (~5 min for a 500 MB archive); waiting just leaves the secret readable in the archive.
- Onboarding: README row and `t3-setup` install block offer t3-maintenance (purge frees disk and drops pasted secrets; the archive stays searchable).

## 2026-10-24 — bitwarden: explained Keychain prompts, 15-min re-copy, username-first

- Keychain dialogs on every request had one cause: the ad-hoc signed broker is trusted by code hash, every rebuild changes it, and "Allow" (not "Always Allow") grants one read. The broker now probes silently; when macOS will ask, a bw-once window says so first ("Always Allow" both times), `touchid status` shows `keychain_prompt: true`, and the installer prints a note on rebuild. A local signing identity was rejected: re-trust would become silent for any same-user code.
- Re-copy without a touch: after a released username/password with `--thread`, the same thread naming the same login (`--id`/`--username`) gets it again for 15 min (`recopy: true`), shown in a small focus-free window; the green box discloses it. Why: one Google sign-in plus gcloud OAuth asked three times for one approved password. TOTP excluded.
- `list --username` narrows; the agent recipe says `copy --username` when the account is known (no `list` across every login) and to click the field again after the touch (the bw-once window takes focus; a paste landed nothing).

## 2026-10-24 — t3-maintenance: secret check, treg.to tokens

- `t3-thread-archive check`: stdin → `true`/`false` through the archive's own redaction (categories on stderr, never values; exit 0/1). Agents can test whether a secret would survive the archive.
- Redaction v2: treg.to API keys (`treg_` + 43 URL-safe chars) are a vendor token; standalone they slipped through as a "typed id". Existing archives: `t3-thread-archive sync --force`, then `scrub` (`--dry-run` first).

## 2026-10-23 — CI on every change; scheduler, purge, gitsync and bitwarden hardening

- CI and the documented test command run the suite with `pytest-xdist -n 4` (about 3x faster); the bitwarden signal test runs in its own process so it is xdist-safe.
- CI: the full suite runs on every push to `main` and every PR (it ran only for lock/workflow changes, so script-only commits were never tested); T3 portability also on push. macOS-only bitwarden tests skip on Linux, so CI is green again.
- `t3-schedule`: an accepted-but-unconfirmed launch now survives midnight and blocks later fires until `t3-relay status` decides; a late confirmation counts for the day it was fired, and a once-job is no longer retired as "never fired" while its launch is still pending. `fire` takes a per-job lock (a launchd run and `run-now --foreground` could double-launch on macOS); specs and markers are written atomically, and an unreadable spec skips only its own job.
- `t3-purge-threads`: Codex transcripts are found in every Codex instance `homePath`, not only `~/.codex`. Its tests now isolate every path it deletes from.
- `gitsync`: one checked `git status` read; a failing read is "unverified" (status) or needs a worker (survey), never clean, landed or fast-forwarded. New claims get a random request id (two claims in the same second reused one).
- bitwarden: the broker releases nothing once 300 s passed since the request, renewal panels included, so the front end's "nothing released" after its timeout is true.
- google-workspace-core: the mail-cases link is absolute, so it works in vendored copies.

## 2026-10-23 — skills-refresh: no runaway t3-schedule refresh

- `skills-refresh` bounds its `t3-schedule refresh` calls (300 s, then TERM/KILL). Why: under a foreign HOME the mise `uv` shim exec-loops at 100% CPU forever; three such processes from test runs burned cores for hours.
- Its test suite stubs `t3-schedule` in the shared fixture, so no test reaches the real one (which would also re-arm the user's launchd jobs).

## 2026-10-23 — scoped auto-mode policy repair

- New `auto-mode-policy`: reusable correction playbook, private setup template, and Codex policy sync with complete-default preservation, drift checks, backups and profile coverage. Claude keeps its existing adapter.
- Global template: a scoped user correction authorizes its durable policy repair; no second “go” or Full Access by default. Why: missing context trust was turning routine delegated work into repeated permission requests. Personal data roots and account grants stay in private overlays.
- Onboarding now covers both engines; Claude policy guidance distinguishes an authorized repair from bypassing a denial.

## v0.5.11 (2026-10-23)

- **History rewrite (sensitive data removed).** Commits from 6 Oct onward and tags v0.4.4–v0.5.10 were rewritten to drop accounting details that had been published by mistake. Tags were re-signed with the same key; files at every tag are unchanged apart from the scrubbed lines. `skills-refresh` users need nothing: this release moves them onto the new history. Anyone with a **git clone** of this repo: re-clone, and never merge or push the old history.

## 2026-10-23 — clickup-core: images and links inside table cells

- Table cells carry the same inline markdown as a paragraph (links, bold, mentions); a cell made only of
  `![](url)` images shows them, and `![[file:NAME]]` shows an attachment as an image. Why: before/after
  screenshot tables showed raw `[name](url)` text instead of the pictures. Verified by readback and the
  rendered task page.
- A bare attachment filename inside `**bold**` is no longer auto-linked (the nested link made ClickUp split
  the URL and the readback check fail).
- ui-before-after: `ticket-table.md` uses `![[file:…]]`, so the screenshots show inline in the ticket.

## 2026-10-23 — ui-before-after; feedback rounds; Codex sandbox note

- New skill `ui-before-after`: `ui-shoot` (Playwright scenes → screenshots) and `ui-compare` (manifest →
  self-contained before/after HTML for a ticket, a tiny `compact.html` for T3 `html_render`, ClickUp table
  + matching attachments). Why: a taste reviewer judges a shipped UI change by looking, same state twice.
- recording-followups: `feedback-round.md`, the playbook for implementing a narrated product walk-through
  in one thread (triage, parallel root-cause workers, BEFORE shots before edits, taste-owner ticket).
- video-shrink-for-gemini: feedback-walkthrough block in the prompt template (feedback items with
  wall-clock, the speaker's diagnosis is not "what was visible"); pass the app's UI copy as context.
- t3-manage-thread workers: Codex `delegate_task` children have no network and no Docker; brief them so.
- global template, Delegation: many items or deep topics → fan out read-only investigation in parallel (one
  sub-agent or `delegate_task` child per cluster) before building. Why: a 19-item feedback round was
  root-caused serially in the lead; the parallel version is faster and goes deeper per item.

## 2026-10-23 — bitwarden: agent picks among several logins, one touch

- `copy` without `--username`/`--id` on a host with several logins no longer fails after the touch: the vaults lock,
  the answer carries `pick` (token, candidates: vault/id/name/username), the window lists them, and
  `bw-once pick --token … --id …` within 60 s releases the chosen one (shown in the window). No second touch.
- SKILL.md agent recipe: click the password field before asking, run in the background, thread title from
  `t3_thread_list`, the pick step.

## 2026-10-23 — global template: 🔓 for auto-mode blocks

- New status emoji 🔓 = blocked only by auto mode; the ask starts with it. Why: an auto-mode block looked like any
  other question, so the human missed that one click (switch the thread to full access) unblocks the agent.

## 2026-10-23 — bitwarden: broker owns the clipboard; stable builds

- The broker writes released secrets to the clipboard itself (previously piped to the separate, unverified
  `clipboard` helper, which a replaced file could have captured silently); a detached copy of the broker clears
  its own unchanged write after 30 s.
- The installer rebuilds the broker only when `broker.swift` changed (builds aren't reproducible; every rebuild
  meant a new Keychain prompt). A bw-broker Keychain prompt outside an update = deny.

## 2026-10-23 — bitwarden: phrase stays put

- The first setup window labels its phrase "NEW" (it becomes yours on Save); later windows say "Your phrase".
  An unreadable Keychain item (e.g. the post-update prompt denied) stops setup instead of minting and saving a
  new phrase.

## 2026-10-23 — bitwarden: compiled Touch ID broker

- New `scripts/broker.swift` (built by the installer, hardened runtime) owns the whole Touch ID path: a native
  window with the human's 3-word phrase, the agent's claim (`list`/`copy` `--thread`, `--why`, marked
  unverified) and the checked request; Touch ID; master passwords of **all** enrolled accounts in one
  Keychain item (ACL = the broker) sealed to a Secure Enclave key; Bitwarden's signed CLI (downloaded by the
  installer, Team ID checked on the file and the running process) as one `bw serve` per vault over a
  socketpair (~1.5 s instead of ~20 s of CLI starts); exact-host search across accounts; lock + verify every
  vault before the clipboard. Renewal inline (setup window with the phrase) only when fingerprints or a master
  password change; no expiry.
- Removed: `scripts/touchid.swift`, the per-vault `~/.config/bw-once/touchid-*.json` enrolment, the Terminal
  renewal prompt and the 30-day expiry. Replacement: `bw-once touchid enroll` once (old files are deleted).

## 2026-10-23 — bitwarden: Touch ID renews itself

- Expired enrolment, changed fingerprints or a changed master password no longer need `touchid forget` +
  `enroll`: the next request opens the Terminal directly (no wasted Touch ID dialog), and the master password
  typed there serves the request and re-seals Touch ID for 30 days. Breakage found during an in-process
  request relaunches that Terminal in the same call; a cancelled dialog doesn't. `touchid status` →
  `renewal_due`. Only `touchid forget` turns it off.

## 2026-10-23 — t3-maintenance: the thread archive redacts secrets

- New `scripts/t3_redact.py`: deterministic rules (vendor token prefixes, secret-named assignments,
  auth headers/cookies, URL passwords and secret params, private keys, long random runs), tuned on
  aggregate counts of the real archive so ids, hashes, paths and Drive ids stay searchable.
- Every archive write (purge, `sync`, `import`) redacts; text is redacted before any clip, so a cut
  can't keep a value without its key. `t3-thread-archive scrub [--dry-run]` re-redacts an existing
  archive (fresh rebuild, verified, atomic swap). Per-thread `redaction` version, a `scrub_required`
  marker for FTS residue, a writer lock and a trigger that stops pre-redaction writer copies.
- No LLM in the loop (it would see the values again). Limits: docstring of `t3_redact.py`.

## 2026-10-23 — bitwarden: Touch ID unlock

- `bw-once touchid enroll` (human Terminal, once per 30 days): the master password, verified by a real unlock,
  is sealed to a Secure Enclave key that only works after Touch ID (`.biometryCurrentSet`, hardware-enforced,
  no signing certificate needed). Enrolled `list`/`copy` then run without a Terminal: one fingerprint per
  request, dialog text built from the request, password piped to the Homebrew `bw` (`--passwordfile /dev/fd/N`),
  vault relocked before delivery. Sessions/Sends keep their Terminal review with Touch ID instead of the password.
  `touchid status|forget`; `doctor` shows enrolment. Design, rejected alternatives, boundary: `touchid.md`.

## 2026-10-23 — t3-route: one term, "routing"

- Why: "dispatch" and "routing" named the same thing (the skill is `t3-route`, its docs said dispatch). Now
  **routing** everywhere; the conversation is the **routing thread**; placing a task is "launch" or "continue".
  Rename your wrapper's wording and the thread title (onboarding suggests `🧭 Routing`); behaviour is unchanged.
  `dispatch-workers.md` keeps its name: batch worker launches, a different concept.
- t3-mail-link: routing threads are recognised by a leading 🧭 in the title (legacy "dispatch" titles still
  match); the excluded reason prints `routing` (was `dispatcher`). "routing" alone is not matched, so a
  "Fix Rails routing" thread can still own mail.

## 2026-10-23 — bitwarden: one unlock per login

- `bw-once copy --host H --username U --field password` picks the only exact-host login in the same unlock
  (no `list` first); zero/several matches fail before delivery. Candidates come from an unfiltered
  `bw list items` inside the helper: bw's `--url`/`--search` hide items with Exact/StartsWith/regex rules.
- `bw-once clear` drops our clipboard write right after the paste (only while it is still ours).
- Terminal: bell, hidden "press Return" approval (an early-typed password is discarded), 6 min locked wait
  for the human, then 180 s for the unlock; errors name the failing bw step. No Touch ID promise: it needs
  Bitwarden's `biometrics-sdk-ipc` server flag (still off on EU).
- `session stop` answers only after a verified lock.
- Docs: T3 incognito is one in-memory partition shared by all threads (not per thread); agent logins use it,
  then site logout + verify + close tab; never log out in Work.

## 2026-10-23 — bitwarden: Send expiry via --days

- `bw-once send-text|send-file --days N` (1-31, default 7): expiry and deletion date; shown in the approval.

## 2026-10-23 — mailbox-review-core: ReplyPen mailbox review moves here

- New core (was `rp-mailbox-cockpit` in replypen/replypen-brain-skills): collect/detail/validate/apply/render
  for unsent ReplyPen drafts, Opus reviewer recipe, research-first operating mode (default corrections
  per wrapper, own T3 thread per confirmed bug, operator-level explanations, end ledger). Project
  wrappers (`mailbox-review`) own mailbox, accounts, repos and policy.

## 2026-10-23 — gitsync: git hygiene is its own skill

- New skill `gitsync` (moved out of t3-maintenance): `gitsync survey|prepare|record|status`, worker
  playbook `worker.md`, own installer. Default `--fresh-minutes` 60 (was 30). State moved to
  `~/.local/state/gitsync`, env `GITSYNC_STATE`.
- Removed: `t3-git-leftovers` → `gitsync` (both installers retire the old link).

## 2026-10-23 — t3-git-leftovers: the orchestrator delegates, claims span runs

- The calling T3 thread runs one `delegate_task` child per judgment repo (results return to it for
  verification): `prepare` claims repos and writes briefs, `record` stores task ids. `dispatch`
  (standalone `t3-relay` workers, title adoption, `--wait`) is gone; children no longer self-settle.
- Claims in `~/.local/state/git-leftovers/claims.json` cover every run and date: another orchestrator
  (e.g. the weekly job) gets `held_elsewhere`; a rerun resumes with the same request ids.
- Survey: interactive vs scheduled (`⏰`) thread counts per repo; `--apply-ff` skips checkouts a live
  thread works in; an unreadable fleet now aborts instead of hiding live owners.
- `status`: `landed` needs an upstream, nothing ahead and no stale dirt; leftovers are `protected`
  only with a named reason (fresh path, live thread); no upstream = `local`.

## v0.5.10 (2026-10-23)

- skills-refresh: the template-history cache force-updates tags. After an upstream history rewrite, the re-signed tags made every later prompt re-sync fail daily ("cannot fetch … retrying tomorrow"). Releases themselves already survived a rewrite: each apply fetches the exact tag into fresh staging and verifies its signature. Recovery after a rewrite = one new signed release (`scripts/release`). Old releases re-created under the same name stay installed until then.

## 2026-10-23 — agents-md global template: no revert recipe in reports

- Autonomy rule: "report what you did" (dropped "+ how to revert": clutter in most reports).

## 2026-10-23 — yuki-core: tenant details come from the wrapper

- `fetch-invoices.md` reads tenant URL, Visma login and mail-in address from the wrapper's `yuki.json`
  `web` object (informational, agent-read; see `templates/yuki.example.json`); missing `web` blocks
  browser delivery only. Company-specific examples, names and paths replaced with neutral ones.
- google-workspace-core / yuki-core tests use neutral fixture accounts and labels.

## 2026-10-23 — t3-purge-threads: fast, verified, smarter keep

- Set-based deletes (one per table, one transaction): a 2,100-thread purge went from ~11 h to
  under 4 min end to end; per-phase/table progress.
- `--full-backup` verifies the copy (integrity + per-table row counts) before deleting anything.
- Keep rules: default `--older-than 7d`; open PRs and real conversations (8+ typed messages or
  typed on 2+ days) are kept with a reason. `--json` key `kept_pending_wake` is now `kept`.
- `--full-backup` keeps only the newest verified copy (it replaces the previous run's).
- t3-find-thread: `read --limit 0` exports a whole (purged) thread; SKILL.md documents reviving it
  in a fresh thread.

## 2026-10-21 — account routing and recovery

- Route away from half-spent sessions burning ahead of pace; remove inherited-account
  tie preference. Generic model requests never imply repository/account affinity.
- Support identity-bound, operator-confirmed size metadata for profiles with no plan
  label; warn when unknown tiers demote available capacity. No credential changes.
- Extend `t3-fleet list` with compact limit/lineage diagnostics, including queued and
  misleadingly completed failures. Document native continuation and per-spawn picks.


## Unreleased

- **microphone-calibration: faster takes, hardware knob.** No spoken prompts: one beep, and each take ends 0.8 s after the speaker stops (live detector on a 16 kHz copy of the stream; the 24-bit WAV stays untouched), capped by `--seconds` (default 8). Noise floor = quietest 20% of frames, no dedicated silent wait. `--manual 'knob as is,knob +50%,soft voice · 5 cm,…'` (alias `--knob`) appends takes at the gain picked from the sweep, one per setup the speaker makes by hand (knob, distance, voice), Enter before each, `r` + Enter redoes a slipped take; the report adds a manual pick. `--wait` is now the window to press Enter; the agent then waits as long as takes progress. Transcripts that only leave words out (no word misheard) are marked “slip?” and no longer rank takes: a live run's knob pick flipped on one forgotten half-sentence. `--keep-gain --manual …` for mics without software gain.

- New `public-footprint-audit`: consent-based public-web privacy research, evidence states, concise lockdown checklist and removal rechecks. Keeps personal findings outside public skill sources.

- agents-md template: explicit “auto-settle” defaults to settling after verified completion; keep open only for material findings, risks or decisions needing human attention. Why: the sidebar should surface work requiring the user's eyes, not routine results.

- t3-manage-thread: workload-aware routing. `t3-pick-instance` ranks by `score × session left / (1 + live load)`; load comes read-only from T3's store (`lib/fleet_load.py`: owners on their actual run account, native sub-agents folded by max, queued/held/orphan/quiet handled, `routing-load: heavy` launch-line = 3). Missing store → quota-only with a warning; `T3_ROUTING_LOAD=shadow` keeps the old pick. Explanations show each reading's real age and observation gaps; picks are logged to a bounded local `t3-routing-decisions.jsonl`. Why: 2026-10-22 six launches in 40 s all went to the account already running 7 jobs.
- google-workspace-core: `gmail-draft`/`gmail-send` always build `multipart/alternative` (authored plain text + escaped HTML twin). Gmail web opened plain-only drafts in Plain text mode and hard-wrapped them at ~70 chars when a human clicked Send (verified with test sends). From now defaults to the mailbox's default send-as identity (`Name <alias>`), `--from` picks another alias. Fix: `gmail-thread --full/--max-chars` (were registered on `gmail-url`, crashed every `gmail-thread`).
- t3-manage-thread: new `permission-ceiling.md`. When an Auto thread must message a Full Access owner (`runtime_mode_escalation_denied`): preflight both modes, keep the continuation in a brief, one user action (paste in owner, optionally after switching it to Auto; or user raises the dispatcher to Full Access, then one idempotent retry). `t3_thread_configure` changes model/account only, never modes; `t3-relay` is no bypass. t3-route continuation + intake link it; fixture case 16.
- t3-setup: new "Auto mode (Claude)" step (install `claude-auto-mode` repo-local, personal + company overlays, T3 default Auto) plus verification. Why: new colleagues get the auto-mode setup in the one bootstrap prompt, no separate prompt.
- **New skill `claude-auto-mode`**: shared Claude Code auto-mode baseline (deploy via the repo's listed channel after tests + prod diff, code edits are not the deletion they implement, reads after an unrelated denial, vendor cleanup with export + ID file + dry run + `--max N`, force-push hard deny) plus `scripts/merge.py`, which merges it with private company overlays (`.agents/claude-auto-mode.json`) into every Claude home. Why: Claude Code ignores `autoMode` in repo settings, so each machine needs it in user settings; one baseline keeps colleagues' agents as autonomous as PJ's without per-person research.
- agents-md template: the auto-mode line now points to `claude-auto-mode`. Why: one place for the rules instead of hand-written `autoMode.environment`.

- Tests: replace removed `load_module()` imports with `exec_module()` so Python 3.15 can collect relay, scheduler and top-up tests and run the native scheduler smoke check.

- t3-relay: launches use the user's new-thread permission default (`defaultRuntimeMode`, e.g. Auto) instead of always `full-access`; unset keeps `full-access`.

- agents-md template: auto-mode rule (ask once naming the exact action instead of working around a block; fix repeated false blocks via `autoMode.environment`, keeping `$defaults`).

## v0.5.9 (2026-10-21)

- **t3-relay: launches into any project again.** v0.5.6 read only the first page of `t3_project_list` (20 projects), so launches into later repos failed with "no T3 project". Now follows the cursor.
- **Browser: explicit escalation order** (`global-template.md`, `t3-manage-thread/browser.md`): (1) T3 browser with an explicit `profileId` on a new tab; (2) only when T3 can't (missing login, site breaks, passkey, OS dialog) the user's Chrome over CDP and/or computer use, never on T3's own browser. Why: agents need one clear signal for which browser to try first and when to fall back; the old "computer use never for browser work" rule blocked a useful fallback. Also: a reused tab silently keeps its old profile (new tab per profile), and Google sessions don't survive cookie import (sign in inside T3). Verified on T3 0.1.1 in Claude and Codex.
- **skills-refresh installs without T3.** The daily job now runs `skills-refresh --apply` as a t3-schedule `--pre-command`, before T3 is even checked; the T3 thread only reports (changelog, template re-sync, ACTION NEEDED). A release that repairs broken T3 tooling therefore lands by itself (v0.5.6, the relay fix, could not reach machines already on T3 0.1.1: the job ran through the broken relay). Existing jobs gain the pre-command on their next run; commit the changed `.agents/schedules/skills-refresh.json` when the thread asks.
- **t3-schedule `--pre-command CMD`**: runs in the runner without T3; nonzero exit notifies once per day, the fire still follows. Notifications under WSL now reach Windows (tray balloon via `powershell.exe`); `t3-schedule notify <msg>` tests it.
- Maintainer `scripts/release` refuses to tag unless a real `t3-relay launch` probe succeeds.
- **t3-preview-gc: no more window crash-reload.** Since T3 0.1, closing a preview tab frees its renderer (verified on v0.1.1), so `--apply` only closes the tabs of settled/archived threads idle past `--idle-hours` and logs renderers before → after. Removed: `--min-guests`, `--quiet-seconds`, `--wait-minutes` and the UI-renderer SIGSEGV + View → Reload fallback (no replacement needed).

## v0.5.8 (2026-10-21)

- skills-refresh: `git check-ignore` runs without literal pathspecs (v0.5.7 printed a `fatal:` line on every commit and could misjudge an ignored skills dir).

## v0.5.7 (2026-10-21)

- **skills-refresh: no more silent breakage on consumer machines** (feedback from a colleague's v0.5.0 → v0.5.4 upgrade). What only you can fix now ends the output as one `ACTION NEEDED` block and keeps the job thread open, also with `--quiet`, every day until fixed. Previously a missing relay was a warning above a long changelog, and the scheduler failed for 3 days with only a log and a once-a-day banner. Sources: the scheduler health check (`t3-schedule install --check`, every run, also when up to date; lists obsolete relay webhook tasks); commands a release removed that your global prompt or own skills still call (file:line); commit/push problems. Manual `skills-refresh` prints the same block plus a hint when your prompt's template marker is behind the installed tag (only `--job` merges).
- **skills-refresh: owns its output in a git-tracked skills dir.** When `~/.agents/skills` lives in a setup repo, every run commits exactly the managed skill dirs whose release files are unedited. It pushes them to the branch's upstream only when every unpushed commit is its own. A failed commit or push is an action, retried daily. A managed copy whose release files you edited blocks the next apply and lists the files, instead of being replaced silently. Commit, edit guard and removed-command scan start with the release after this one: the old script runs this apply, so no release fingerprint exists yet.
- skills-refresh template re-sync: the merge brief cites the CHANGELOG entries since the base as the why per change. At most one delegated merge per release per 24 h, so a catch-up run can't start a second one beside a running merge.
- Skills with Python ship a `.gitignore` for `__pycache__`, so running them in a git-tracked skills dir no longer leaves it dirty. `t3-maintenance` / `t3-usage-windows` descriptions are quoted (`skills update` reported a YAML parse error); a test now checks every frontmatter.
- README: pin repo-local copies to a release by tag URL (`skills add https://github.com/pjmuller/skills/tree/vX.Y.Z/skills/<name>`); `skills update -p` keeps the ref.

## v0.5.6 (2026-10-21)

- **t3-relay: direct MCP client, no relay host (fixes T3 0.1.1).** T3 0.1.1 ([#20447](https://github.com/pingdotgg/t3code/pull/20447)) frames webhook placeholders as untrusted data, so the Haiku/Luna host refused every request. `t3-relay` now calls T3's own loopback `/mcp` (`t3_thread_launch` / `t3_thread_send`) as OAuth MCP client `t3-relay` (full-access), approved by a pairing code from the local `t3 auth pairing create`; 30-day token cached 0600, renewed automatically. Output and exit contract unchanged for callers; exit 0 now means the thread/message exists. Migrate: `t3-relay check` lists the old `⚙️ T3 relay` webhook tasks: delete them, settle their host threads ([relay.md](skills/t3-manage-thread/relay.md)).

## v0.5.5 (2026-10-20)

- **skills-refresh: pinned SSH-signed releases.** Verify the exact tag object, signed name and commit before checkout/install; reject unsigned, unknown-key, tampered, renamed and automatic downgrade releases. Tests and forced tags cannot bypass trust. Prompt re-sync uses the verified commit recorded in the stamp. New maintainer `scripts/release` explicitly signs and verifies before publishing. First enrollment is TOFU; key rotation needs an old-key-signed bridge ([trust and rollout](skills/t3-manage-thread/skills-refresh.md#trust-and-bootstrap)).
- **t3-mail-link: drafting claims the mail case; no registry; triage before waking.** gws `gmail-draft`/`gmail-send`/`gmail-draft-update`/`gmail-draft-send` print `Mail-ref: gmail:<thread> <account>`; the poller reads it from T3's recorded command output, so the thread that drafted owns the case (sub-agents map to their parent; latest claim wins; "dispatch" threads never own). New `claim [--for ID]` / `release`; `add`/`unlink` removed, `mail-links.json` migrates once to the rebuildable cache `mail-watch.json`. New inbound mail: auto-replies skipped by headers, the rest triaged by Haiku (fail-open) before the wake. Poll every 30 min (weekdays 08:00-18:30). Run `t3-mail-link --config … schedule [--policy FILE]` to watch an account and re-arm.
- **t3-mail-link / recording-watcher: a relay-accepted ping or launch can no longer be lost.** Both now call `t3-relay … --wait 120` and mark mail seen / a call spawned only once the effect exists. Accepted but unconfirmed → recorded as pending and re-checked with `t3-relay status` next tick (landed → done; failed → resent; never resent while pending; reported after 30 min / 1 h). Previously HTTP 202 counted as delivered, so a failed relay host turn dropped the mail ping or the recording follow-up.
- settle-thread / AGENTS.md: settling stops in-session sub-agents, not `delegate_task` children (their result wakes the parent).
- **microphone-calibration (new): find the best input gain for dictation.** `mic-calibrate run` records the same sentence once per gain level (beep-driven, bounded, Enter to start in a Terminal window because agent shells have no TTY and agent apps may lack microphone access), restores the original gain on finish, Ctrl-C or window close, then writes `report.md`: peak/clipping, noise floor, speech level, SNR (beep removed by its tone), local Whisper transcripts with word error rate (no hint), playable clips and one tested recommended level. Devices without software gain are refused for sweeps (`--keep-gain` for knob positions and A/B samples). Gain is set on every channel element (some USB mics have no main control).

## v0.5.4 (2026-10-20)

- **skills-refresh: global prompt re-sync.** After each run the job compares the template marker in your global prompt (`<!-- template: pjmuller/skills@… -->`) with the installed tag. Changed template → a frontier `delegate_task` child merges three-way (base, released template, your file): commits clear improvements, your facts/rules/deletions win, logs skips in `template-decisions.md`, asks about the rest, bumps the marker. Uncommitted prompt edits → it only recommends; no marker → base inferred from the prompt's first commit. Marker at the tag → no network, thread settles as before. Existing jobs need nothing: the first run rewrites an older `.agents/schedules/skills-refresh.prompt.md` (keeps the thread open once: commit that file), delegation starts the next run ([skills-refresh.md](skills/t3-manage-thread/skills-refresh.md)).
- t3-manage-thread: provider aliases select Astra (OpenAI/Codex) or Opus (Claude); relay defaults to Opus then Astra. Instance-only launches infer the provider default and capacity-route within the named account; explicit models/efforts survive. Document native T3 inheritance separately. Fresh delegates for independent opinions; distinct outcomes keep separate threads.

- agents-md: OpenAI entrypoints use Astra (house medium); direct Sol for code review, with Astra free to choose scoped workers. Preserve explicit user choices and account routing; no silent Astra-to-Sol orchestration fallback.

- **t3-mail-link find: which T3 thread owns this mail.** Read-only: resolves a pasted Gmail URL/id (Print-all `thread-f`, `msg-f`, verified `msg-a` drafts, hex) with the account verified, then searches T3 (purged archive included) for every hex/decimal form of the thread and its messages. Ranks mail link > `Mail-ref:` marker > id; dispatcher titles and `--exclude` ids are listed as intake; no id hit → subject fallback flagged weak. `resolve` JSON adds `marker`. Convention (t3-route intake, google-workspace-core, mail-link.md): T3 briefs/reports on mail carry `Mail-ref: gmail:<hex thread> <account>`, never the mail itself. Previously a decimal URL id found only the dispatcher.
- **t3-manage-thread / agents-md: one ownership rule.** Native `delegate_task` child = ping-pong inside one task (planning opinion, scoped research, opposite-model review; cross-provider included). Standalone `t3_thread_launch` = independent topic, another repo's work, explicit standalone ask, or a selected recording follow-up (recording-followups: never a child of the intake thread). Every review round is a new `delegate_task` with full context; `childThreadId` only for short same-conversation clarifications. Global template + `global.md` carry the one-line rule.
- **recording-followups: human-first prompt shape.** Prompts open with the moment in the call and the concrete case (bug: what came in → what we answered → why wrong; request/research/mail: who asked what), then the broader question and 2–4 next steps; repo, skills, Class/Lifecycle, evidence ids and verify/ship move below a `---` agent block. The old "repo + skills first" order made the user open the ticket to recall the item. Two neutral examples in `prompt-shape.md`; overview gets one current status line.
- t3-schedule: drop the `--settle-when-done` + 🏓-title guard (launched threads are never 🏓 children). dispatch-workers: dispatched items are 📤.
- t3-limits: a Claude profile with only a setup-token reads usage from one tiny Haiku CLI turn (only while a session window is open); a Fable turn checks the Fable weekly cap every 2 h. codexbar-setup: `codexbar-claude-usage`, a read-only claude-swap stand-in fed by t3-limits. t3-usage-windows warm-ups pass `--allow-small-model`.
- t3-mail-link: re-`add` keeps the seen baseline; `add` verifies the account; failed T3 pings notify.
- data-enrichment: `geocode.py` forward geocoding, Mapbox (temporary results) or Geopunt (storable, Flanders/Brussels).
- whatsapp-bridge: `wa voice --transcribe --hint` downloads and transcribes voice notes (via transcribe-gemini, which now sends audio as audio).
- recording-watcher: a speaker without a vendor email carries `name:<display name>`, so the roster can claim it. recording-followups: clearer execution cues.
- t3-manage-thread: thread links keep the threadId verbatim; scoped recovery for stale provider health. google-workspace-core: API enablement vs token renewal in troubleshooting.

## v0.5.3 (2026-10-19)

- **t3-relay: confirmed delivery + failover hosts.** `launch`/`send --wait SECS` and `status <rid>` report `ok <threadId>` / `failed` / `pending` from the effect (thread with that title launched, or message `relay-<rid>` landed), not the host's reply wording; failed only once the host turn ended without it, so retries cannot duplicate. Several relay hosts (one task + bound host thread per provider, e.g. Claude Haiku + Codex Luna, effort low): a request goes to the first host that is not stuck, not recently failed and whose account passes the capacity check. `--via INSTANCE` probes one host; `check` lists every host.
- t3-schedule: a job counts as fired only when t3-relay confirms it (`.last`); unconfirmed → `.pending`, re-checked by the catch-up tick, never blindly re-fired. Previously a relay that accepted and then failed marked the job done and catch-up never retried. Runners change: `skills-refresh` runs `t3-schedule refresh`.
  **Upgrade (once per machine):** add a host per provider and drop the old single host: [relay.md#heal](skills/t3-manage-thread/relay.md#heal-relay-created-before-2026-10-19).

## v0.5.2 (2026-10-19)

- **t3-relay: bind the relay to a host thread.** T3 gives an unbound webhook task a fresh git worktree from `origin/main` per run, so every relay request fetched and left a worktree (PJ: 55 in 3 days), and a fetch timeout or `git config` lock race silently dropped the request after the script got 202 (a missed `skills-refresh` and a missed launch). The relay now runs as queued turns in one `⚙️ T3 relay` host thread at the repo root. `t3-relay check` / `install --check` fail on an unbound relay or a deleted host; `launch`/`send` warn. **Heal once per machine** if you set up the relay before this release: [relay.md#heal](skills/t3-manage-thread/relay.md#heal-relay-created-before-2026-10-19).
- agents-md: distinguish local file deliverables (absolute paths) from live product/ticket links; reserve remote file URLs for versions unavailable in a stable local checkout.

## v0.5.1 (2026-10-18)

- t3-maintenance / t3-find-thread: purged threads stay findable. `t3-purge-threads apply` first copies its cohort into one searchable SQLite archive (`~/.t3/backups/t3-archive.sqlite`, FTS5, mode 600; refuses to purge if any thread misses it), replacing the slim backup. Kept: metadata, lineage, every message whole, tool calls with output head/tail, diffs, sub-agent results, questions/answers, errors; dropped: event log, intermediate tool states, progress noise, images. PJ's whole 6.6 GB store → 445 MB. `t3-find-thread search` adds the archive when no live hit has every term or `--since`/`--until` predate the live store (`--backup on|off`); hits are flagged `_(backup)_`, and the new `read` shows a purged thread in full. New `t3-thread-archive` (`sync`, `stats`, `import` of old `purged-threads-*.sqlite`, done automatically by the next purge). Upgrade: rerun `t3-maintenance/scripts/install`.

- Browser: T3 `preview_*` with explicit `profileId` is the default for signed-in work; the user's Chrome over CDP becomes last resort with their OK (Chrome ≥ 144 shows a focus-stealing consent modal per connection). Sign-in recipe for v0.1.0 (cookie import, focused-tab paste, no passkey sheet) in [browser.md](skills/t3-manage-thread/browser.md); template rule updated.
- bitwarden: `bw-once --vault NAME` (several accounts via `~/.config/bw-once/vaults.json`, per-vault data dir/socket/lock, wrong-account guard), `session start --reason`, `bw-once login` in the human Terminal, pre-flight before opening a Terminal, `doctor` reports `touch_id_flag` (CLI 2026.10.0 Touch ID unlock is gated by Bitwarden's `biometrics-sdk-ipc` server flag).
- t3-relay / t3-schedule: standalone threads run on a frontier model. `t3-relay launch` without `--model` now picks opus, else sol (it used to inherit the relay thread's Haiku, not the project default). haiku/luna are refused unless `--allow-small-model` (`allow_small_model` in job specs; grandfathered for existing `skills-refresh` jobs). Rule for agents calling `t3_thread_launch`: [SKILL.md](skills/t3-manage-thread/SKILL.md#model-tier).

## v0.5.0 (2026-10-16)

- **T3 Code ≥ 0.1.0 (Orchestrator V2) only.** Agents use T3's MCP tools: 🏓 worker = `delegate_task` (no sidebar row, its result wakes the parent), standalone = `t3_thread_launch`, plus `t3_thread_send/read/organize` ([workers.md](skills/t3-manage-thread/workers.md)). New `t3-pick-instance MODEL` → `<instanceId> <modelId> <effort>` (capacity routing, model floor). New `t3-relay launch|send` lets scripts outside T3 start or message threads through one native webhook task ([relay.md](skills/t3-manage-thread/relay.md)); t3-schedule, recording-watcher, t3-mail-link, t3-git-leftovers and usage-window warm-ups use it. Readers (t3-fleet, t3-find-thread, t3-purge-threads, t3-my-prompts, t3-preview-gc, t3-drafts) read `statev2.sqlite`. Deleted: t3-spawn/ping/read/settle/delete/hide/rename-thread, t3-thread-maintenance, `t3-usage-windows limited` (T3 auto-resumes), T3 Open.app, all snoozing.
  **Upgrade (once per machine):** update the T3 app to ≥ 0.1.0 first (`skills-refresh` refuses this release on 0.0.x). If you use t3-schedule, recording-watcher or t3-mail-link, ask any T3 agent: "create the T3 relay per t3-manage-thread relay.md", then check with `t3-relay check`. `skills-refresh` reinstalls, drops the dead helper links and runs `t3-schedule refresh`.

- agents-md / t3-manage-thread: independent planning opinions start from the same brief without the other planner's proposal; compare afterward. Astra plans; Sol reviews Claude-built code.

- agents-md / t3-manage-thread: Opus defaults to planning, orchestration, implementation and Claude-side review; reserve Fable for very complex planning.

- t3-maintenance: `t3-git-leftovers` finds uncommitted/unpushed work in recently active repos (T3 threads + recent commits), protects paths edited < 30 min ago, spawns one hidden self-settling worker per repo (capped, resumable ledger, never duplicates), and re-checks git for landed/protected/blocked counts. Worker playbook: [git-leftovers.md](skills/t3-maintenance/git-leftovers.md).
- video-shrink-for-gemini: screen-share detection samples every 15 seconds by default; evidence thresholds scale with cadence and range padding covers transitions between samples.
- recording-watcher (new): config-driven poller for Fathom, Leexi and Monologue, every 5 min in work hours (launchd on macOS, systemd user timer on Linux/WSL), with deterministic owner election so one teammate machine processes each call; `seed` starts a new machine without backfill. [setup](skills/recording-watcher/setup.md).
- recording-followups: shared spoken cue "James" with spawn/ticket commands. [spoken-cues.md](skills/recording-followups/spoken-cues.md).
- agents-md: chat file paths are always absolute (repo-relative badges broke when the file lived in another repo); a file only on a remote branch gets its web URL.
- agents-md: try the account-correct Chrome/CDP session when T3 is unavailable or lacks the needed login; inspect existing signed-in tabs before asking for authentication help.

## v0.4.9 (2026-10-15)

- clickup-core: urllib3 2.8.0 fixes GHSA-8988-9cw3-xx77, GHSA-vxq7-64xx-v4gw and GHSA-gh4c-6fx4-qh6g; root test lock updated too. Source fix prevents consumer refreshes from restoring 2.7.0.
- Dependencies: weekly Dependabot PRs for Python (including transitive pins) and GitHub Actions; CI validates locks, the skill suite and ClickUp's shipped environment. No automatic merges.

- clickup-core: description readback compares the Quill normal form, so ClickUp's own autolinks on bare URLs and merged code-block newlines no longer report a false `content readback differs`; a real link rewrite still fails.

- whatsapp-bridge: `scripts/install` / `scripts/build-neonize` also build the pinned Neonize on Linux x86_64/arm64 (incl. WSL2 Ubuntu; needs `build-essential libmagic1`), verified in Ubuntu 24.04 containers up to a live login QR. `--window` stays macOS-only; on Linux run `wa login` in a terminal the human sees.

- t3-manage-thread: `t3-ping-thread --model/--thinking [--no-turn]` resumes an existing thread on another model/effort of its own provider account (Fable → Opus, Astra → Sol), history intact; persisted via native `thread.meta.update` so later plain pings keep it (a raw `turn.start` modelSelection is per-turn only). Other provider/account refused. Docs: reuse threads with relevant context (planner → reviewer, re-review), new thread when unrelated. Model aliases/floor/house effort shared with spawn in `lib/t3-common.sh`.

- agents-md / t3-manage-thread: default model split — plan in a thinker (Astra as 🏓 second planner on consequential designs), build with Opus sub-agents, verify/review with a Sol 🏓 worker (Codex-built → Fable); `code-review.md` spawns `--model sol`. Global template: copy chat file paths verbatim from tool output, never retype them.

- bitwarden: `bw-once session start --ttl 60m [--host …]` — PJ unlocks once in Terminal, a holder keeps the key in memory, serves exact-host `list`/`copy` over a private socket (same commands, automatic fallback to per-request unlock), logs each request and runs `bw lock` at expiry/stop; design + paste mechanics in `session.md`.

## v0.4.8 (2026-10-13)

- agents-md: global template uses progressive disclosure — browser routing, T3 thread mechanics and handoff checklist move to pointer files inside installed skills (new `t3-manage-thread/browser.md`); `scripts/check-pointers <prompt>` flags missing files and unfilled placeholders, run at merge, re-sync and in t3-setup verification (install the owning skill or drop the line).

- t3-manage-thread: plan tier (`20x`, `5x map`, `1x?`) shown in `t3-limits` (all formats; `multiplier`/`multiplier_source` in JSON), `t3-list-profiles` (cached, no network) and routing output. Labels without a stated multiplier (Codex `pro`/`prolite`) take it from an optional private `$T3CODE_HOME/userdata/t3-plan-multipliers.json` (driver → plan → N); unmapped stays 1x, never optimistic. Fix: inside a homePath instance's thread, the default Claude instance no longer inherits that thread's `CLAUDE_CONFIG_DIR` (it mirrored the caller's usage).

- agents-md: global template — pre-task feedback-loop check (build minimal self-verification tooling first, little human QA) and post-task improvement loop for recurring work; `global.md` budget raised to ~6k tokens (~24 KB).

- google-workspace-core: `--attach PATH` (repeatable) on `gmail-draft`, `gmail-send` and `gmail-draft-update` builds `multipart/mixed` (text first, one attachment part per file); refuses missing files, symlinks and >20 MB total; `files=<n>` is the read-back attachment count.

- clickup-core: body-free lookup summaries, repeated keyword OR matching, title-only first pass, strict ISO recency filters, and tasks added from other lists. Before-create guidance checks recent closed plus older open work; project wrappers define relevant read scopes.

- t3-manage-thread: `t3-spawn-thread --profile a,b` routes by capacity among only the named accounts; a single explicit `--profile` is capacity-checked and refuses an exhausted relevant window (incl. "Fable only") with the best alternative and a rerun command. `--force-profile` overrides; unknown usage only warns.

- agents-md: global template — several named profiles → `--profile a,b`; explicit profiles are capacity-checked.

- t3-route / agents-md: align standalone self-settlement with authorized routing policy; keep-open review requires a concrete pending user decision, not merely completed agent review or a readable result. Template links private settling-policy notes for iteration.

## v0.4.7 (2026-10-10)

- t3-manage-thread: Claude plan discovery reads live OAuth profile metadata, cached with usage for 90 s, so subscription upgrades/downgrades override stale login tiers. Failed discovery preserves valid usage with a marked login fallback; cache identity survives token rotation when local account ids exist. No credential changes or quota overrides.
  Spawn-selection fixtures now use the current model floor and explicitly verify rejection of older Sol models.

- agents-md global template: browser routing by job (T3 preview / CLI over CDP / computer use), from measured Gmail tests.

- t3-route: optional preferred model per task type, with a wrapper tier map and reported cross-provider fallback when the preferred provider is exhausted.

- agents-md: git rule — pull is a merge, rebase only your own unpushed commits, never rewrite pushed history or force-push the shared branch; plus the recovery recipe when a local branch has swallowed foreign history (`git cherry` to prove your commits landed, `git reset --keep origin/<branch>`).

## v0.4.6 (2026-10-08)

- t3-manage-thread: automatic profile routing is plan-aware. The headroom-per-hour score is multiplied by the multiplier the login label states (`max_20x` → 20, `max_5x` → 5, no multiplier → 1), and session tightness is measured in the same plan units relative to the largest verified plan (a 5x beside a 20x is tight from 60 % used; a 1x beside a 20x is overflow only). Unlabelled providers (Codex `pro`/`prolite`) keep the unweighted ranking; exclusion, unknown/stale handling, model-only caps and explicit `--profile` are unchanged. Routing output shows `%/h × Nx = score`.

- agents-md: verify rule now front-loads the proof: before non-trivial work the agent designs how it will verify end to end without the human (seed data, demo UI, device, scheduled check), builds that tooling first, flags only when it is a chunk of work, and treats "can you check…" as a defect.

## v0.4.5 (2026-10-08)

- video-shrink-for-gemini: `download-loom` fetches a public Loom share's video, metadata and Loom's own timestamped transcript without login (share-page Apollo cache, GraphQL fallback); `loom.md` documents the merge with Gemini. recording-followups lists Loom as a speech layer.

- t3-route: decide conditional self-settlement per standalone dispatch; verified durable delivery, existing authorization and no user review required. Eligible tasks stay visible while running; helper footer preserves keep-open instructions and surfaces material findings.

- agents-md: concise Markdown reports use progressive disclosure, callouts and Mermaid; conclusions stay visible.

- agents-md: simplify colleague handoffs to pre-merged prompts and short installation steps; retain inline repo maps, keep setup mechanics outside the global prompt, and scale optional PR/review flow to regression risk.

- agents-md: one role-neutral core with product-owner Git assistance, repository-aware integration and release authority; global-prompt migration inventories all homes/overrides, preserves backups and verifies fresh instruction loading.

## v0.4.4 (2026-10-07)
- t3-route (new): instruction-only intake, verified thread reuse and dispatch through a private wrapper; account/scope-aware onboarding and bounded corrections, with source evidence separate from inferred intent.
- t3-mail-link: `resolve` reads the selected account and Gmail thread ID without linking, spawning, writing mail-link state or scheduling; ambiguous references remain unresolved.
- bitwarden (pilot): `bw-once` opens human Terminal for fresh native authentication, performs one bounded lookup/copy/Send, then locks before delivery; no agent vault session, clipboard expiry preserves newer contents. Current released CLI requires a master password; live-vault UX remains unverified.
- yuki-core (new): Yuki "Aan te leveren aankoopfacturen" for one quarter (`yuki.py outstanding|sheet-push|discover`): read-only zeep client behind a method allowlist, carryover flag for older open items, Belgian-format FX parsing, fails closed on malformed data; `sheet-push` creates the `<YYYY>-Q<n>` tab, appends only unseen Yuki item ids, seeds manual cells once from the previous quarter tab and verifies on read-back. Company ids, sheet and Google account live in the wrapper's `yuki.json`.
- t3-setup / agents-md: offer browser cookie import, verify selected profiles in installed harnesses, and save only purpose/profile/account routing in the user's global prompt; retain browser fallbacks and keep setup details private.
- agents-md: global template tells agents to use T3 inline visual replies (`html_preview`/`html_render`, T3 ≥0.0.46) for charts/tables/mockups instead of prose or loose HTML files.
- agents-md: prefer native T3 browser tools in both Claude and Codex; retain tab IDs and verify account identity, with profile-selection details kept outside the global prompt.
- clickup-core: `[[file:NAME]]` links an attachment of the target task in comments, handoffs, reviews and descriptions (fails closed before writing on unknown/ambiguous names; newest version wins); bare attachment filenames are auto-linked instead of becoming ClickUp's dead domain links; `attach` prints `reference: [[file:<title>]]`.
- clickup-core: `chat read` / `chat post` for channels, DMs and threads; `--image` posts real inline images through the web app's session (`chat session` reads the one-year refresh cookie from a Chrome profile; the public API stores chat images as `src="http://null/"`).
- data-enrichment: durable URL/PDF capture to Markdown via free Jina, then one pinned treg/Olostep fallback; preserve raw evidence, links and billing receipts. Free capture needs no token.
- t3-schedule: persistent systemd user timers on Linux/WSL for recurring jobs and one-time continuations, sharing the existing retry/catch-up and duplicate guards; macOS keeps launchd. Installer checks verify scheduler readiness.
- t3-manage-thread: harden platform credential loading and background-worker readiness; use the native scheduler for Linux skills-refresh jobs.

## v0.4.3 (2026-10-02)
- t3-limits: reads Claude's `/login` credential from `<home>/.credentials.json` on Linux/WSL (and as macOS Keychain fallback) instead of crashing on a missing `security` binary; a profile that only holds a `claude setup-token` gets a "setup-token only" row (the usage API answers 403 to those tokens).
- skills-refresh: `schedule` on Linux/WSL warns when no cron daemon runs (with the WSL `[boot] systemd=true` persistence hint) and prints the zone the hour is read in; `--version` reports the release stamp for a managed copy inside a setup repo (was: that repo's commit).
- t3-find-thread: `t3-open-thread` refuses on Linux/WSL with a sidebar hint (`--browser` still works); docs mark it macOS-only.
- t3-setup: `skills add` lines pass `-a claude-code` (+ `-a codex`) so the CLI never prompts for agents in a non-TTY shell; verify the Codex login inside WSL (`codex login status`), not the Windows desktop app; WSL limitations listed in one place.
- t3-purge-threads: never purges a thread with a pending wake-up (`t3-schedule pending-resumes` continuation, `t3-mail-link list --thread-ids` link); `list` reports them as kept (`kept_pending_wake` in `--json`), a failing helper aborts.
- data-enrichment (new): one `TREG_TOKEN` for the treg.to catalog (~3,800 endpoints: email find/verify, person and company enrichment, scraping blocked pages, social, SERP/keywords, reviews, generation). `treg.py search|get` are free and print one line per endpoint (price, observed success); `call` caps routed spend at $0.05 and reports the real charge; `balance`. SKILL.md gives inspiration, money/verification rules and pointers into treg's own docs instead of a list.
- text-to-speech (new): provider-neutral voice discovery, single-clip generation with key-free provenance, optional normalization, and offline comparison; ElevenLabs/Gemini controls, accent guidance, and a catalog-to-Voice-Design workflow for specific voices.
- perplexity-core (new): `px.py ask` = one sourced research question over the Perplexity Agent API (web_search always on, optional people_search), markdown + retrieved-source list or `--schema` structured JSON with nullable fields and verified `*url` keys; `check` spends nothing. Extracted from brellascraper's enrichment service. Empty answers exit 3 after one retry; 429s back off.
- t3-setup: "Fresh machine" section for a Mac with nothing installed (Homebrew via one Terminal line the user pastes, then gh/jq/mise, Claude Code CLI, T3 Code cask, GitHub login) and a non-developer rule; startable from Claude Desktop's Code tab.
- recording-followups (new): after a Fathom/Leexi/SyncUp transcript, a debrief note plus self-contained T3 prompts, one temp file per prompt spawned by path (`t3-spawn-thread … < file`); light code research before proposing; thinker vs coding-model routing. Linked from video-shrink-for-gemini, leexi, clickup-core.
- agents-md: global template gains self-armed follow-ups: when the next step needs time to pass, the agent schedules `t3-schedule add --once <date> --resume-thread self` and reports a new ⏰ status. `t3-schedule` accepts `--resume-thread self` (the calling thread).
- t3-schedule: `pause <name> [--until YYYY-MM-DD]` and `resume <name>` keep recurring repo jobs registered while runners and catch-up skip them; an until date resumes at local midnight. `list`/`show` display effective status.
- t3-schedule: repo specs record `machines` (`one` default · `many` via `add --many-machines`) and `adopted_by` (label, git user.name, since, random id; `t3-schedule machine --label`). Adopting a one-machine job registered elsewhere asks for confirmation at a terminal and needs `--takeover` unattended (`--force` never implies it, also on `add`/`migrate --force`); repo-wide adopt checks every job before writing. A one-machine job no longer listing this machine skips at fire time (before the T3 wait and right before the spawn) and in catch-up; `list` shows who runs what. Intent from the local checkout, not a lock: the old machine stops once it pulls. Run `t3-schedule refresh` so existing runners get the check, then `adopt` each job once to record the machine.
- agents-md: global template gains four rules from PJ's first prompt retro: 80/20 cut first + opposite-model opinion on consequential design, web-verified external facts, Downloads + short thread titles, read the colleague's machine notes before writing instructions for their agent.
- clickup-core: `triage.md` escalations open with a gradable `Needs developer because:` reason (env gap · authority · cross-boundary · unresolved doubt · incident); a bare escalation goes back to the PO's agent.
- agents-md: global template gains the in-worktree session commit rule, minimal global skill registration, and same-session refresh of committed shared-skill copies.
- agents-md: global template env rule tightened: values only in `~/.config/mise-env/<org>/<repo>.env` (chmod 600), never a repo `.env` or `source .env`.
- t3-usage-windows: `topup` is the single automatic flow: runs daily 05:00–21:00 (was Mon–Fri) and gives accounts without a session window (Codex, weekly only) one `start` per local day on the first tick from 05:00 (state beside the log). `start` covers named Codex instances. The short-lived `warmup install` / `usage-window-warmup` job is gone: `t3-schedule remove usage-window-warmup`, `git rm` its two `.agents/schedules/` files, rerun `t3-usage-windows topup install`. Warm-up child threads are titled `Warm-up — <profile> <model>`.
- t3-schedule: recurring job definitions are versioned in the project repo (`.agents/schedules/<name>.json` + `.prompt.md`; no path, no profile); the runtime dir keeps a machine-local pointer + artefacts. `adopt <repo|spec>` opts a machine in (never on clone), `migrate` moves pre-versioning jobs, `list` flags untracked/uncommitted/missing specs and stale runners. `--once`/`--resume-thread` stay local.
- google-workspace-core: `gmail-draft-update <draft-id> (--body TEXT | --body-file PATH|-) [--html-file PATH] [--expect-message ID]` edits a draft body in place, never sends. Draft id, threadId, headers and every other MIME part stay byte-identical (no header refolding, original line endings, body Content-ID/Disposition kept); the candidate is checked before the PUT, so unsupported shapes are refused without writing, and verified again on read-back.
- video-shrink-for-gemini: `shrink-video --max-bytes 48M` splits output over the limit into overlapping `<name>.gemini.partNN.mp4` + `<name>.chunks.md` (absolute start/end per part); re-encodes once with 30 s keyframes, then stream-copies.
- resource-audit: read-only `resource_snapshot.sh` (CPU via top's second sample, memory pressure, paging, process swarms; printed suggestions only) + `scripts/install`.
- t3-manage-thread: `skills-refresh --version` reports "source checkout" only for this repo's own checkout (a managed copy inside a setup repo now shows its tag); `t3-spawn-thread` house effort by model family; `t3-rename-thread --help` corrected.
- claude-cloud: `--help` documents defaults, env fallbacks and exit codes. t3-maintenance: t3-drafts tests hermetic.
- t3-schedule: `add --resume-thread ID` schedules a continuation: at fire time the job pings that thread with the prompt; if it is deleted/archived/unreadable, its profile is gone or the ping fails, it spawns a fallback thread with the prompt + a bounded context pack. `t3-read-thread` exposes `deleted_at`.
- t3-manage-thread: a requested "separate/standalone thread" is spawned visible (`--no-hide` or 📤); 🏓 alone hides it while running.
- t3-manage-thread: `t3-mail-link` links a T3 thread to a Gmail thread (URL, hex id or `--search`; `FMfcg` web ids via the Chrome tab title). A weekday LaunchAgent poller pings the thread on new inbound mail (own/sent mail marks seen, no wake); the woken agent drafts, asks or settles per [mail-link.md](skills/t3-manage-thread/mail-link.md). Account via a google-workspace-core wrapper config.

## v0.4.2 (2026-09-26)
- t3-manage-thread: show account plan labels in limits JSON/Markdown and spawn routing explanations; clarify account-relative percentages and large-job capacity checks without changing routing. Sync the t3-drafts test fixture with the session/activity tables read by limit detection.

## v0.4.1 (2026-09-26)
- Docs-only skill audit across every skill and `setup/t3-setup` (~−700 lines): docs keep trigger, map, intent and gotchas; usage that `--help` prints moved to pointers. File names and `##` anchors that consumer wrappers link to are unchanged, except whatsapp-bridge (`## Map`, `## Safety (hard rules)`, `## History limits`) and removed `setup/t3-setup/codexbar.md` (→ `codexbar-setup/install.md`).
- Stale claims fixed: account routing covers Claude and Codex; an explicit `--model` gets its house effort; `--self` settles via `t3_supervise`; `transcribe-openai --hint` is ≤20 terms, and the prompt expects `--out transcript.openai.md`; `keychain_service()` lives in `lib/t3_limits.py`; t3-schedule `--once` for one-time routines; clickup appends are verified by `content_signature`; google-workspace sends `supportsAllDrives` on every Drive call and has no draft-update command.
- Public hygiene: customer, colleague and personal example names neutralized in docs, a `transcribe-openai` docstring and a `clickup.py` comment.

## v0.4.0 (2026-09-25)
- t3-manage-thread: `skills-refresh` — release-gated updater for globally installed copies of this repo's skills: applies only new `vX.Y.Z` tags (never `main` HEAD), stages a clone at the tag, `bash -n` pre-check, swaps the skill directories with a last-good rollback, reruns each updated skill's `scripts/install`, writes `~/.agents/pjmuller-skills.version` and prints the CHANGELOG entries between the two tags (exit 0 current · 10 applied · 1 failed). `skills-refresh schedule` registers the daily 06:30 job: macOS via `t3-schedule add --hide --no-notify` on `haiku,luna`, prompt = `skills-refresh --job`, which itself settles the thread (nothing new) or surfaces it once with the changelog (applied) or the error; `--quiet` settles on applied too. Linux/WSL via cron. Symlinked source checkouts are left alone. No `skills update`/`skills check` involved.
- t3-manage-thread: `t3-spawn-thread --version` / `skills-refresh --version` print the installed release tag from the stamp (or `source checkout <git describe>`); `scripts/install --check` shows it. `--model luna` alias (`gpt-6-luna`).
- t3-schedule: `add --hide` (snooze keeper without the self-settle footer) and `add --no-notify` (no launch notification); `refresh` skips jobs whose runner is active instead of killing a spawn in flight.
- t3-schedule: `--model` accepts an ordered comma list (`opus,sol`): at fire time the runner probes each candidate with `t3-spawn-thread --dry-run` and spawns the first whose ecosystem is installed and has capacity; no `--model` ≡ `opus,sol`. Profile keeps following the spawn helper's capacity routing (unknown-capacity accounts only when nothing is verified).
- t3-setup / README: the standard T3 setup is `t3-manage-thread` + `t3-schedule`, both global, plus the `skills-refresh` job; `docs/onboarding/skills-refresh.md` is the paste-to-colleague upgrade note.

## v0.3.4 (2026-09-25)
- video-shrink-for-gemini: mandatory vocabulary grounding before any Gemini/OpenAI transcription (people, products, taxonomies/enums from the project's docs → `## Vocabulary` block and `--hint`); `transcribe-openai` without `OPENAI_API_KEY` prints skipped and exits 0 (enrichment, not a blocker). Annotation prompt carries the same vocabulary field.

## v0.3.3 (2026-09-25)
- video-shrink-for-gemini: `transcribe-openai` — second-opinion speech layer through OpenAI's transcription API (`gpt-transcribe` + vocabulary hint), aligned to the vendor transcript's speakers/timestamps or in chunks (`--diarize` optional); measured on Flemish meeting audio. video-frames-for-vision's annotation prompt reads it next to the vendor transcript.

## v0.3.2 (2026-09-25)
- video-frames-for-vision: defaults favour few but relevant frames (`--max-frames 60`, one view per page, 20 s coverage); over-budget demotion drops near-duplicate pages before short novel ones.
- agents-md / clickup-core: handoff to a non-technical reader who works through a coding agent = one copy-pasteable md block addressed to the agent.

## v0.3.1 (2026-09-25)
- video-frames-for-vision / leexi: Codex recipe targets Linux/WSL/macOS (apt/brew, `uv run --script` with POSIX paths); the PowerShell/winget instructions were wrong for a WSL-backed setup. Benchmark note: one Claude Code agent hits a media request limit after ~54 frames.

## v0.3.0 (2026-09-25)
- leexi: new skill (infrastructure layer split out of video-shrink-for-gemini). `download-leexi` gains `--at "today 14:00"` (nearest call in a time window, `--pick` on ambiguity) and a default git-ignored `./.local/leexi/<uuid>/` out dir; `leexi-calls` lists recent calls; shared stdlib client `leexi_api.py`; Windows-safe `uv run --script` invocation; unit tests.
- video-frames-for-vision: new skill for vision-only models (Codex, Claude Code) without Gemini. `select-frames` samples a recording at 1 fps, classifies people-only frames (skin/edge/content-region heuristics), groups screen frames into views (pHash + SSIM) and pages (same chrome + header band, scroll tolerant), keeps one frame per page plus extra scroll positions, crops the shared-content region at 2×, writes `manifest.md/json`, contact sheets and audit sheets (people-only sentinels, transients). Annotation prompt reproduces the meeting-analysis shape (screen events, topics, action items, ready-to-paste prompts); Codex recipe for Windows.
- video-shrink-for-gemini: **breaking** — `download-leexi` and `leexi.md` moved to the `leexi` skill; `scene-frames` removed in favour of `select-frames`. Docs delegate: Leexi input → `leexi`, no Gemini → `video-frames-for-vision`. Rerun `scripts/install` for both skills.
- clickup-core: `scripts/syncup.py` downloads a SyncUp's recording, AI notes and untimed notetaker transcript from a chat message, chat channel (`--list`) or notes Doc URL; token-only (no clickup.toml), private git-ignored output, exit 75 while ClickUp is still processing.
- t3-schedule: once-jobs retry a missed/failed slot until 23:00 that day (recurring jobs keep slot+10h: they have tomorrow).
- t3-spawn-thread: `--settle-when-done` footer is conditional — the worker self-settles only on a clean outcome (nothing new the user needs); otherwise it unhides itself (`t3-hide-thread --unhide <own id>`) and ends with a terse report.
- t3-schedule: `add --once YYYY-MM-DD` one-shot jobs with the recurring guarantees (catch-up until slot+10h, one spawn). Runner guards launchd's yearly re-fire; the catch-up poller retires fired/expired once-jobs (`list` shows the outcome, expiry notifies); `run-now` forces the date; past date/time rejected; `--weekdays`/`--days`/`--once` mutually exclusive.
- whatsapp-bridge: new skill. Local Python WhatsApp helper (pinned Neonize 0.4.7 built from source, `NEONIZE_BOT_TAG=off`, no browser/daemon): QR pairing via a real Terminal window, synced-history reads, contact lookup/bounded reply context, allowlisted individual sends with 5 s cross-process pacing. Mechanics live in the core; a repo-local wrapper skill owns the account, own number, allowed recipients and drafting policy.
- t3-limits: Codex usage is read per T3 instance from `<home>/auth.json` + `chatgpt.com/backend-api/wham/usage` (no CodexBar dependency): every Codex account gets its own row, attributed to the instance T3 would run, with the login e-mail on the plan line. Cache entries are bound to home path + account id; an exhausted window outlives the 15 min stale cutoff until its reset; missing percentages are unknown (`?`/`null`), never 0.
- t3-spawn-thread: one capacity policy for Claude and Codex — a driver switch (`--model astra` from a Claude thread) is routed by capacity too, the sibling account only breaks ties; no sibling no longer blocks routing. Every automatic route prints a decision block (candidates, windows, room, unknown/stale/excluded state, chosen account, override hint), also on refusal and under `--dry-run`. A single profile is polled too (an exhausted one refuses instead of spawning a blocked thread).
- t3-schedule: `pick-profile`, `picks.log` and the recent-pick penalty are gone; the runner omits `--profile` and inherits the spawn routing. All-exhausted spawns fail and are retried by the catch-up poller.
- Scope: default to repo-local registration; distinguish personal setup, project and skill source repositories. Only `t3-manage-thread` is recommended globally. Prompt/voice maintenance stays in the personal setup repository; migration and cloud-session skills belong in consuming projects.
- tone-of-voice: new skill. Interview-driven capture of how a person writes from their real samples (pasted, sent mail via google-workspace-core, Docs, posts), ping-pong confirmation, `tone-of-voice.md` with a starter template and anti-AI-slop checklist, wired into the global prompt.
- agents-md: `handoff.md` (relay prompt for a colleague/harness, dev → non-technical, non-technical → dev with intent first and symptoms over conclusions); template synced (delegation heading, sub-agent model lists, handoff pointer). clickup-core links to it for reporter → developer handoffs; wrapper template no longer carries a link that only resolves after copying.
- t3-manage-thread: `t3-list-profiles` lists enabled accounts per ecosystem (Claude / OpenAI / Google) with the exact `--profile` value; spawn examples drop `--profile`/`--thinking` (account and effort follow the parent). `code-review.md` absorbs the model pairing and hand-off-plugin rule; agents-md `global-template.md` delegation block simplified to match.
- t3-spawn-thread: `--profile` is an account label orthogonal to `--model` (`probackup` + `astra` → Codex ProBackup, + `fable` → Claude ProBackup); a driver switch without `--profile` picks the inherited account's sibling instance instead of failing. Docs/examples drop `--profile codex`.
- t3-manage-thread: `code-review.md` — opposite-model review as a 🏓 worker (when, spawn commands both directions, brief shape, reviewer output, builder push-back); `SKILL.md` slimmed to a commands-first entrypoint with cross-provider spawn examples.
- google-workspace-core: `gmail-export` writes a query's messages (or `--by-thread` conversations) as compact Markdown files plus `index.md` for local grep; `gmail-search` paginates and fetches metadata concurrently; `references/gmail-search.md` holds the search → export → grep → clean-up loop and Gmail query cheat sheet. Body text: strict UTF-8 before a declared Windows-1252, wrapped `On … wrote:` attributions trimmed, mailer tracking links dropped.
- agents-md: `global.md` + `global-template.md` for the user-level cross-project prompt (what belongs where, pruning by experiment, merging the template into an existing file, re-sync marker); t3-setup merges this template instead of external bases.
- t3-manage-thread: `dispatch-workers.md` — project-agnostic rules for spawning worker threads (short 🏓/📤 titles, thinker model, brief shapes, bookkeeping).
- google-workspace-core: one `gws.py --config workspace.json` CLI and importable `gws_core`; replaces REST/read-only/modular facades. Includes account-bound OAuth, secret-safe diagnostics, draft CRUD, Slides tooling and offline parity tests.
- ClickUp missing-token errors now identify checked paths safely.
- video-shrink-for-gemini: `download-leexi` fetches a Leexi call's transcript, summary, follow-up tasks and presigned recording through the public API (Basic auth, scoped keys, 403 on Python's default User-Agent); `leexi.md` condenses the API reference.
- slides: default to committed repo-local installs, so colleagues/cloud agents need no global skill.
- slides: reusable presentation craft, concise speaker notes, visual verification and curated MIT-attributed Slidev guidance; thin project wrappers retain local brand and delivery context.
- t3-spawn-thread: discover accounts across native provider drivers; model-aware name matching, ambiguity rejection, and preserved Codex account/effort inheritance.
- migration-parity: concise autonomous migration guidance with independent baselines, data/effect comparisons and end-to-end user workflows.
- t3-hide-thread: preserve fractional timestamps so same-second turn completion is re-snoozed; regression coverage for queued pings and attention requests.
- t3-usage-windows: list banked Codex resets as Markdown/JSON or consume the earliest expiry through the native app-server protocol.
- video-shrink-for-gemini: explicit `download-fathom --transcript-only` exports raw API JSON and speaker/timestamp Markdown without video or ASR.
- claude-cloud: disclosed profile/environment/repository defaults, create --wait/--title, official-CLI token refresh, paginated session review and redacted idempotent export.
- Command installers guard against switching checkouts accidentally; `--relink` opts in, project copies warn, and `--check` identifies the source.
- claude-cloud: headless Claude Code cloud sessions (envs, create, send, wait, read, archive) with T3-profile substring resolution through t3-manage-thread's Keychain mapping; undocumented-API experiment.
- video-shrink-for-gemini: measured local route for when Gemini is unavailable — `transcribe-local` (mlx-whisper ASR) and `scene-frames` (scene-sampled original-resolution frames with a visual-token estimate), plus subscription modality limits and per-model ID-reading fidelity.
- video-shrink-for-gemini: bounded native drafts, candidate provenance and targeted original-frame verification for opaque identifiers.
- t3-read-thread: expose parsed thread model selection in JSON for post-spawn route attestation.
- agents-md: concise guidance for creating and simplifying canonical agent entrypoints, grounded in intent, domain language, ownership and verification.
- t3-manage-thread: installer check recognizes T3 Code's `last-server-origin` fallback when the runtime descriptor is absent.
- **Breaking rename:** claude-cloud-feedback-loop merged into claude-cloud; dry-run and browser-fallback guides replace its entrypoint.
- video-shrink-for-gemini: browser-free Fathom API download and timing references; smaller readable 720p presets, measured 50 MiB fitting and minimal-chunk fallback.
- codexbar-setup: standalone macOS guide and Python helper for shared native profiles, bidirectional Claude credential sync and expiry alerts; linked from T3 setup.
- t3-manage-thread: clarify standalone/no-ping scope for parent tasks versus round-trip reviewers.
- t3-spawn-thread: model-aware Claude account routing from shared cached quota/pace data; explicit profiles win, known exhausted accounts are excluded, unknown capacity is reported.
- Antigravity: concise colleague setup; verified native CLI video-paste → Markdown transcript workflow.
- resource-audit: incorporate compressed-memory, worker-swarm, and stale-server investigation recipes from existing operator guardrails.
- resource-audit: separate macOS CPU/RAM diagnosis, process ownership, and recovery recipes; keep disk-audit focused on storage.
- Antigravity spawns: Gemini 3.8 Flash High default, model-encoded thinking; video skill delegates locally and requires verified Markdown output.
- t3-setup: `migrate-claude-routines.md` — Claude Desktop local routines → t3-schedule (registry + prompt locations, mapping, disable step).

## v0.2.1 — 2026-09-09

- clickup-core 0.2.1: pytest rootdir pinned to the skill (`[tool.pytest.ini_options]`) so a consumer
  repo's own pytest config no longer leaks into `pytest -q` inside the installed copy.
- t3-limits: cache usage reads per profile (90 s fresh window, `--fresh` to bypass) and fall back to
  the last good value on 429/network errors instead of reporting the account as unknown.
- t3-setup: default account's provider must carry no `CLAUDE_CONFIG_DIR` (the Keychain item is
  hashed from its value, so an explicit `$HOME/.claude` reads an entry that never existed).
- t3-setup: document the settings.json path for adding a Claude provider instance, reading the
  field shape from an existing instance instead of assuming it.
- t3-schedule: put pnpm's global bin (`$PNPM_HOME`, else `~/Library/pnpm`) on the launchd runner
  PATH, and have `scripts/install --check` resolve pnpm/uv/jq/sqlite3 under that PATH.
- t3-limits: print `<rateLimitTier> (<subscriptionType>)` when the tier does not match the plan.

## v0.2.0 — 2026-09-09

- Merge window warm-up and limit recovery into t3-usage-windows; unified CLI, system timezone, migrated top-up label.

### ClickUp core

- Add workspace-neutral clickup-core: discovery, tasks, rich comments, media, custom fields and configured handoff/review.
- Preserve native rich content on append; ship TOML templates, shared Loom downloads and offline contract tests.

## v0.1.0 — 2026-09-09

- Import eight skills, then replace personal examples with neutral fixtures.
- Add raw one-time T3 setup, MIT license and CLI distribution/update recipes.
- Check helper dependencies, resolve mise tools in launchd, migrate scheduler/top-up labels.
- Add visual-first and mixed recording prompts; make disk-audit scripts self-contained.
- Verify project CLI installation through a committed Claude directory symlink.
