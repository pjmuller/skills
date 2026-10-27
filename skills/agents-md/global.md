# The global (user-level) file

`~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`: the operating contract between one human and
every agent on their machine (reporting, autonomy, verification, delegation, tooling, repo map).
Loaded into every session of every repo, so every line is always paid for and competes with the
repo's own instructions.

Admission test per line: **true in every repo, and would removing it cause a
mistake or a detour?** Both yes → keep. Otherwise move it down or delete it.

Starting point or merge base: [global-template.md](global-template.md); adapt the
[role and Git workflow](roles.md).

## Mechanics worth knowing

- One canonical file in a versioned private setup repo; `~/.claude/CLAUDE.md`, each
  `CLAUDE_CONFIG_DIR/CLAUDE.md` and each `CODEX_HOME/AGENTS.md` symlink to it. Edit and commit
  the target.
- State that repo guidance wins over personal defaults, but remove contradictions rather than
  rely on that sentence. Codex reads each `CODEX_HOME`, preferring `AGENTS.override.md` over
  `AGENTS.md`; deeper project guidance wins
  ([discovery rules](https://learn.chatgpt.com/docs/agent-configuration/agents-md)).
- Codex caps the *whole chain* (`project_doc_max_bytes`, 32 KiB default) and truncates
  silently from the end: a fat global file cuts the repo's. Check what loaded: Claude
  `/context`; Codex: ask it to summarize its instructions.
- Adherence drops as instruction count grows, with a bias toward earlier lines.
  Budget: ≤ 6k tokens (~24 KB); behaviour-defining rules first, lookup facts last.
- Portable progressive disclosure = a pointer with a trigger: "doing X → read `/abs/path.md`
  first". `@import` and `~/.claude/rules/` are Claude-only and load eagerly (no saving).
  Absolute paths (cwd differs per session), into an installed skill
  (`~/.agents/skills/<skill>/…`, refreshed daily by `skills-refresh`; repo-local ones in the
  setup repo) or the user's setup repo, never a loose copy.
- Harness-specific block: name the harness in the heading ("Claude Code only; Codex: skip").

## What belongs where

| Content | Home |
| --- | --- |
| Reporting style, autonomy limits, verification bar, delegation routing (the one-line ownership rule: native child vs standalone thread; mechanics stay in the linked workflow skill), machine tooling monoculture, repo map, personal aliases | global file |
| Architecture, domain terms, build/test/deploy commands of one project | that repo's entrypoint ([SKILL.md](SKILL.md)) |
| Multi-step procedures, rarely needed know-how | a skill (loads on demand) |
| Machine facts needed only for some tasks: browser profile IDs, account maps, tool recipes | pointer file beside the global file |
| Must happen with zero exceptions | hook / permissions / CI; prose is advisory |
| Secrets | nowhere in prose |

## Writing lines that get followed

The [repo-entrypoint lenses](SKILL.md#choose-what-earns-space) apply (intent and reason over
capitals, an incident's reason in a clause, not the story). Global-specific:

- Emphasis works on one line; on ten it works on none.
- Keep an example where it saves hitting a wall (exact spawn command, speech-to-text aliases,
  status-emoji legend); drop examples of what a frontier model gets right unprompted.
- Thresholds and mechanisms are proxies; name the intent next to them.
- Volatile values (IDs, versions, verification dates) go stale silently → pointer file.
- Personal facts are fine in the private file, never in a shared template.

## Prune

1. Measure tokens (tiktoken `o200k_base` is close enough).
2. `git log -p` the file: what was added for which incident; does the cause still exist (old
   harness behaviour, abandoned workflow, weaker models)?
3. Classify every line: keep · tighten · pointer file · move to repo/skill ·
   enforce with a hook · delete (model does it anyway, duplicate, stale).
4. Uncertain deletions are experiments: remove, run a representative task headless
   (`claude -p`, `codex exec`), compare behaviour *and* tokens spent. A line that saves three
   failed attempts earns its place.
5. Large trim → another frontier model compares before/after for lost behaviour. Report cuts
   and why in a few lines; the diff is the record.

Signals between prunes: a rule is repeatedly ignored → file too long, or the rule
wants a hook. The agent asks what the file already says → wording is ambiguous.
The same correction given twice in chat → it is a missing line.

## Merge the template into someone's existing file

Their facts and preferences survive; the template adds behaviour they lack. For a colleague,
prepare the merged content here (their repo map inline); their agent saves, links and verifies
it, no second redesign. Setup/symlink steps stay in the installer, outside the prompt. Adapt the
[role](roles.md) without a second competing Git policy.

1. Read existing copies (Claude/Codex homes, symlink targets, global overrides). Back up
   contents and link destinations outside Git before replacing; check for missing personal
   rules. Leave project overrides alone.
2. Keep verbatim: identity, role, language, repos, accounts, tooling they actually use. Fill
   placeholders from evidence (`gh api user`, `ls ~/code/*`, `mise ls`, `brew list`); ask only
   what the machine cannot tell you.
   Browser routing: purpose → profile → verified account, preserving their fallback.
   Missing setup → offer [browser onboarding](https://github.com/pjmuller/skills/blob/main/setup/t3-setup/browser-profiles.md);
   keep import steps and volatile IDs outside the global prompt.
3. Same rule in both → the tighter wording. Conflict → theirs wins; list it.
4. Drop template sections for tools they lack (T3 threads, a second harness,
   deploy rights). Keep the template's model names; they are refreshed upstream.
   Review rules: with T3, resolve the full [review guide](../t3-manage-thread/code-review.md)
   from their installation; without T3, copy it minus its "In T3" section into
   their setup repo and link its absolute path. Never copy another person's machine path.
5. Apply Prune to the result. End the file with
   `<!-- template: pjmuller/skills@<short-sha> -->`.
6. Verify links resolve to the tracked source and fresh sessions load it. Every pointer must
   exist on this machine (`scripts/check-pointers <file>` lists misses): install the owning
   skill at its scope, else drop the line. Commit/push under the setup repo's rules; report
   source, commit/PR and unresolved differences or failed checks. Never change accounts or
   working tooling as part of prompt installation.

Re-sync later: the daily [skills-refresh](../t3-manage-thread/skills-refresh.md) job
detects a template change between the marker and the installed release tag (never
`main`) and hands this to a frontier child; by hand, the same with
`git log -p <marker>..<tag> -- skills/agents-md/global-template.md`. Three-way: their
wording, facts and deletions win; apply clear improvements, ask about unclear ones;
uncommitted prompt edits → change nothing, recommend. Log each skipped change in
`template-decisions.md` beside the prompt so it is never re-proposed; rerun the pointer
check of step 6; set the marker to the tag even when everything was skipped.

## Port a live file's improvements into a shared template

On request, walk `git log -p <last-ported>.. -- <live file>` hunk by hunk (plus `git diff` for uncommitted edits): a behaviour rule
any colleague would want → port, reworded neutrally; a personal fact (path, account, company,
ID, colleague name) → placeholder or skip; a removal → remove from the template too unless it
was personal. Record the new last-ported commit beside the live file, not in the public
template. Reread the template top to bottom: it must stand alone and hold nothing private.
Template edits are policy: PR plus a CHANGELOG why line ([AGENTS.md](../../AGENTS.md)).
