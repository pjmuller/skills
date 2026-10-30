---
name: t3-retro
description: "Use for a weekly retro on how you work with your agents: \"t3 retro\", \"/t3-retro\", \"coach me on my prompting\", \"what should I change in how I use agents\", \"which workarounds do my agents keep using\". Reads your own T3 threads on this machine (your prompts and the agents' answers) and returns one change to make, under 250 words. Not for mining prompts into rules only (t3-maintenance t3-my-prompts) or reviewing someone else's work."
---

# t3-retro

Why: you are the bottleneck, not the agents. Once a week, look at what actually happened in your
threads (what you asked, what the agent claimed, what broke, what you had to correct) and change
**one** thing: a line in a file, a check, a hook or a default. One change that happens beats five
that don't. The retro must remove more work than it creates. North star: agents that close their
own feedback loop; every look, click or paste you do for them is a candidate change.

Method (sources in [lens.md](lens.md)): Anthropic's study of ~400k Claude Code sessions rates how
precise the goal was, what the user asked to verify and who corrected whom; Claude Code's best
practices map each failure to one fix type; error analysis reads the threads first and notes the
first failure in each before grouping.

## Run (≈10 min, one agent, no sub-agents)

1. `t3-retro-prep` (from `t3-maintenance`; `--days 7` default, `--until`, `--out`). Read-only. It
   writes `packets.md` + `selection.json` to `~/.local/state/t3-retro/<date>/` (mode 700, outside
   any repo) and prints the path. It picks 12 threads: 8 by signal, 4 at random (silent omissions
   raise no signal), max half from one project, plus a table of errors that recur across threads
   and phrases you typed in several threads. Packets are secret-masked and capped (~30k tokens).
2. Read `packets.md` whole, then the previous `report.md` it names. Judge with [lens.md](lens.md).
   A signal is a lead, not a verdict. Open a thread (`t3-find-thread <id>`, or the store) only to
   confirm a finding before you write it.
3. Write `report.md` next to `packets.md` in the shape below, ≤250 words, and show it inline as
   your answer. Nothing else: no HTML, no question list, no backlog.
4. Don't apply the change. The user decides; applying it is a separate request.

## Report shape

```markdown
**Coverage:** <window> · <n> of <eligible> threads read · <gaps: purged, no tool history, odd day>
**Last change:** <not applied | applied, outcome unknown | helped | didn't help>: <evidence>
**This week's change:** <finding, 1 sentence> (<thread ids, ≤2>)
- Fix type: <context | check | enforce | default>
- Exact change: <the line and its file, or the setting/command>
- Next run can see it worked when: <observable signal>
**Keep doing:** <one pattern with evidence; useful agent initiative counts>
**Also serious (optional):** <only an unresolved problem with real cost>
```

Last change not applied → name what got in the way and make it smaller, or drop it. Never repeat
it as a new finding.

## Privacy

Everything stays in `~/.local/state/t3-retro/`. The model provider sees the selected excerpts, as
in any agent session; masking (`t3_redact`) misses secrets in prose, so don't paste the packets
anywhere. Sharing is the user's choice: at most the report's lines, never packets or transcripts.
A wrapper skill may add personal lenses or a destination for the report; it reuses this run.
