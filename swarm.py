"""Bounded anonymous visual swarm state; no radio, hardware or remote commands.

Version1 uses ten service-data bytes. Peer locations are artistic hashes of
ephemeral session IDs; they do not describe physical distance or bearing.
"""
import binascii
import math
import os

SCORE_MS = 140000
TTL_MS = 6000
MAX_PEERS = 12
MAX_HISTORY = 24
HISTORY_MS = 30000
EVENT_MS = 500
PULSE_MS = 1500
TAU = 2 * math.pi


def _time(value):
    return type(value) is int and 0 <= value <= 9007199254740991


def _hex(value):
    return binascii.hexlify(value).decode()


def _colour(hue):
    value = hue * 6 / 256
    sector, fraction = int(value), value % 1
    low, down, up = 51, int(255 * (1 - .8 * fraction)), int(255 * (.2 + .8 * fraction))
    return ((255, up, low), (down, 255, low), (low, 255, up),
            (low, down, 255), (up, low, 255), (255, low, down))[sector % 6]


def _point(node):
    seed = (node[0] << 24) | (node[1] << 16) | (node[2] << 8) | node[3]
    angle = (seed % 997) * TAU / 997
    radius = .36 + ((seed >> 8) & 255) * .5 / 255
    return math.cos(angle) * radius, math.sin(angle) * radius


def _fade(now, started):
    return max(0, 1 - (now - started) / PULSE_MS) if started is not None else 0


def _local(frame):
    if not isinstance(frame, dict):
        raise ValueError("Invalid local swarm frame")
    position, paused = frame.get("time_ms"), frame.get("paused", False)
    if type(position) is not int or not 0 <= position < SCORE_MS or type(paused) is not bool:
        raise ValueError("Invalid local swarm frame")
    return position, paused


class Swarm:
    def __init__(self, node_id=None, hue=None):
        node_id = os.urandom(4) if node_id is None else node_id
        if not isinstance(node_id, bytes) or len(node_id) != 4:
            raise ValueError("Swarm session ID must be four bytes")
        if hue is None:
            hue = node_id[0] ^ node_id[1] ^ node_id[2] ^ node_id[3]
        if type(hue) is not int or not 0 <= hue <= 255:
            raise ValueError("Invalid swarm hue")
        self.node_id, self.hue = node_id, hue
        self._seq, self._burst = 255, 0
        self._now = 0
        self._peers = {}
        self._history = {}
        self._pending_at = None
        self._local_burst_at = None

    def clear(self):
        """Forget remote state on radio/focus loss; retain this session's wire counters."""
        self._peers.clear()
        self._history.clear()
        self._pending_at = None

    def _clock(self, now):
        if not _time(now) or now < self._now:
            return False
        self._now = now
        for node in tuple(self._peers):
            if now - self._peers[node]["seen"] >= TTL_MS:
                del self._peers[node]
        for node in tuple(self._history):
            if node not in self._peers and now - self._history[node][1] >= HISTORY_MS:
                del self._history[node]
        return True

    def _remember(self, node, sequence, now):
        if node not in self._history and len(self._history) >= MAX_HISTORY:
            unused = [key for key in self._history if key not in self._peers]
            if unused:
                del self._history[min(unused, key=lambda key: self._history[key][1])]
        self._history[node] = (sequence, now)

    def packet(self, frame, now):
        position, paused = _local(frame)
        if not self._clock(now):
            raise ValueError("Invalid swarm clock")
        self._seq = (self._seq + 1) & 255
        units = position // 8
        return bytes((0x11 if paused else 0x10,)) + self.node_id + bytes(
            (self._seq, self._burst, units >> 8, units & 255, self.hue))

    def receive(self, payload, now_ms, rssi=None):
        if not self._clock(now_ms):
            return False
        if not isinstance(payload, (bytes, bytearray)) or len(payload) != 10 or payload[0] not in (0x10, 0x11):
            return False
        node = bytes(payload[1:5])
        units = (payload[7] << 8) | payload[8]
        if node == self.node_id or units * 8 >= SCORE_MS:
            return False
        sequence, counter = payload[5], payload[6]
        history = self._history.get(node)
        if history is not None and not 1 <= ((sequence - history[0]) & 255) <= 127:
            return False
        peer = self._peers.get(node)
        if peer is None:
            if len(self._peers) >= MAX_PEERS:
                return False
            x, y = _point(node)
            peer = {"joined": now_ms, "event": None, "last_event": None,
                    "counter": counter, "x": x, "y": y}
            self._peers[node] = peer
        else:
            advanced = (counter - peer["counter"]) & 255
            if 1 <= advanced <= 127:
                # Store even rate-limited forward counters so their repeat
                # cannot become a delayed echo. A backwards counter cannot
                # rewind this baseline and turn an old event into a new one.
                peer["counter"] = counter
                if peer["last_event"] is None or now_ms - peer["last_event"] >= EVENT_MS:
                    peer["last_event"] = peer["event"] = now_ms
                    self._pending_at = now_ms
        peer.update(seen=now_ms, position=units * 8, paused=payload[0] == 0x11, hue=payload[9])
        self._remember(node, sequence, now_ms)
        return True

    def burst(self, now):
        if not self._clock(now):
            return False
        self._burst = (self._burst + 1) & 255
        self._local_burst_at = now
        return True

    def consume_burst(self, now):
        if not self._clock(now):
            return False
        started, self._pending_at = self._pending_at, None
        return started is not None and now - started <= PULSE_MS

    def view(self, frame, now):
        position, paused = _local(frame)
        if not self._clock(now):
            now = self._now
        candidates = [(self.node_id, position, self.hue)] if not paused else []
        for node, peer in self._peers.items():
            if not peer["paused"]:
                predicted = (peer["position"] + now - peer["seen"]) % SCORE_MS
                candidates.append((node, predicted, peer["hue"]))
        conductor = min(candidates, key=lambda row: row[0]) if candidates else None
        leader_id, shared, hue = conductor if conductor is not None else (None, position, self.hue)
        phase = (shared % 500) / 500
        pulse = (1 + math.cos(phase * TAU)) / 2
        result, joined, energy = [], 0, _fade(now, self._local_burst_at)
        for node in sorted(self._peers):
            peer = self._peers[node]
            age = now - peer["seen"]
            predicted = (peer["position"] + (0 if peer["paused"] else age)) % SCORE_MS
            peer_phase = (predicted % 500) / 500
            arrival, burst = _fade(now, peer["joined"]), _fade(now, peer["event"])
            strength = max(0, min(1, 1 - age / TTL_MS))
            joined, energy = max(joined, arrival), max(energy, burst)
            result.append({"id": _hex(node), "x": peer["x"], "y": peer["y"],
                           "colour": _colour(peer["hue"]), "hue": peer["hue"], "phase": peer_phase,
                           "pulse": (1 + math.cos(peer_phase * TAU)) / 2, "joined": arrival,
                           "energy": strength, "burst": burst, "age_ms": age,
                           "paused": peer["paused"], "leader": node == leader_id})
        own_leader = leader_id == self.node_id
        role = "paused" if conductor is None else "solo" if not result and own_leader else "conductor" if own_leader else "follower"
        return {"peers": result, "count": len(result), "phase": phase, "pulse": pulse,
                "joined": joined, "energy": energy, "self_hue": self.hue, "colour": _colour(hue),
                "leader": own_leader, "leader_id": _hex(leader_id) if leader_id is not None else None,
                "role": role}
