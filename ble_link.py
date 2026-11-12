"""Exclusive, bounded BLE advertisement transport for nearby Event Horizon.

Uses the existing MicroPython BLE stack, with no Wi-Fi or channel changes.
An already-active singleton belongs to someone else and is left untouched.
Protocol interpretation and peer identity are deliberately outside this module.
"""

SERVICE_UUID = "8dd8332c-6329-45dc-a01b-d0dd6688e1f0"
# BLE encodes the entire128-bit UUID least-significant byte first. This is
# UUID.bytes[::-1], NOT Python UUID.bytes_le / Windows Guid.ToByteArray().
SERVICE_UUID_LE = b"\xf0\xe1\x88\x66\xdd\xd0\x1b\xa0\xdc\x45\x29\x63\x2c\x33\xd8\x8d"
PAYLOAD_SIZE = 10
MAX_QUEUE = 16
MIN_UPDATE_MS = 500
ADVERT_INTERVAL_US = 250000
SCAN_INTERVAL_US = 240000
SCAN_WINDOW_US = 40000
ADV_PREFIX = b"\x02\x01\x06\x1b\x21" + SERVICE_UUID_LE
_SCAN_RESULT = 5
_SCAN_DONE = 6
_OWNER = None
_MESSAGES = {"idle": "NEARBY IDLE", "disabled": "NEARBY OFF", "ready": "NEARBY READY",
             "busy": "BLUETOOTH IN USE", "unavailable": "BLUETOOTH UNAVAILABLE",
             "error": "NEARBY RADIO ERROR", "closed": "NEARBY CLOSED"}


def advertisement(payload):
    """A legacy31-byte packet: Flags plus one128-bit service-data section."""
    if not isinstance(payload, (bytes, bytearray, memoryview)) or len(payload) != PAYLOAD_SIZE:
        raise ValueError("Nearby payload must contain exactly10 bytes")
    payload = bytes(payload)
    if len(payload) != PAYLOAD_SIZE:
        raise ValueError("Nearby payload must contain exactly10 bytes")
    return ADV_PREFIX + payload


