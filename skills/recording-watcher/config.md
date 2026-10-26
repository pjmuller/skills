# Machine config

`~/.config/recording-watcher/config.json` (env `RECORDING_WATCHER_CONFIG` overrides), chmod 600,
outside the installed skill. `recording-watcher check` validates it; errors stop the poll loudly.

```json
{
  "self": "ana",
  "roster": "~/code/acme/team-setup/recording-roster.json",
  "sources": {
    "fathom": {"env_file": "~/.config/mise-env/acme/backend.env"},
    "leexi": {"env_file": "~/.config/mise-env/beta/app.env", "workspace": "~/code/beta/app"},
    "monologue": {"env_file": "~/.config/mise-env/acme/notes.env", "personal": true}
  },
  "workspace": "~/code/acme/backend",
  "routes": [{"workspace": "~/code/beta/app", "names": "\\b(dan|beta)\\b", "emails": ["@beta.example"]}],
  "model": "sol",
  "briefs_dir": "~/code/acme/team-setup/briefs",
  "followups_skill": "~/code/acme/team-setup/.agents/skills/acme-followups/SKILL.md",
  "speaker_aliases": {"Alpha Office": "Ben Example"}
}
```

| Key | Meaning |
| --- | --- |
| `self` | This machine's roster person. Required. |
| `roster` | Inline object or path; identical on every team machine ([schema](owner-election.md#roster)). |
| `sources` | Enabled providers. `env_file`: mise env file with `FATHOM_API_KEY`, `LEEXI_KEY_ID` + `LEEXI_KEY_SECRET`, or `MONOLOGUE_API_KEY` (process env wins). `workspace` pins every call of that source. `personal`: the account is only this person's, so no election. |
| `workspace` | Default T3 project (registered in T3) for follow-up threads. |
| `routes` | Optional speaker/invitee → workspace votes (`names` regex, `emails` suffixes). |
| `model` | Optional `t3-relay launch --model` alias; omitted = t3-relay's default ([relay.md](../t3-manage-thread/relay.md)). |
| `briefs_dir` | Optional `<workspace-basename>.md` / `default.md` templates; else [briefs/default.md](briefs/default.md). Variables `$facts $media $transcript $workspace $followups`. |
| `followups_skill` | Skill the thread runs; default the core [recording-followups](../recording-followups/SKILL.md). |
| `speaker_aliases` | Display name of a shared recorder login → the person, for transcripts/titles only. Never identity evidence. |

Paths may use `~`. Keys never go in this file or the roster.
