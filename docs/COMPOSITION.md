# Signal Beyond: original trailer soundtrack

`tools/compose_soundtrack.py` creates the Event Horizon video's original score.
It uses only Python's standard library and synthesizes every sound from
oscillators and deterministic noise. There are no sampled recordings, imported
melodies, downloaded instruments or third-party backing tracks. The composition,
generative source and generated recordings are provided under the project's
[MIT licence](../LICENSE).

This audio is for the trailer video. The badge app does not play it and does not
assume a speaker or audio output exists on the hardware.

The generator retains the original eight-act, 48- and 120-second video
arrangements. These are independent of the current nine-chapter, 140-second
badge loop: the music has no separate Gravitational Choir act. Video edits may
use an excerpt, with the chosen arrangement and duration recorded in their
media metadata.

The music is in D minor at 120 BPM. Its repeating harmonic colours are D minor
add9, B-flat major7, F major add9 and C add9. An original D–F–A–E melodic figure
connects the acts. Warm detuned pads, a controlled three-harmonic chiptune arp,
sub/upper bass, synthesized pitch-swept kick, noise snare and hats build toward
the black-hole scene. A quieter planet act provides contrast. Cross-channel
dotted-eighth echoes provide width; a final tonic and fade close the piece.

| Act | 120-second arrangement | 48-second arrangement |
| --- | --- | --- |
| Intro | 0–8 s | 0–6 s |
| Starflight | 8–24 s | 6–12 s |
| Tunnel | 24–40 s | 12–18 s |
| Terrain | 40–56 s | 18–24 s |
| Planet | 56–72 s | 24–30 s |
| Kaleidoscope | 72–88 s | 30–36 s |
| Black hole | 88–108 s | 36–42 s |
| Finale | 108–120 s | 42–48 s |

Generate either arrangement from the project directory:

```sh
python tools/compose_soundtrack.py --seconds 120 --output work/horizon-media/event-horizon-120.wav
python tools/compose_soundtrack.py --seconds 48 --output work/horizon-media/event-horizon-48.wav
```

The default is 24 kHz stereo, 16-bit PCM; `--rate` also accepts 16000 or 44100.
`--seed` reproduces the synthesized percussion. The shorter arrangement uses
the same instruments and motifs, with eight six-second chapters aligned to
twelve beats each, rather than abruptly truncating the long arrangement.

A JSON sidecar records exact frames/duration, sample peak, true sample RMS,
RMS dBFS, DC offset, stereo difference and clipping checks. Master gain is
limited by both a 0.92 sample-peak ceiling and 0.17 RMS target. It does not
claim a measured LUFS or oversampled inter-sample true peak. Both ends fade
to zero and no clipping/limiter distortion is used to obtain loudness.
