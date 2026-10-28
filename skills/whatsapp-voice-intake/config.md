# Machine config

`~/.config/whatsapp-voice-intake/config.json` (env `WHATSAPP_VOICE_INTAKE_CONFIG` overrides), outside the
installed skill; a wrapper repo may own it and link it there. `whatsapp-voice-intake check` validates it.

```json
{
  "self_number": "+32470123456",
  "owner": "Ana",
  "hours": {"timezone": "Europe/Brussels", "days": ["mon", "tue", "wed", "thu", "fri"], "start": "09:00", "end": "18:00"},
  "hint": "Dutch or English, often mixed in one sentence",
  "vocabulary": "~/code/acme/setup/.agents/skills/voice-intake/vocabulary.md",
  "target": {"project": "~/code/acme/setup", "title": "🧭 Ana routing"},
  "fallback": {"brief": "~/code/acme/setup/.agents/skills/voice-intake/router-init.md", "model": "astra", "effort": "medium"},
  "daily_audio_minutes": 60
}
```

| Key | Meaning |
| --- | --- |
| `self_number` | The paired account's number. Every poll checks the self chat's sender against it and refuses on mismatch. Required. |
| `owner` | Name used in the delivered message ("Ana dictated this"). |
| `hours` | Poll window, local time; defaults shown. Outside it the job exits without reading. |
| `hint` | Transcription hint: languages and how they mix. |
| `vocabulary` | Optional Markdown file of terms to spell exactly, best with how dictation mishears them (`Globex ≈ "Glow Bex"`). Mine it from the words you actually use (e.g. your router thread messages); re-read per note. |
| `context` | Optional override of the purpose line the transcriber gets (default `CONTEXT` in the script: a note-to-self for a dispatcher, still verbatim). |
| `target` | T3 project root and **exact** thread title to deliver to. Required. |
| `fallback` | Optional. No open target → launch one thread with `Read and execute <brief>` (t3-relay model/effort; runtime = the user's new-thread default). Omit to only alert. |
| `daily_audio_minutes` | Paid transcription cap per local day (default 60 ≈ $0.25). |

Seed on a new machine: `whatsapp-voice-intake seed` (plus `--include <id>` for a specific earlier note from
`wa read me`), then `scripts/install --schedule` and `scripts/install --check`.
