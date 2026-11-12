"""In-memory peer preview of the ESP-NOW service using production model data.

This host-only module has no bluetooth, network or socket imports. Repeated
advertisements, queue limits and optional deterministic loss/jitter are explicit
simulation choices, not measurements of physical radio range or reliability.
No native ESP-NOW broker, Wi-Fi channel control or RF scheduler is exercised.
"""


class Air:
    def __init__(self, wire=None, drop_every=0, jitter_ms=0):
        self.wire = wire
        self.drop_every, self.jitter_ms = max(0, int(drop_every)), max(0, min(1000, int(jitter_ms)))
        self.radios, self.pending = [], []
        self.now, self.next_advert, self.deliveries, self.dropped = 0, 0, 0, 0

    def radio(self, label, owner=None, enabled=True):
        self.radios = [radio for radio in self.radios if not radio.closed]
        if len(self.radios) >= 16:
            raise ValueError("Virtual radio limit")
        radio = Radio(self, label, owner, enabled)
        self.radios.append(radio)
        return radio

    def tick(self, now):
        if type(now) is not int or now < self.now:
            raise ValueError("Invalid virtual radio clock")
        self.now = now
        if now >= self.next_advert:
            self.next_advert = now + 250
            live = [radio for radio in self.radios if radio.running]
            for sender in live:
                if sender.advert is None:
                    continue
                for receiver in live:
                    if sender is receiver:
                        continue
                    self.deliveries += 1
                    if self.drop_every and self.deliveries % self.drop_every == 0:
                        self.dropped += 1
                        continue
                    delay = self.deliveries * 37 % (self.jitter_ms + 1) if self.jitter_ms else 0
                    if len(self.pending) >= 64:
                        self.pending.pop(0)
                        self.dropped += 1
                    self.pending.append((now + delay, receiver, sender.advert))
        waiting = []
        for due, receiver, advert in self.pending:
            if due > now:
                waiting.append((due, receiver, advert))
            elif receiver.running:
                payload = self.wire.extract(advert) if self.wire else advert
                if payload is not None:
                    receiver._receive(payload)
        self.pending = waiting


class Radio:
    transport = "virtual-espnow"
    channel = 1  # Explicit synthetic readout; no real channel is queried/changed.
    physical_active = False
    cleanup_timed_out = False

    def __init__(self, air, label, owner, enabled):
        self.air, self.label, self.owner = air, label, owner
        self.enabled, self.running, self.closed = enabled is True, False, False
        self.status_code, self.status = "idle", "VIRTUAL PEER IDLE"
        self.tx_count = self.rx_count = self.dropped = 0
        self.queue, self.advert, self.last_payload, self.last_tx = [], None, None, None

    @property
    def tx(self):
        return self.tx_count

    @property
    def rx(self):
        return self.rx_count

    def start(self):
        if self.closed or not self.enabled:
            return False
        self.running = True
        self.status_code, self.status = "ready", "VIRTUAL ESP-NOW PEER READY"
        return True

    def send(self, payload, now_ms):
        if not self.running or not isinstance(payload, (bytes, bytearray, memoryview)) or len(payload) != 10:
            return False
        if type(now_ms) is not int or now_ms < 0:
            return False
        payload = bytes(payload)
        if payload == self.last_payload:
            return True
        if self.last_tx is not None and now_ms - self.last_tx < 500:
            return False
        self.advert = self.air.wire.advertisement(payload) if self.air.wire else payload
        self.last_payload, self.last_tx = payload, now_ms
        self.tx_count += 1
        return True

    def _receive(self, payload):
        self.rx_count += 1
        if len(self.queue) >= 16:
            self.queue.pop(0)
            self.dropped += 1
        self.queue.append((bytes(payload), -52))  # Synthetic RSSI, never distance.

    def poll(self):
        result, self.queue = self.queue, []
        return result

    def set_enabled(self, enabled):
        if type(enabled) is not bool or self.closed:
            return False
        self.enabled = enabled
        if enabled:
            return self.start()
        self.running, self.advert, self.queue = False, None, []
        self.status_code, self.status = "disabled", "VIRTUAL PEER OFF"
        return True

    def close(self):
        self.closed, self.running, self.advert, self.queue = True, False, None, []
        self.status_code, self.status = "closed", "VIRTUAL PEER CLOSED"


