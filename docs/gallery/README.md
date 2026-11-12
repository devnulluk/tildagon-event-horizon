# Event Horizon gallery

Open [index.html](index.html) for the gallery or [contact-sheet.png](contact-sheet.png) for all eight chapters. Every screenshot is produced by the app running inside the official SDL/ctx simulator. Native LCD files are 240×240; full-window files include clearly labelled virtual Spaceagon controls and expansion diagrams. These are not photographs or physical FPS evidence.

From the project checkout:

```powershell
py -3.10 tools/prepare_simulator.py
.\Launch-Simulator.ps1 -Gallery .\docs\gallery -Expansions
py -3.10 tools/compose_soundtrack.py --seconds 48 --output .\score-48.wav
py -3.10 tools/compose_soundtrack.py --seconds 120 --output .\score-120.wav
.\Launch-Simulator.ps1 -Record .\docs\media\event-horizon-trailer.mp4 -Seconds 48 -Soundtrack .\score-48.wav -Expansions
.\Launch-Simulator.ps1 -Record .\docs\media\event-horizon-full.mp4 -Seconds 120 -Soundtrack .\score-120.wav -Expansions
```

The trailer selects all eight chapters at six-second boundaries without accelerating their animation. The full film follows the app's natural 120-second score from zero. Videos retain actual monotonic frame timing; FFmpeg duplicates/drops samples as needed for the output frame rate and performs no motion interpolation. JSON siblings contain source hashes, capture timing and encoding proof.

Published media metadata uses repository-relative artifact paths. Generated WAV
references point to the reproducible `work/horizon-media/` output directory;
those intermediate files are not part of the badge download. Machine-local
directory prefixes are omitted while source hashes, frame counts and timing
remain unchanged.

To add the original 120 BPM video soundtrack, compose a 48- or 120-second WAV using [compose_soundtrack.py](../../tools/compose_soundtrack.py), then pass it as `-Soundtrack`. The encoder copies the video stream unchanged while muxing AAC, caps the requested duration, retains the silent original, and keeps GIF previews silent. The badge itself does not play this soundtrack.

See [simulator/README.md](../../simulator/README.md) for prerequisites, controls, Python CLI equivalents and the isolated cache layout. Neither capture nor setup connects to USB or changes a badge setting.

The official simulator and its board artwork are from Electromagnetic Field.
Its [MIT copyright and permission notice](../SIMULATOR-LICENSE.txt) is retained
here; the upstream [firmware licence](https://github.com/emfcamp/badge-2024-software/blob/f10ecb8b18631b0cd328c765b4a3d9f39dbe1ede/LICENSE)
identifies that source. The procedural show itself and its original soundtrack
use the [project licence](../../LICENSE).
