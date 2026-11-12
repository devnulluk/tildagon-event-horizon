# Nearby badges: Gravitational Choir

Event Horizon's nine-chapter, 140-second show includes a twenty-second
constellation chapter. Version 0.2.1 uses **ESP-NOW over the 2.4 GHz Wi-Fi
radio**, replacing the withdrawn Bluetooth beta. No internet, router, pairing,
account or phone application is required by this exchange.

**Participating badges must run a matching release on the same current
2.4 GHz channel.** The app observes that channel; it never changes it. The
current native endurance status is recorded in [VALIDATION.md](VALIDATION.md).

**RF verification limit:** an exchange between two physical ESP-NOW badges has
not been verified. Multi-peer native fixtures and the film use synthetic peers.

## Try it

1. Install the same tested ESP-NOW release on every participating badge. The
   old Bluetooth beta cannot join an ESP-NOW group.
2. Leave **Nearby** on in the sixth settings row. Hold A to open settings;
   use A/D to select a row and B/E to change it, then C to close.
3. Compare the **CH** value in the HUD or Gravitational Choir page on every
   badge. They must match. `CH ?` means the current channel is unknown.
4. Select **Gravitational Choir**, or let the show reach it at 72 seconds.
5. Briefly press A, or move the Spaceagon joystick up, to create a nova event.
   A received event adds a response without being broadcast as another local
   boost.

The **same SSID is not enough**: badges using different access points can be
on different channels. A connected station follows its access point's current
channel, and roaming can change that channel. The app does not disconnect,
change credentials or hop channels to make a group match. ESP-NOW itself does
not need an access point, but all participants still need the same channel.

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

## Status and ownership

The constellation page and HUD show the observed channel, peer count and
conductor/follower role; an all-paused group is labelled paused. **Searching /
CH n** means Nearby is ready but its peer view is empty. It does not prove
another badge is reachable on that channel.

| Message | Meaning |
| --- | --- |
| Nearby off | This app's Nearby setting is disabled |
| Nearby ESP-NOW ready | The selected adapter started successfully |
| ESP-NOW in use | An already-active raw singleton is left untouched |
| ESP-NOW unavailable | The firmware does not expose a supported path |
| ESP-NOW radio error | Subscription, send, receive or cleanup failed |

The adapter prefers the firmware's **shared ESP-NOW broker** where available.
It subscribes through the service and sends through its existing API;
it does not create another receiver or replace a shared callback. Off, loss of
foreground focus and exit remove only this app's exact wrapped subscription,
stop its sends and clear its peer view. Other listeners and the service remain
running.

When the broker is **unavailable**, the adapter can claim the raw
ESP-NOW singleton only when it is inactive. An already-active singleton is
refused. After that exclusive claim, a stale receive handler is cleared and
the app uses polling rather than registering its own receiving callback.
The raw receive buffer is 2,048 bytes and at most sixteen nonwaiting reads are
examined per update. Raw receive RSSI is reported as unknown. Closing stops
only the raw instance this adapter claimed; failed cleanup retains ownership
so a later close can retry.

Neither path writes a channel, SSID, credentials or connect/disconnect request.
The firmware broker may activate its station interface and keep Wi-Fi
awake while listeners exist, then reconcile its normal power policy. The raw
fallback also activates STA if required, but **never deactivates STA on exit**.
It temporarily disables station power saving only when the old value can be
read, and restores that value only if it still matches what this app wrote.
An intervening power-mode change is preserved. The previous raw receive-buffer
setting is restored on the same conditional basis.

Nearby off therefore does **not** mean all Wi-Fi is powered down. There is no
Bluetooth activation, firmware modification, CPU-speed change or watchdog
change in this transport.

## Version 1 application envelope

The ten-byte visual payload retains its previous byte layout. ESP-NOW carries
it in the same **31-byte UUID-prefixed application envelope**; it is now data
in an ESP-NOW message, not an over-air Bluetooth advertisement. Keeping the
codec unchanged does not make the two radio transports interoperable.

The envelope starts with `02 01 06 1b 21`, followed by the application UUID
`8dd8332c-6329-45dc-a01b-d0dd6688e1f0` encoded least-significant byte first,
then these ten bytes:

| Byte offset | Field |
| --- | --- |
| 0 | `0x10` for running or `0x11` for paused; version 1 |
| 1–4 | Four random bytes identifying this app session |
| 5 | Application-state update sequence counter, modulo 256 |
| 6 | Local boost-event counter, modulo 256 |
| 7–8 | Position in the 140-second score, in eight-millisecond units, big-endian |
| 9 | Colour hue, 0–255 |

Broadcast sends use `sync=False`, no more than once per 500 milliseconds. A
successful return and TX increment mean the stack accepted the send; they are
not an over-air receipt or acknowledgement. A repeated unchanged request
within that interval does not send another packet. `sync=False` skips waiting
for acknowledgement, but native queue-pressure handling can still delay a
call; it is not a guarantee of instantaneous execution.

Only exact matching 31-byte envelopes reach this app's model. The broker path
copies matching messages into a sixteen-entry FIFO, dropping the oldest when
full. The raw path examines at most sixteen pending messages per update and
ignores other applications' packets. The model rejects self messages,
duplicates, backwards sequence updates and invalid positions; it bounds its
state to twelve peers and twenty-four replay-history entries. These limits do
not bound every buffer or peer table inside the firmware's shared/native
radio implementation.

Remote boosts are rate-limited and do not advance the local outbound boost
counter, so peers cannot amplify one event indefinitely. Packets can be lost
or coalesced. This is unauthenticated visual signalling, not reliable messaging.

The payload contains no name, account, call data, credentials or physical
location. Session IDs are random application identifiers rather than persistent
badge identities. The app does not read received MAC addresses or persist a
peer list. Ordinary Wi-Fi device addresses remain observable to the radio and
firmware, which may maintain their own receive tables; this is not a claim of
radio untrackability or zero address retention by the operating system.

## Demonstrations and verification scope

The [sixty-second preview](gallery/swarm-preview.mp4),
[GIF](gallery/swarm-preview.gif) and
[contact sheet](gallery/swarm-preview-contact-sheet.png) use the production
application's encoder, model and renderer with three **virtual** badges and
in-memory packet delivery. Their matching channel is synthetic. The substitute
adapter does not exercise physical ESP-NOW, channel control or native radio
scheduling. Peer positions and density fixtures are explicitly synthetic.
These captures are not photographs, RF-range measurements or physical
frame-rate evidence.

The [native full-show soak](hardware-espnow-soak-0.2.1.json) used the normal
booted system's **shared broker on channel 6**. It completed 679 seconds and
3,688 frames across all nine chapters with zero recorded errors. The separate
[raw API qualification](hardware-espnow-qualification.json) accepted one transmit
request on channel 6 and confirmed the owned raw instance inactive after close.
That API check was run in a bare REPL; broker visibility there did not establish
whether the full booted OS provided the service. Neither check proves another
physical badge received a packet. See [VALIDATION.md](VALIDATION.md) for the
measurements and their limits.

The [final native peer fixture](hardware-espnow-stress-0.2.1.json) checked the
latest status-text background across all nine scenes and with twelve synthetic
peers, including expiry, echo suppression, off/focus subscription removal and
shared-radio preservation. It used the real app broker callback on the badge,
not physical over-air messages.

The earlier badge-to-PC Bluetooth advertising observation is historical; it
proves neither ESP-NOW reception nor an ESP-NOW exchange between two physical
badges. Do not infer either from the simulator film.
