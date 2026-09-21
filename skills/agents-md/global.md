# The global (user-level) file

`~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`: the operating contract between one
human and every agent on their machine. How to report, how far to go alone, how
to verify, whom to delegate to, which tools this machine uses, where the repos
are. It is loaded into every session of every repo, so every line is paid for
always and competes with the repo's own instructions for attention.

Admission test per line: **true in every repo, and would removing it cause a
mistake or a detour?** Both yes → keep. Otherwise move it down or delete it.

Starting point or merge base: [global-template.md](global-template.md).

## Mechanics worth knowing

- Keep one canonical file in a versioned, private setup repo; symlink
  `~/.claude/CLAUDE.md`, every isolated `CLAUDE_CONFIG_DIR`, and
  `~/.codex/AGENTS.md` to it. Resolve the symlink and edit the target; commit there.
- Nothing overrides anything. Claude Code concatenates user + project files;
  Codex concatenates global → repo root → cwd. Conflicts are resolved by the
  model, arbitrarily. Say once in the global file that repo files win.
- Codex caps the *whole chain* (`project_doc_max_bytes`, 32 KiB by default) and
  truncates silently from the end, so a fat global file cuts the repo's file.
  Check what loaded: Claude `/context`; Codex: ask it to summarize its instructions.
- Adherence drops as instruction count grows, with a bias toward earlier lines.
  Budget: ≤ 4k tokens (~16 KB); behaviour-defining rules first, lookup facts last.
- Portable progressive disclosure = a plain pointer with a trigger: "doing X →
  read `/abs/path.md` first". Works in both harnesses. `@import` and
  `~/.claude/rules/` are Claude-only, and imports load eagerly (no saving).
  Use absolute paths: the working directory differs per session.
- One file, several harnesses/models: put the harness in the heading and tell
  the others to skip the block ("Claude Code only; Codex: skip").

## What belongs where

| Content | Home |
| --- | --- |
| Reporting style, autonomy limits, verification bar, delegation routing, machine tooling monoculture, repo map, personal aliases | global file |
| Architecture, domain terms, build/test/deploy commands of one project | that repo's entrypoint ([SKILL.md](SKILL.md)) |
| Multi-step procedures, rarely needed know-how | a skill (loads on demand) |
| Machine facts needed only for some tasks: browser profile IDs, account maps, tool recipes | pointer file beside the global file |
| Must happen with zero exceptions | hook / permissions / CI; prose is advisory |
| Secrets | nowhere in prose |

## Writing lines that get followed

- State intent and the reason; a capable model generalizes from "why" and needs
  no capitals. Emphasis works on one line; on ten it works on none.
- Keep an example where it saves hitting a wall: the exact spawn command with
  its flags, speech-to-text aliases, a status-emoji legend. Drop examples of
  things a frontier model gets right unprompted.
- Thresholds and mechanisms are proxies; name the intent next to them.
- No volatile values (IDs, versions, dates of verification) in the always-loaded
  file; they go stale silently. Pointer file instead.
- A rule born from an incident carries its reason in a clause, not the story.
- Personal facts are fine in the private file; they never travel to a shared template.

## Prune

1. Measure tokens (`uv run --with tiktoken python -c …`, `o200k_base` is close enough).
2. Read `git log -p` of the file: what was added for which incident, and does
   the cause still exist (old harness behaviour, abandoned workflow, weaker models)?
3. Classify every line: keep · tighten · pointer file · move to repo/skill ·
   enforce with a hook · delete (model does it anyway, duplicate, stale).
4. Uncertain deletions are experiments: remove, run a representative task in a
   fresh headless session (`claude -p`, `codex exec`), compare behaviour *and*
   tokens spent getting there. A line that saves three failed attempts earns its place.
5. For a large trim, have another frontier model compare before/after for lost
   behaviour. Report what was cut and why in a few lines; the diff is the record.

Signals between prunes: a rule is repeatedly ignored → file too long, or the rule
wants a hook. The agent asks what the file already says → wording is ambiguous.
The same correction given twice in chat → it is a missing line.

## Merge the template into someone's existing file

Their facts and preferences survive; the template adds behaviour they lack.

1. Read every copy (each Claude home, Codex, differing symlink targets). Back
   them up outside the repo before changing links.
2. Keep verbatim: identity, role, language, repos, accounts, tooling they
   actually use. Fill template placeholders from evidence (`gh api user`,
   `ls ~/code/*`, `mise ls`, `brew list`), not guesses; ask only for what the
   machine cannot tell you.
3. Same rule in both → the tighter wording. Conflict → theirs wins; list it.
4. Drop template sections for tools they lack (T3 threads, a second harness,
   deploy rights). Keep the template's model names; they are refreshed upstream.
5. Apply Prune to the result. End the file with
   `<!-- template: pjmuller/skills@<short-sha> -->`.
6. Show the human: conflicts, dropped sections, token count. Commit in their setup repo.

Re-sync later: `git log -p <sha>.. -- skills/agents-md/global-template.md` in a
clone of the skills repo; offer each change as adopt/skip, then update the marker.

## Port a live file's improvements into a shared template

The owner iterates on their private file; the template follows on request.
Walk `git log -p <last-ported>.. -- <live file>` hunk by hunk: a behaviour rule
any colleague would want → port it, reworded neutrally; a personal fact (path,
account, company, ID, colleague name) → placeholder or skip; a removal → remove
it from the template too unless it was personal. Record the new last-ported
commit beside the live file, not in the public template. Re-read the template
top to bottom afterwards: it must still stand on its own and hold nothing private.