class SwarmLab:
    """Main production app plus two virtual production-protocol peers."""
    MAIN_ID = b"\x20\x7a\x51\x33"
    STAGES = ((0, "SOLO"), (6000, "ONE VIRTUAL PEER JOINS"),
              (14000, "THREE VIRTUAL BADGES"), (23000, "REMOTE BURST / CYAN"),
              (31000, "REMOTE BURST / AMBER"), (38000, "CONDUCTOR LEAVING"),
              (44000, "CONDUCTOR HANDOVER"), (50000, "LAST PEER LEAVING"),
              (56000, "SOLO RECOVERY"))

    def __init__(self, model_type, show_type, wire=None):
        self.model_type, self.show_type = model_type, show_type
        self.air = Air(wire)
        self.main_radio = None
        self.origin = None
        self.previous = None
        self.elapsed = 0
        self.stage = 0
        self.remote_events = 0
        self.peers = []
        for label, identity, hue, join, leave, burst in (
                ("CYAN", b"\x10\x62\xd3\xaf", 130, 6000, 38000, 23000),
                ("AMBER", b"\x30\xf4\xc4\x8b", 24, 14000, 50000, 31000)):
            self.peers.append({"label": label, "model": model_type(identity, hue), "show": show_type(),
                               "radio": self.air.radio(label), "join": join, "leave": leave,
                               "burst": burst, "fired": False, "last_send": -500})

    def factory(self, owner=None, enabled=True, backend=None, clock=None, event_bus=None, event_type=None):
        self.main_radio = self.air.radio("MAIN", owner, enabled)
        return self.main_radio

    def begin(self, now):
        if self.origin is None:
            self.origin, self.previous = now, now

    def advance(self, now, active=True):
        if active:
            self.begin(now)
        self.elapsed = max(0, now - self.origin) if self.origin is not None else 0
        delta = max(0, now - self.previous) if self.previous is not None else 0
        self.previous = now
        self.stage = max(index for index, (at, label) in enumerate(self.STAGES) if self.elapsed >= at)
        for peer in self.peers:
            peer["show"].advance(delta)
            present = self.origin is not None and peer["join"] <= self.elapsed < peer["leave"]
            radio, model, show = peer["radio"], peer["model"], peer["show"]
            if present and not radio.running:
                radio.start()
            elif not present and radio.running:
                radio.set_enabled(False)
            if present and not peer["fired"] and self.elapsed >= peer["burst"]:
                model.burst(now)
                show.burst()
                peer["fired"] = True
            if present and now - peer["last_send"] >= 500:
                frame = dict(show.frame(), paused=show.paused)
                radio.send(model.packet(frame, now), now)
                peer["last_send"] = now
        self.air.tick(now)
        for peer in self.peers:
            if not peer["radio"].running:
                continue
            for payload, rssi in peer["radio"].poll()[:4]:
                peer["model"].receive(payload, now, rssi)
            if peer["model"].consume_burst(now):
                peer["show"].burst()  # Echo is deliberately not model.burst().
                self.remote_events += 1

    @property
    def label(self):
        return self.STAGES[self.stage][1]

    def snapshot(self, now):
        result = []
        for peer in self.peers:
            frame = dict(peer["show"].frame(), paused=peer["show"].paused)
            view = peer["model"].view(frame, now)
            result.append({"label": peer["label"], "advertising": peer["radio"].running,
                           "count": view["count"], "role": view["role"],
                           "tx": peer["radio"].tx, "rx": peer["radio"].rx})
        return {"synthetic_radio": True, "physical_multibadge_test": False,
                "reference_transport": "Official firmware ESP-NOW broker",
                "synthetic_channel": 1, "real_radio_adapter_used": False,
                "native_radio_scheduler_exercised": False,
                "label": self.label, "elapsed_ms": self.elapsed, "peers": result,
                "dropped": self.air.dropped, "remote_echoes": self.remote_events}

    def close(self):
        for radio in self.air.radios:
            radio.close()
        self.air.pending = []
