# Event Horizon simulator

This runs the production Event Horizon app through the official Tildagon SDL/ctx renderer. It uses no USB connection, live hardware or PBX. Spaceagon controls and optional hexpansions are explicit virtual devices.

## Setup

Git and CPython 3.10 are prerequisites. From this project checkout:

```powershell
py -3.10 tools/prepare_simulator.py
.\Launch-Simulator.ps1
```

Setup creates a local `.simulator/` cache, downloads a shallow sparse checkout of the [official firmware at f10ecb8b](https://github.com/emfcamp/badge-2024-software/tree/f10ecb8b18631b0cd328c765b4a3d9f39dbe1ede), verifies its already-compiled `ctx.wasm`, and installs [pinned dependencies](requirements.txt) into a local virtual environment. No firmware toolchain, global Python package installation, overclock or power-policy change is used.

For Linux/macOS:

```sh
python3.10 tools/prepare_simulator.py
.simulator/venv/bin/python simulator/launch.py
```

Some Linux/macOS machines need the SDL packages described by the [official simulator](https://github.com/emfcamp/badge-2024-software/blob/f10ecb8b18631b0cd328c765b4a3d9f39dbe1ede/sim/README.md). Those platforms have not been exercised here. Windows with CPython 3.10.18 was verified. The optional `mad`/MP3 warning is harmless for this demo.

`TILDAGON_HORIZON_SIM_ROOT` selects another cache directory; this is intentionally separate from the 3CX simulator. PowerShell also accepts `-SimRoot`. To reuse an existing compatible environment without modifying it:

```sh
python3.10 tools/prepare_simulator.py --reuse-runtime /path/to/venv/bin/python
python3.10 tools/prepare_simulator.py --check
```

Keep `.simulator/` out of Git and release archives. It contains generated settings, logs, temporary frames and machine-local runtime paths.

## Controls

- **Arrows / Enter:** the Spaceagon joystick; left/right change scene, up boosts, down toggles HUD, Enter pauses.
- **1–9,0,-,=:** the 12 touch pads. A tap selects a scene; neighbouring steps rotate through scenes. The joystick and ring diagrams can also be clicked/dragged.
- **Drag the small tilt disc:** simulated relative accelerometer tilt.
- **A:** boost on release; hold A for settings.
- **B/E:** next/previous scene; **C/Space:** pause; **D/H:** HUD.
- **S:** settings; **T:** tilt toggle; **F/Escape:** exit.

Proximity gestures are disabled. The optional EEH and Liteloop diagrams are simulations, not physical photographs or brightness measurements. The matrix diagram normalizes PWM for visibility and uses the documented 156-LED mapping.

## Captures

```powershell
.\Launch-Simulator.ps1 -Gallery .\docs\gallery -Expansions
.\Launch-Simulator.ps1 -Scene tunnel -Screenshot -OutputPath .\tunnel.png
.\Launch-Simulator.ps1 -Record .\event-horizon-trailer.mp4 -Seconds 48 -Expansions
.\Launch-Simulator.ps1 -Record .\event-horizon-full.mp4 -Seconds 120 -Expansions
```

The 48-second trailer selects all eight chapters in six-second sections while animation continues in real time. The 120-second capture follows the app's unmodified two-minute score from zero. Frame metadata declares which mode was used. Recordings keep actual monotonic capture timing, use no motion interpolation, and export H.264 MP4, GIF preview, poster, contact sheet and JSON provenance. Native LCD crops are 240×240; full-window captures retain the labelled simulator/virtual-control panel.

An original 120 BPM score can accompany the exported video:

```powershell
py -3.10 tools/compose_soundtrack.py --seconds 48 --output .\score-48.wav
.\Launch-Simulator.ps1 -Record .\event-horizon-trailer.mp4 -Seconds 48 -Soundtrack .\score-48.wav -Expansions
```

Use the 120-second composition for the full film. Audio is muxed as AAC with the already-encoded video stream copied unchanged and the requested exact duration enforced. A silent MP4 is retained, and GIF previews are silent. This soundtrack is for the video; the badge app does not play it through hardware audio.

The Python CLI accepts `--scene`, `--gallery`, `--screenshot`, `--output`, `--record`, `--seconds`, `--showcase`, `--quality` and `--expansions`. Set `SDL_VIDEODRIVER=dummy` for headless captures; the PowerShell wrapper does this automatically. Video performance reflects the desktop simulator and does not establish physical badge FPS.

Only runtime Python source and public manifests are copied into this cache. Its generated app configuration contains no personal data or credentials. The firmware's optional boot animation is disabled in the simulator process so it cannot cover the captured demo; no connected badge setting is touched.
