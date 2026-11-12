# Native validation

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
