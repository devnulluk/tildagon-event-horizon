# Controls and settings

Event Horizon 0.2 runs its nine-chapter, 140-second loop immediately after launch.
Animation uses elapsed time rather than frame counts. Pausing holds the scene
position; chapter navigation still works while paused. A boost briefly adds
energy to the current world and light pattern without exceeding brightness
settings. With Nearby enabled, a local boost is also advertised to other
copies; a received boost adds a visual response without being rebroadcast.

## Six physical buttons

| Button | During the show | In settings |
| --- | --- | --- |
| A | Boost on a short press; hold about 0.85 s to open settings | Previous row |
| B | Next chapter | Increase value |
| C | Pause / resume | Save and close |
| D | Show / hide HUD | Next row |
| E | Previous chapter | Decrease value |
| F | Exit the app | Save and close |

Buttons held while the app launches are suppressed until released. A long A
press opens settings without first firing its short-press boost. Holding a
navigation button does not repeatedly skip chapters.

## Spaceagon joystick

| Direction | During the show | In settings |
| --- | --- | --- |
| Left / right | Previous / next chapter | Decrease / increase |
| Up | Boost | Previous row |
| Down | Show / hide HUD | Next row |
| Press | Pause / resume | Save and close |

The app accepts the Spaceagon frontboard's canonical joystick events. Ordinary
physical A–F buttons retain their own mappings.

## Touch ring and motion

Tap a pad to choose a chapter. Moving across adjacent pads produces a
next/previous rotation gesture. A rotation is not also treated as a tap.
The twelve pads map onto nine chapters as follows:

| Pads | Chapter |
| --- | --- |
| 1–2 | Opening |
| 3 | Departure / starflight |
| 4 | Hyperspace / tunnel |
| 5–6 | Signal Lost / terrain |
| 7 | New Worlds / planet |
| 8 | Gravitational Choir / nearby constellation |
| 9–10 | Crystal Mind / kaleidoscope |
| 11 | Event Horizon / black hole |
| 12 | Finale |

Touch-ring gestures are ignored while settings are open. Joystick navigation
remains available there. Relative accelerometer tilt moves the scene viewpoint;
it is enabled by default for this show and can be disabled in settings or with
keyboard T. It is not an absolute compass heading. Invalid motion readings
return toward a neutral view.

Proximity gestures are disabled by default. An explicit private
`"space_proximity": true` configuration enables a deliberate two-sensor sweep
as another boost input. The app uses the running frontboard driver and cached
sensor readings; it does not scan arbitrary expansion buses or configure IMU
registers.

## Keyboard

| Key | During the show |
| --- | --- |
| Left / right | Previous / next chapter |
| Up | Boost |
| Down or H | Show / hide HUD |
| Enter or Space | Pause / resume |
| S | Open settings |
| T | Toggle tilt |
| Escape | Exit |

In settings, up/down chooses a row and left/right changes it. Enter, Space, S
or Escape saves and closes settings. The
[simulator guide](../simulator/README.md) includes keyboard substitutes for the
twelve touch pads and mouse-operated virtual controls.

## Settings

| Row | Meaning | Fresh default |
| --- | --- | --- |
| Ring | Maximum outer-ring brightness | 15% |
| EEH | Maximum EEH Logo brightness | 3% |
| Matrix | Maximum Liteloop brightness | 12% |
| Detail | Maximum drawing detail; adaptation can reduce it on slow frames | 90% |
| Tilt | Relative scene viewpoint motion | On |
| Nearby | Bluetooth advertisement discovery and shared visual events | On |

Numeric rows move in one-percentage-point steps and are clamped to 0–100%.
Brightness values are independent, including zero. Existing local brightness
preferences can supply the initial ring/logo levels. Changes are stored under
the app's own firmware settings when settings close or the app exits. Keyboard
T is saved on a normal exit as well.

Nearby is the sixth row. Switch it off to stop this app's advertising and
scanning and clear the peer view. It does not change Wi-Fi settings. If another
app already owns Bluetooth, Event Horizon leaves that radio alone and continues
the solo show. Detailed behaviour is in the [Nearby guide](SWARM.md).

Recognized optional expansions are driven only when available and not already
owned by another driver. If the matrix is absent, removed or fails, the LCD and
other controls remain usable. On exit, the app stops its sensor subscriptions,
darkens its owned ring/logo and gives the matrix a short opportunity to accept
a blank frame. An external matrix processor can retain its last frame if that
transfer cannot finish; its own app or a power cycle replaces it.
