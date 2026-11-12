# Native validation

## Version 0.2: Nearby edition

Version 0.2 has nine chapters and a 140-second score. All **135 automated tests
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

The [final clean-boot record](hardware-final.json) confirms version 0.2.0 running
and focused, with valid Spaceagon motion, EEH Logo and matrix readiness, Nearby
ready and zero peers. Its instantaneous smoke metrics are not a sustained FPS
measurement. The historical 0.1 soak below is not a performance result for this
Nearby edition.

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
