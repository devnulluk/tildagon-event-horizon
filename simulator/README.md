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
.\Launch-Simulator.ps1 -Record .\event-horizon-full.mp4 -Seconds 140 -Expansions
.\Launch-Simulator.ps1 -Showcase swarm -Record .\swarm-preview.mp4 -Seconds 60 -Expansions
```

The current 48-second trailer selects all nine chapters while animation continues
in real time. The 140-second capture follows the app's unmodified score from
zero. The earlier 0.1 films retain their eight-chapter, 48/120-second scope. Frame
metadata declares which mode was used. Recordings keep actual monotonic capture
timing, use no motion interpolation, and export H.264 MP4, GIF preview, poster,
contact sheet and JSON provenance. Native LCD crops are 240×240; full-window
captures retain the labelled simulator/virtual-control panel.

## Three virtual badges

`-Swarm` starts an in-memory peer preview of the firmware's ESP-NOW service with
the production app and two additional production `Swarm`/`Show` instances. It
never starts a real radio adapter or Wi-Fi connection. The lab uses the actual
ten-byte message and its 31-byte application envelope/parser. Artificial packet
repeats, two payload updates per second and bounded receive queues exercise the
model independently of hardware timing. Artificial session IDs are deterministic;
no physical address or nearby device is read. The optional RSSI value is
synthetic and is not distance.

The preview's channel-1 readout is explicitly synthetic. Physical participants
must share the same current 2.4GHz Wi-Fi channel to use the official ESP-NOW
broker. The app does not directly select a channel/SSID or write saved Wi-Fi
settings. The shared firmware broker owns the real radio and may activate its
station interface or change power-saving mode as part of that service; leaving
the app is not a claim that the global radio is off. The host preview performs
none of those physical operations.

The sixty-second `-Showcase swarm` sequence covers solo, one peer joining, three
virtual badges, two remote boosts, conductor handover, peers leaving and expiry
back to solo. Local scene cuts expose both the full Gravitational Choir scene and
its sparse overlays; peer packets do not select scenes or pause another badge.
The script ends with both virtual peers quiet; the interactive app then continues
in solo mode. Radio status and encoded video labels explicitly identify this as
a simulation, not evidence from two physical badges or a radio-range test.
The in-memory adapter replaces the firmware broker: this preview exercises the
production message/model/render path, not native ESP-NOW delivery, channel
coordination, radio scheduling or hardware watchdog stability. The previous BLE
transport investigations remain separate historical evidence.

Repeatable stills can preplay the same real packet/state path:

```powershell
.\Launch-Simulator.ps1 -Swarm -SwarmStage trio -Screenshot -OutputPath .\swarm-trio.png -Expansions
.\Launch-Simulator.ps1 -Swarm -SwarmStage burst -Screenshot -OutputPath .\swarm-burst.png -Expansions
```

Stages are `solo`, `joined`, `trio`, `burst`, `handover` and `departed`. A still's
metadata records its synthetic preroll. `-SwarmStage` cannot be combined with a
recording; record the real-time script instead. The Python equivalents are
`--swarm`, `--swarm-stage` and `--showcase swarm`. Normal simulator runs leave
nearby radio disabled unless this explicit virtual lab is selected.

An original 120 BPM score can accompany the exported video:

```powershell
py -3.10 tools/compose_soundtrack.py --seconds 48 --output .\score-48.wav
.\Launch-Simulator.ps1 -Record .\event-horizon-trailer.mp4 -Seconds 48 -Soundtrack .\score-48.wav -Expansions
```

The composer provides the existing 48/120-second video arrangements; it does not
generate a new 140-second arrangement. The swarm preview may use the first sixty
seconds of the original 120-second composition. Audio is muxed as AAC with the
already-encoded video stream copied unchanged and the requested exact duration
enforced. A silent MP4 is retained, and GIF previews are silent. This soundtrack
is for the video; the badge app does not play it through hardware audio.

The Python CLI accepts `--scene`, `--gallery`, `--screenshot`, `--output`, `--record`, `--seconds`, `--showcase`, `--quality` and `--expansions`. Set `SDL_VIDEODRIVER=dummy` for headless captures; the PowerShell wrapper does this automatically. Video performance reflects the desktop simulator and does not establish physical badge FPS.

Only runtime Python source and public manifests are copied into this cache. Its generated app configuration contains no personal data or credentials. The firmware's optional boot animation is disabled in the simulator process so it cannot cover the captured demo; no connected badge setting is touched.
