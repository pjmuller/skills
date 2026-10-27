# Lessons from live sessions

Read before planning a session. Numbers: one USB condenser mic, one speaker, one sentence per setting
(evidence, not law).

- **Distance is the lever, gain is not.** Software gain and an analog knob both raised voice and
  room noise together (knob +50%: voice +5 dB, noise +5.4 dB, SNR unchanged). Halving the distance
  added +6.4 dB SNR. A soft voice at 5 cm ≈ a normal voice at 10 cm; 30 cm or a whisper ≈ 17 dB.
- **Gain only sets the level.** Pick the highest level without clipping; at maximum software gain,
  a knob turned up brings a normal voice at 5 cm close to clipping.
- **Session design that worked:** (1) gain sweep + `--manual` knob takes; (2) `--keep-gain --manual`
  grid over voice × distance × knob, with a normal-voice reference take first.
- **Speakers slip** (a pause, then half the sentence). Offer `r` + Enter; `slip?` keeps such takes out
  of the WER ranking. Without it, one slip flipped the knob pick.
- **STT barely discriminates:** local Whisper got every take right down to ~16 dB SNR. Decide on
  peak/SNR, then confirm with the speaker's own dictation engine at the borderline setup.
- **Below ~18 dB SNR the live end detector misses the end**: the take runs to `--seconds`. Harmless.
- **Keep the UX minimal:** spoken prompts annoyed the speaker; one beep plus automatic end is enough.
- **Devices:** gain may be per channel only (no main element: set all) and quantized (0.25 → 0.2667);
  the report shows what was actually set. Whether an agent host can record changes over time:
  the digital-silence warning tells you.