def extract(data):
    """Copy only matching service data from a bounded legacy advertisement.

    A broadcaster may omit Flags, so a28-byte service-data-only packet is also
    valid. Malformed lengths, oversized/extended frames and other UUIDs fail
    closed. The caller never retains a transient BLE memoryview.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)) or not 28 <= len(data) <= 31:
        return None
    at, end, found = 0, len(data), None
    while at < end:
        length = data[at]
        if length == 0:
            # Only zero padding may follow a terminal empty AD field.
            return found if all(value == 0 for value in data[at:]) else None
        stop = at + length + 1
        if length < 1 or stop > end:
            return None
        if data[at + 1] == 0x21 and length == 27:
            matches = True
            for index in range(16):
                if data[at + 2 + index] != SERVICE_UUID_LE[index]:
                    matches = False
                    break
            if matches:
                if found is not None:
                    return None
                found = bytes(data[at + 18:stop])
                if len(found) != PAYLOAD_SIZE:
                    return None
        at = stop
    return found


class NearbyRadio:
    """Lazy BLE owner; close is terminal, disable/re-enable is reversible.

    backend is an optional BLE-like instance or factory for deterministic tests.
    poll returns at most16(payload_bytes, RSSI_or_None) tuples. TX counters count
    advertisement updates; RX counters count matching received advertisements.
    No names, addresses, exceptions or packet contents are logged.
    """
    def __init__(self, owner=None, enabled=True, backend=None):
        self.owner, self.enabled, self._backend = owner, enabled is True, backend
        self._ble = None
        self._claimed = self._running = self._closed = False
        self._queue = []
        self._handler = self._on_irq
        self._scan_restart = False
        self._last_payload = None
        self._last_tx = None
        self.tx_count = self.rx_count = self.dropped = 0
        self.status_code = "idle" if self.enabled else "disabled"
        self.status = _MESSAGES[self.status_code]

    @property
    def running(self):
        return self._running

    @property
    def tx(self):
        return self.tx_count

    @property
    def rx(self):
        return self.rx_count

    def _status(self, code):
        self.status_code, self.status = code, _MESSAGES[code]

    def start(self):
        global _OWNER
        if self._closed:
            self._status("closed")
            return False
        if not self.enabled:
            self._status("disabled")
            return False
        if self._running:
            return True
        if _OWNER is not None and _OWNER is not self:
            self._status("busy")
            return False
        try:
            if self._backend is None:
                import bluetooth
                ble = bluetooth.BLE()
            elif hasattr(self._backend, "active"):
                ble = self._backend
            else:
                ble = self._backend()
        except ImportError:
            self._status("unavailable")
            return False
        except Exception:
            self._status("error")
            return False
        try:
            # irq() has no getter in the pinned firmware. Never replace an
            # unknown active radio's callback, advertisements or scanner.
            if ble.active():
                self._status("busy")
                return False
            _OWNER = self
            self._ble, self._claimed = ble, True
            ble.active(True)
            ble.irq(self._handler)
            self._running = True
            ble.gap_scan(0, SCAN_INTERVAL_US, SCAN_WINDOW_US, False)
            self._scan_restart = False
            self._status("ready")
            return True
        except Exception:
            self._release()
            self._status("error")
            return False

    def send(self, payload, now_ms):
        if (not self._running or not isinstance(payload, (bytes, bytearray, memoryview))
                or len(payload) != PAYLOAD_SIZE or isinstance(now_ms, bool)
                or not isinstance(now_ms, (int, float)) or not 0 <= now_ms <= 9007199254740991):
            return False
        try:
            payload = bytes(payload)
        except (TypeError, ValueError):
            return False
        if len(payload) != PAYLOAD_SIZE:
            return False
        if payload == self._last_payload:
            return True
        now_ms = int(now_ms)
        if self._last_tx is not None and now_ms - self._last_tx < MIN_UPDATE_MS:
            return False
        try:
            self._ble.gap_advertise(ADVERT_INTERVAL_US, advertisement(payload), connectable=False)
            self._last_payload, self._last_tx = payload, now_ms
            self.tx_count += 1
            return True
        except Exception:
            self._release()
            self._status("error")
            return False

    def _on_irq(self, event, data):
        if not self._running or self._closed:
            return
        if event == _SCAN_DONE:
            self._scan_restart = True
            return
        if event != _SCAN_RESULT:
            return
        try:
            if len(data) != 5:
                return
            addr_type, addr, adv_type, rssi, adv_data = data
            if adv_type not in (0, 2, 3):
                return
            payload = extract(adv_data)
            if payload is None:
                return
            rssi = rssi if type(rssi) is int and -127 <= rssi <= 20 else None
            self.rx_count += 1
            if len(self._queue) >= MAX_QUEUE:
                self._queue.pop(0)
                self.dropped += 1
            self._queue.append((payload, rssi))
        except Exception:
            # A malformed peer or allocation failure must not make MicroPython
            # disable the callback by escaping an exception from this handler.
            self.dropped += 1

    def poll(self):
        if self._running and self._scan_restart:
            self._scan_restart = False
            try:
                self._ble.gap_scan(0, SCAN_INTERVAL_US, SCAN_WINDOW_US, False)
            except Exception:
                self._release()
                self._status("error")
        result, self._queue = self._queue, []
        return result

    def _release(self):
        global _OWNER
        self._running = False
        ble, claimed = self._ble, self._claimed
        self._ble, self._claimed = None, False
        self._scan_restart = False
        self._queue = []
        self._last_payload = self._last_tx = None
        if claimed and ble is not None:
            # Each step is independent: a failing stop must not skip clearing
            # our IRQ or restoring the originally inactive controller state.
            for operation in (lambda: ble.gap_scan(None), lambda: ble.gap_advertise(None),
                              lambda: ble.irq(None), lambda: ble.active(False)):
                try:
                    operation()
                except Exception:
                    pass
        if _OWNER is self:
            _OWNER = None

    def set_enabled(self, enabled):
        if not isinstance(enabled, bool) or self._closed:
            return False
        self.enabled = enabled
        if enabled:
            return self.start()
        self._release()
        self._status("disabled")
        return True

    def close(self):
        if not self._closed:
            self._closed = True
            self._release()
        self._status("closed")
