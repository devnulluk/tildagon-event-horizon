# Native validation

## Version 0.2.1: ESP-NOW native endurance

**RF scope:** native tests used one physical Spaceagon. An ESP-NOW exchange
between two physical badges has **not** been verified; multi-peer fixtures and
the simulator film use synthetic peers.

All **151 automated tests passed** for the current source, including 29
transport checks for shared-broker subscription ownership, inactive raw
singleton ownership, bounded polling, payload copying, rate limits, cleanup
retries, stale-handler clearing and conditional power-mode restoration. These
hardware-independent checks do not establish long-duration native stability.

The [native full-show soak](hardware-espnow-soak-0.2.1.json) completed **679
seconds and 3,688 rendered frames across all nine chapters**, with zero recorded
errors. The normal booted system used its **shared ESP-NOW broker, channel 6**.
The app remained focused, Spaceagon motion was valid, and the EEH Logo and
matrix stayed ready. There were 1,145 accepted broadcast requests, zero rejected
sends and no last transport error. The matrix completed 262 register frames.

| Native ESP-NOW soak measurement | Result |
| --- | --- |
| Duration | 679 s |
| Rendered frames | 3,688 |
| Chapters | All nine |
| Recorded errors / rejected sends | 0 / 0 |
| Adapter / observed channel | Shared broker / 6 |
| Accepted broadcast requests | 1,145 |
| Free heap before / after | 1,534,960 / 1,529,488 bytes |
| Lowest uncollected free heap | 1,378,944 bytes |
| Completed matrix frames | 262 |

The report's legacy `advertisement_updates` field counts accepted ESP-NOW
broadcast requests, not observed over-air packets. No other physical badge was
present in the peer view. This run verifies sustained operation under the
tested conditions, not an indefinite stability or fixed-FPS guarantee, a
controlled heap-leak proof, or an exchange between two physical badges.

The separate [raw API qualification](hardware-espnow-qualification.json) used
**raw mode on channel 6**, accepted one transmit request and closed without an
error, confirming the owned raw instance inactive afterward. It was performed
in a bare REPL. Failure to import the broker in that context did not establish
that the full booted firmware lacked it; the endurance report confirms broker
mode during normal launch. The raw fallback's API check is not a 679-second
endurance result for raw mode.

The app prefers that shared broker where available; only when it is unavailable
can the fallback claim an inactive raw singleton. Either path may activate STA
and manage power saving as documented in [SWARM.md](SWARM.md), but neither
writes a channel, SSID, credentials or connect/disconnect request. Raw close
leaves STA active. No Bluetooth activation, firmware modification or watchdog
change is used. Participants need matching releases on the **same current
2.4 GHz channel**, observed as **CH**; the same SSID alone is insufficient.

The endurance run preceded one cosmetic change adding a dark background behind
the channel/status text; transport behavior was unchanged. The measured
endurance figures above apply to the pre-contrast-plate display revision.

The [final-source native fixture](hardware-espnow-stress-0.2.1.json) then checked
that updated display across all nine scenes and with twelve synthetic peers.
Synthetic messages entered through the app's actual broker callback on the
physical badge; they were **not received over the air**. The run recorded no
errors on broker mode/channel 6. Seven remote visual echoes left the outbound
boost counter at zero; one local boost advanced it to one. Peers expired to zero.
Nearby off paused app sends and removed its subscription; focus loss also
removed the subscription, both restart paths succeeded, and the shared radio
was preserved. EEH Logo, matrix, Spaceagon and foreground readiness stayed true.

Those scene samples were short and used adaptive detail; they are not a fixed
FPS or sustained twelve-peer performance guarantee. The complete final source
also passed all 151 tests, compilation and diff checks after the visual change.
The virtual-peer simulator exercises neither native hardware adapter and does
not prove physical RF reception.

The [final clean-startup record](hardware-final-0.2.1.json) confirms 0.2.1 running
and focused in the intro, using the broker on channel 6 with Nearby enabled.
Spaceagon motion, keyboard, EEH Logo and matrix readiness were true; ring and
logo brightness remained 15% and 3%. This is a startup smoke check, not another
endurance run or a physical peer-exchange test.

### Withdrawn Bluetooth implementations

The published 0.2.0 beta and later unpublished local 0.2.1 Bluetooth attempts
were withdrawn after full-application reset failures. The underlying native
cause remains unproven; the ESP-NOW replacement is a different transport, not
a claim that a Bluetooth or firmware fault has been repaired.

The [finite-scan attempt](hardware-watchdog-0.2.1.json) used 300 ms scans and
40 ms quiet boundaries. Its last progress was 41 seconds, 229 frames and four
chapters; after reconnecting, the app was absent and the reset cause was again
`WDT_RESET` (3). A separate RTC-instrumented
[diagnostic run](hardware-rtc-probe-0.2.1.json) completed 309 seconds, illustrating
that the failure did not reproduce on every timing-altered run.

A later controller-off Bluetooth burst attempt with an active host serial
reader ended without a completed report after last reporting 377 seconds,
1,289 frames and all nine chapters. Its serial-closed full-application attempt
also left no fresh completed native report: the app was absent and the observed
reset-cause classification was 2. That classification does not identify the
failing native operation or subsystem. Closing the host reader therefore did
not establish a stable operating condition. Neither burst attempt qualified
as a stable release.

Further isolated checks ran without the UI or expansion I/O:

