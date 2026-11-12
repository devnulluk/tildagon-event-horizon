# Nearby badges: Gravitational Choir

Event Horizon 0.2 adds a twenty-second constellation chapter to the
140-second show. Nearby mode discovers other copies through connectionless
Bluetooth Low Energy advertisements. No pairing, Wi-Fi network, router,
account, phone application or cloud service is required.

## Try it

1. Launch Event Horizon 0.2 on the participating badges.
2. Leave **Nearby** on in the sixth settings row. Hold A to open settings;
   use A/D to select a row and B/E to change it, then C to close.
3. Navigate to **Gravitational Choir**, or let the show reach it at 72 seconds.
4. Briefly press A, or move the Spaceagon joystick up, to send a nova event.
   Watch another badge's constellation, chapter and lights respond.

The controls still work when Nearby is off or no other badge is present. All
light effects respect the independent ring, EEH Logo and Liteloop brightness
settings, including zero. Optional expansions are not required.

Each badge retains its own chapter, pause and brightness controls. Within its
current peer view, the lowest unpaused temporary session ID supplies the shared
beat sample and colour. This is not a command to seek another badge's chapter
or change its settings. Paused badges remain visible but do not compete to
conduct. A changed or incomplete peer view can select a different conductor.

The full chapter adds coloured stars, luminous links, aurora, join ripples and
boost novas. Small overlays carry those interactions into the other chapters.
Star positions are deterministic artistic placements; they do not show physical
distance, direction, RSSI or a map. The app represents at most twelve recent
peers, with reduced visual detail at lower quality. A peer disappears after
six seconds without a fresh accepted message.

## Status and radio lifetime

With peers present, the constellation chapter and HUD show their count and
the conductor/follower role; an all-paused group is labelled paused.
**Searching for badges** means the radio is running with an empty peer view.
Other messages include:

| Message | Meaning |
| --- | --- |
| Nearby off | The saved Nearby setting is disabled |
| Bluetooth in use | An existing active Bluetooth owner is left untouched |
| Bluetooth unavailable | The firmware does not expose the required BLE module |
| Nearby radio error | The current start, scan or advertisement attempt failed |

The visual show remains usable in these cases. Nearby opens lazily, retries
after a failure, and releases only the radio it acquired. Disabling it, losing
foreground focus or exiting stops its scanning/advertising and clears remote
state. Returning to the show can reopen Nearby if its saved setting is on.

## Version 1 advertisement format

The application service UUID is
`8dd8332c-6329-45dc-a01b-d0dd6688e1f0`. The legacy advertisement contains Flags
and one 128-bit Service Data field (AD type `0x21`), totalling 31 bytes. The
service UUID is encoded least-significant byte first, followed by this
ten-byte application payload:

| Byte offset | Field |
| --- | --- |
| 0 | `0x10` for running or `0x11` for paused; version 1 |
| 1–4 | Four random bytes identifying this app session |
| 5 | Advertisement-update sequence counter, modulo 256 |
| 6 | Local boost-event counter, modulo 256 |
| 7–8 | Position in the 140-second score, in eight-millisecond units, big-endian |
| 9 | Colour hue, 0–255 |

Advertisements repeat at a nominal 250-millisecond interval; application
updates are limited to one per 500 milliseconds. Scanning is passive, with a
40-millisecond window per 240-millisecond interval. These are configured
intervals, not promises of delivery or reception latency.

Only matching, correctly sized packets are accepted. Self messages, duplicates,
backward sequence updates and invalid positions are rejected. State is bounded
to twelve peers, twenty-four replay-history entries and a sixteen-item radio
queue. The app drains the full bounded batch of up to sixteen messages per
update, so simultaneous beacons are not silently discarded. Remote boost
events are rate-limited and are not echoed into the local outbound counter, so
two badges cannot amplify one event indefinitely. Broadcast events can be lost
or coalesced; this is visual signalling rather than reliable messaging.

The payload contains no name, account, call information, credentials or physical
location. Session IDs are random application identifiers, not persistent badge
identities. Ordinary Bluetooth controller addresses may still be observable;
this is not a claim of radio untrackability. Signalling is unauthenticated and
controls visual state only. The app does not save a peer list to disk.

## Demonstrations and verification scope

The [sixty-second preview](gallery/swarm-preview.mp4),
[GIF](gallery/swarm-preview.gif) and
[contact sheet](gallery/swarm-preview-contact-sheet.png) use the production
application with three **virtual** badge models and in-memory advertisement
delivery. They exercise the real packet encoder, receiver and model without
using physical Bluetooth. Peer positions and extra density fixtures remain
explicitly synthetic. They are not evidence of multiple physical badges,
radio range or physical frame rate.

Physical verification is recorded separately in [VALIDATION.md](VALIDATION.md).
At the initial radio check, a test PC received advertisements from one physical
Spaceagon. The PC publisher reported **Aborted**; PC-to-badge transmission was
not verified. That confirms the badge's transmit path, not a two-badge exchange
or its radio receive path.
Do not infer multi-badge RF verification from the simulator film.
