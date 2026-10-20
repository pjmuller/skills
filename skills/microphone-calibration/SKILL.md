---
name: microphone-calibration
description: Find the best macOS input gain for a microphone before dictation or recording - the speaker repeats one sentence after a beep at several gains; levels, clipping, noise, SNR and local speech-to-text accuracy go into a Markdown report with playable clips. Also single A/B samples (device, placement, filter) at a fixed level. Use for "test my microphone", mic gain/volume calibration, noisy or clipped dictation, comparing microphones.
---

# Microphone calibration

One variable per session: the device's input gain (the System Settings input slider, 0.0-1.0).
Same sentence, distance, posture and loudness every take; only back-to-back takes compare.
`scripts/install` links `mic-calibrate`; `--check` verifies dependencies and lists inputs. macOS only.

## Run

1. `mic-calibrate devices`: name, channels, settable gain. **No settable gain** (hardware knob, many
   USB mics) → the tool refuses to sweep; never "simulate" gain by amplifying afterwards. Instead
   `run --keep-gain`, one session per knob position the speaker sets.
2. Agree with the speaker first: device, mic position, the sentence (~5 s, their own words are
   fine), and that they are ready now. Never start a capture unannounced. `run --dry-run` shows
   device, levels and duration without recording or changing anything.
3. `mic-calibrate run --device NAME --sentence "…" [--levels 0.25,0.5,0.75,1.0] [--language en]`.
   Without a TTY (every agent shell) the capture opens in a **Terminal.app window**: it shows the
   sentence, waits for Enter, then per take sets the gain, says "Take N", records a quiet second
   (noise floor), beeps, and records `--seconds` of speech. Agent apps without microphone access
   record digital silence, which is why capture never runs in the agent's own shell. First use:
   macOS asks to allow Terminal's microphone. Run `run` in the background; it waits up to `--wait`.
4. The original gain is restored after the last take, on Ctrl-C and when the window closes. A
   killed run: `mic-calibrate restore SESSION_DIR`. `--apply-recommended` (or later
   `mic-calibrate gain --device NAME VALUE`) only after the speaker agrees.
5. Deliver `report.md`: recommendation, table, clips embedded by absolute path
   (`![take 2](/abs/…/take-2-gain-0.50.wav)`), transcripts. `results.json` has the same data.
   Re-analyse without recording: `mic-calibrate report SESSION_DIR [--no-stt]`.

Output: `~/Downloads/microphone-calibration/<time>-<device>/` (`--out`, `MIC_CALIBRATION_DIR`).
Device choice: `--device` > `MIC_DEVICE_NAME` > system default input; exact name, else a unique
case-insensitive substring. Other system audio settings stay untouched.

## Read the result

- **Measured**: peak and clipping (all channels), noise floor (quiet wait before the beep), speech
  level and SNR (loudest channel, beep frames removed by their 1 kHz tone). The pick is a
  **tested** level: no clipping, peak ≤ -3 dBFS, SNR within 3 dB of the best, then peak nearest
  -9 dBFS; transcript errors break ties. Refine with a narrower sweep around it (e.g. `0.6,0.7,0.8`).
- **Expect** SNR to barely change: input gain raises voice and room noise together. Gain mostly
  decides clipping (too high) versus a weak signal (too low); distance and room decide SNR.
- **STT**: `transcribe-local` (sibling `video-shrink-for-gemini`, local Whisper; nothing uploaded),
  same settings per take, the sentence is never passed as a hint. Equal transcripts do not mean
  equal audio, and the speaker's own dictation engine may behave differently.
- **Not measured**: how it sounds. Ask the speaker to listen to the extremes and the pick.
  A warning that speech level ignored the gain sweep points to onboard AGC, an ineffective control
  or changed delivery. A few takes of one sentence are evidence, not a global optimum.

A/B of device, placement or filter: `run --keep-gain --takes 1` per variant, same sentence.
