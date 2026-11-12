# Event Horizon gallery

Open [index.html](index.html) for the gallery or [contact-sheet.png](contact-sheet.png) for all nine chapters of Event Horizon. Every screenshot is produced by the app running inside the official SDL/ctx simulator. Native LCD files are 240×240; full-window files include clearly labelled virtual Spaceagon controls and expansion diagrams. These are not photographs or physical FPS evidence.

The current [sixty-second Nearby preview](swarm-preview.mp4),
[GIF](swarm-preview.gif) and [contact sheet](swarm-preview-contact-sheet.png)
use three virtual badge models with in-memory packet delivery and a synthetic
matching channel. Actual production packet encoding, parsing, duplicate
handling, expiry and visual responses are exercised. There are no physical
radios in this capture. It is
not a test of native ESP-NOW scheduling, channel control, three physical badges,
RF range or two-badge over-air exchange.
See the [Nearby guide](../SWARM.md) and [native evidence](../VALIDATION.md).

For physical Nearby use, every badge must run a matching ESP-NOW release on the
same **current 2.4 GHz channel**, displayed as **CH**. A matching SSID is not
sufficient across access points on different channels. The app observes the
channel and never changes it. The earlier Bluetooth beta cannot join this
transport. The shared ESP-NOW broker is preferred where available; otherwise
the app can claim an inactive raw singleton. A simulator film proves neither
hardware path. The physical full-show soak used the normal booted system's
broker; the separate raw check qualified its API and cleanup only.

The final native twelve-peer fixture also injected synthetic broker events.
**Two physical badges exchanging ESP-NOW messages have not been verified.**
Neither the native callback fixture nor this film should be read as that proof.

From the project checkout:

```powershell
py -3.10 tools/prepare_simulator.py
.\Launch-Simulator.ps1 -Gallery .\docs\gallery -Expansions
.\Launch-Simulator.ps1 -Showcase swarm -Record .\docs\gallery\swarm-preview.mp4 -Seconds 60 -Expansions
```

The current on-device show has nine chapters and lasts 140 seconds. The Nearby
preview is a representative sequence with explicit simulator events and scene
cuts; it does not accelerate the underlying animation. Its metadata records
the virtual-peer configuration and capture timing.

The original **0.1** [48-second trailer](../media/event-horizon-trailer.mp4)
and [120-second film](../media/event-horizon-full.mp4) are historical recordings
of the earlier eight-chapter edition. Use the **0.1.0 source checkout** for the
old video-capture commands below. The original soundtrack arrangements can
still be regenerated independently; they do not define the new live show's
length:

```powershell
py -3.10 tools/compose_soundtrack.py --seconds 48 --output .\score-48.wav
py -3.10 tools/compose_soundtrack.py --seconds 120 --output .\score-120.wav
.\Launch-Simulator.ps1 -Record .\docs\media\event-horizon-trailer.mp4 -Seconds 48 -Soundtrack .\score-48.wav -Expansions
.\Launch-Simulator.ps1 -Record .\docs\media\event-horizon-full.mp4 -Seconds 120 -Soundtrack .\score-120.wav -Expansions
```

The historical trailer selected eight chapters at six-second boundaries; its
full film followed the earlier 120-second score. Reproducing those exact old
scene cuts requires the 0.1.0 source tag. All videos retain actual monotonic
capture timing; FFmpeg duplicates/drops samples as needed for the output frame
rate and performs no motion interpolation. JSON siblings contain source
hashes, capture timing and encoding proof.

Published media metadata uses repository-relative artifact paths. Generated WAV
references point to the reproducible `work/horizon-media/` output directory;
those intermediate files are not part of the badge download. Machine-local
directory prefixes are omitted while source hashes, frame counts and timing
remain unchanged.

`badge_source_sha256` hashes canonical UTF-8 source bytes with CRLF normalized
to LF, matching the repository's published source. The gallery's `source_hashes`
field is an alias for that canonical map. `capture_raw_badge_source_sha256`
preserves the original on-disk hashes from capture, so line-ending changes do
not erase provenance. The JSON states this normalization explicitly.

To add the original 120 BPM video soundtrack, compose a 48- or 120-second WAV using [compose_soundtrack.py](../../tools/compose_soundtrack.py), then pass it as `-Soundtrack`. The encoder copies the video stream unchanged while muxing AAC, caps the requested duration, retains the silent original, and keeps GIF previews silent. The badge itself does not play this soundtrack.

See [simulator/README.md](../../simulator/README.md) for prerequisites, controls, Python CLI equivalents and the isolated cache layout. Neither capture nor setup connects to USB or changes a badge setting.

The official simulator and its board artwork are from Electromagnetic Field.
Its [MIT copyright and permission notice](../SIMULATOR-LICENSE.txt) is retained
here; the upstream [firmware licence](https://github.com/emfcamp/badge-2024-software/blob/f10ecb8b18631b0cd328c765b4a3d9f39dbe1ede/LICENSE)
identifies that source. The procedural show itself and its original soundtrack
use the [project licence](../../LICENSE).