- [Fixed BLE advertising](hardware-bare-ble-tx.json) completed 120 seconds.
- The [unmodified finite-scan transport](hardware-bare-ble-link.json) completed
  120 seconds and 237 native advertisement updates, then confirmed the radio
  off. No over-air reception was recorded.

These are subsystem-isolation observations, not proof that the full application
is stable or that a particular native subsystem caused the resets. A fixed
advertisement with the complete UI also reset, so receive callbacks and parser
work were not required to reproduce the problem. None of these Bluetooth
results is an endurance result for the replacement ESP-NOW implementation.

## Version 0.2.0: watchdog observation and isolation

The [extended radio-on test](hardware-watchdog-0.2.0.json) did **not** complete.
Its last progress report showed 247 seconds, 1,366 rendered frames and all nine
chapters. USB serial then dropped before the final report. After reconnecting,
the app was absent and `machine.reset_cause()` equalled the firmware's
`WDT_RESET` constant, both 3. That establishes a watchdog reset; it does not
identify the task, native subsystem or exact instruction responsible. Version
0.2.0 was marked as a pre-release while this was investigated.

Two follow-up native checks isolated the renderer with Nearby disabled:

- The [radio-off soak](hardware-soak-0.2.0-radio-off.json) completed **309
  seconds and 1,699 frames** across all nine chapters, with zero recorded
  errors. Motion, foreground focus, EEH Logo and matrix readiness remained true.
- The [late-kaleidoscope iris stress](hardware-kaleidoscope-stress.json)
  completed **99 draws**: score positions 107,840–107,995 ms in 5 ms steps plus
  107,999 ms, each at quality 0.25, 0.6 and 0.9. The radio was off and tilt was
  fixed at zero. No errors were recorded, and the original show, pause state,
  tilt option and draw method were restored.

These checks isolate radio-disabled rendering. They do not identify the
watchdog's cause or rule out every timing-dependent native failure. The later
radio investigations and the ESP-NOW candidate are described above.

### Earlier 0.2.0 short checks

Version 0.2.0 has nine chapters and a 140-second score. Its **135 automated tests
passed**. They cover
the ten-byte protocol, duplicate/replay rejection, expiry and event coalescing,
Bluetooth ownership and cleanup, shared visual state, malformed inputs and
bounded vector geometry. Simulator previews exercise three virtual badge
models; they do not prove reception between physical badges.

The [native 0.2 benchmark](hardware-swarm-benchmark.json) exercised all nine
scenes with two synthetic peers, then a twelve-peer stress case on the actual
Spaceagon. Synthetic advertisements entered through the normal receive
callback, advertisement parser and swarm model; they were not received over
the air. The run recorded no errors, kept the EEH Logo and matrix ready,
expired the peer set to zero, and released/restarted the radio when Nearby or
foreground focus changed. Eight remote visual echoes left the outbound boost
counter at zero; a local boost advanced it to one.

These were short samples: nine or ten frames per scene with two injected
peers, and sixteen frames in the twelve-peer stress case. The two-peer samples
observed about 4.0–4.6 FPS across scenes; the twelve-peer sample observed 3.76
FPS at reduced detail. Adaptive detail varied, so these are neither fixed FPS
guarantees nor controlled comparisons between peer counts. See the raw report
for draw times, detail levels and sample sizes.

The separate [over-air check](hardware-ble-air.json) used one Spaceagon and a
test PC. The PC received thirteen matching ten-byte service-data advertisements.
Its return advertiser reported **Aborted**, with no matching over-air receive
recorded on the badge. This verifies the badge-to-PC transmit path, not the
badge's RF receive path or a two-physical-badge interaction. The
[Nearby guide](SWARM.md) explains this distinction.

These earlier short checks did not qualify 0.2.0 for long-duration stability.
The historical 0.1 soak below is not a performance result for a Nearby edition.

## Version 0.1: historical baseline

The recorded [native soak](hardware-soak.json) ran Event Horizon 0.1.0 for
370 seconds on the attached Spaceagon. It completed 2,142 rendered frames
across all eight chapters with zero recorded errors. The app remained focused,
with Spaceagon input detection, valid motion, EEH Logo and Liteloop readiness
all true. The matrix completed 148 register frames during the run.

| Native soak measurement | Result |
| --- | --- |
| Duration | 370 s |
| Rendered frames | 2,142 |
| Chapters exercised | All eight |
| Recorded errors | 0 |
| Free heap before | 1,007,136 bytes |
| Free heap after | 1,001,456 bytes |
| Lowest uncollected free heap | 808,528 bytes |
| Completed matrix frames | 148 |

This run averaged approximately 5.8 rendered frames per second across the
complete loop. That is observed native application throughput, including
scheduling, display transfer and optional expansion work. It is not a
per-scene or long-term FPS guarantee, nor a claim of constant frame timing.
The before/after heap difference is a short-run observation; it does not prove
the absence of every possible long-duration leak.

The final [native scene sweep](hardware-benchmark.json) records
short per-scene draw samples and the active detail level. Scene cost varies,
and adaptive quality can lower the rendering detail. Draw time alone does not
include the whole frame's cost.

The [automated tests](../tests/) cover score boundaries, wall-clock timing,
pause/navigation, brightness ceilings, startup-held buttons, shutdown races,
native drawing API shapes and fixed-point projection bounds. The
[gallery](gallery/README.md) and video metadata describe actual simulator
captures; desktop capture FPS is separate from the native results above.
