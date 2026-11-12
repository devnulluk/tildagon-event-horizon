"""Fail-closed adapter for Kristian Hentschel's Liteloop matrix hexpansion.

Only the exact CAFE:54E1 / Liteloop header is supported. Its monochrome LEDs
have a fixed colour: RGB colour is not available. No GPIO, port-power,
bootloader, firmware, EEPROM, or SD-card writes are performed here.

Protocol and grid: manufacturer companion app b7202429, board_liteloop.py;
firmware 873f484f, firmware/shared/core_registers.h.
https://github.com/kristianhentschel/tildagon-matrix-hexpansion-app
"""

import asyncio

# Physical grid derived from the manufacturer's MIT-licensed companion app.
# Copyright (c)2026 Kristian Hentschel.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

VID, PID, NAME = 0xCAFE, 0x54E1, "Liteloop"
ADDRESS, DIRECT_REGISTER, LED_COUNT = 0x20, 0x50, 156
WIDTH, HEIGHT = 18, 9

# Physical LED numbers in display order, not wiring order. The manufacturer's
# top row is shorter; the right-hand six columns have their own wiring order.
GRID = (
    -1, -1, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, -1, -1, -1,
    12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 114, 115, 116, 117, 118, 119,
    24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 126, 127, 128, 129, 130, 131,
    36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 138, 139, 140, 141, 142, 143,
    48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 150, 151, 152, 153, 154, 155,
    60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 108, 109, 110, 111, 112, 113,
    72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 120, 121, 122, 123, 124, 125,
    84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 132, 133, 134, 135, 136, 137,
    96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 144, 145, 146, 147, 148, 149,
)


def matches_header(header):
    return (getattr(header, "vid", None) == VID
            and getattr(header, "pid", None) == PID
            and getattr(header, "friendly_name", None) == NAME)


def _dict(value):
    return value if isinstance(value, dict) else {}


class MatrixDisplay:
    """Bounded transport for one exact Liteloop header.

    A procedural owner queues complete PWM frames. One background coroutine
    flushes at most24 one-byte writes per pass, yielding every8 successful
    bytes and rechecking physical attachment/ownership before each write.
    Each native transaction has a bounded~500ms fault timeout rather than
    the~16seconds of a single bulk transfer. No retry occurs within a pass.
    The processor can retain its last frame if the owner is cancelled.
    """

    def __init__(self, config=None, backend=None):
        if backend is None:
            from .expansions import FirmwareBackend
            backend = FirmwareBackend()
        self.backend = backend
        config = _dict(config)
        self.setting = config.get("matrix", {})
        self.ready = False
        self.status = "MATRIX NOT CONNECTED"
        self.slot = None
        self.last_mode = None
        self.frames_written = 0
        self.displayed_mode = None
        self._bus = None
        self._header = None
        self._last_frame = None
        self._last_write_ms = None
        self._retry_at = 0
        self._closed = False
        self._flushing = False
        self._goal_pending = False
        self._goal_peak = None
        self._clock_ms = 0
        self._actual = bytearray(LED_COUNT)
        self._known = bytearray(LED_COUNT)
        self._cursor = 1
        self._phase = 0
        self._byte = bytearray(1)
        self._packet = bytearray(LED_COUNT + 1)
        self._packet[0] = 3
        self._zero = bytes(LED_COUNT)
        self._peak = 38
        self.refresh(0)

    def _drop(self, status):
        self.ready = False
        self.status = status
        self._bus = None
        self._header = None
        self.slot = None
        self._last_frame = None
        self.last_mode = None
        self.displayed_mode = None
        self._goal_pending = False

    def refresh(self, now_ms):
        if self._closed:
            return False
        setting = self.setting
        if setting is False or (isinstance(setting, dict) and setting.get("enabled") is False):
            self._drop("MATRIX OFF")
            return False
        if not isinstance(setting, dict):
            self._drop("MATRIX CONFIG INVALID")
            return False
        slot = setting.get("slot")
        level = setting.get("brightness", 0.15)
        if (setting.get("type", NAME) != NAME
                or (slot is not None and (isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 6))
                or isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 <= level <= 1):
            self._drop("MATRIX CONFIG INVALID")
            return False
        self._peak = int(level * 255)
        try:
            drivers, attached, running = self.backend.snapshot()
            headers = self.backend.headers()
            candidates = [number for number in attached
                          if isinstance(number, int) and not isinstance(number, bool)
                          and 1 <= number <= 6 and (slot is None or number == slot)
                          and matches_header(headers.get(number))]
        except Exception:
            self._drop("MATRIX UNAVAILABLE")
            return False
        if len(candidates) != 1:
            self._drop("MATRIX CHOOSE SLOT" if len(candidates) > 1 else "MATRIX NOT CONNECTED")
            return False
        slot = candidates[0]
        if slot in drivers:
            self._drop("MATRIX SLOT IN USE")
            return False
        if any(app.__class__.__name__ == "MatrixHexpansionApp" for app in running):
            self._drop("CLOSE MATRIX APP")
            return False
        header = headers[slot]
        if self._bus is not None and self.slot == slot and self._header is header:
            return True
        if now_ms < self._retry_at:
            return False
        try:
            self._bus = self.backend.matrix_i2c(slot)
        except Exception:
            self._drop("MATRIX DRIVER ERROR")
            self._retry_at = now_ms + 2000
            return False
        self._header = header
        self.slot = slot
        self.ready = True
        self.status = "MATRIX READY"
        self._last_frame = None
        self._last_write_ms = None
        self._actual[:] = self._zero
        self._known[:] = self._zero
        self._cursor = 1
        self._phase = 0
        return True


    @property
    def pending(self):
        return self._goal_pending and not self._closed

    def _write_byte(self, register, value):
        self._byte[0] = value
        result = self._bus.writeto_mem(ADDRESS, register, self._byte)
        if result is not None and result != 1:
            raise OSError("Incomplete matrix register write")

    async def flush(self):
        """Drain at most24 changes, coalescing semantic goals at every yield.

        No task is created here. A unique owner task serializes calls. Failed
        writes abort the pass immediately and block reinitialization for2s.
        Initial loading holds constant-zero mode until the entire PWM buffer
        is known. LED0 remains zero until PWM mode is enabled, avoiding a
        full-matrix flash from the shared constant-brightness/data0 register.
        """
        if self._closed or self._flushing or not self._goal_pending:
            return 0
        self._flushing = True
        writes = 0
        try:
            while writes < 24 and self._goal_pending and not self._closed:
                if not self.refresh(self._clock_ms):
                    break
                try:
                    if self._phase == 0:
                        self._write_byte(DIRECT_REGISTER + 1, 0)
                        self._actual[0], self._known[0] = 0, 1
                        self._phase = 1
                    elif self._phase == 1:
                        self._write_byte(DIRECT_REGISTER, 1)
                        self._phase = 2
                    else:
                        index = None
                        # During initial loading data0 must remain zero while
                        # it controls constant mode. Other bytes can load.
                        start, count = (1, LED_COUNT - 1) if self._phase == 2 else (0, LED_COUNT)
                        for offset in range(count):
                            candidate = start + (self._cursor - start + offset) % count
                            if (not self._known[candidate]
                                    or self._actual[candidate] != self._packet[candidate + 1]):
                                index = candidate
                                break
                        if index is None:
                            if self._phase == 2:
                                self._write_byte(DIRECT_REGISTER, 3)
                                self._phase = 3
                                self._cursor = 0
                            else:
                                self._goal_pending = False
                                self.frames_written += 1
                                self.displayed_mode = self.last_mode
                                break
                        else:
                            value = self._packet[index + 1]
                            self._write_byte(DIRECT_REGISTER + 1 + index, value)
                            self._actual[index], self._known[index] = value, 1
                            self._cursor = index + 1
                except Exception:
                    self._drop("MATRIX I2C ERROR")
                    self._retry_at = self._clock_ms + 2000
                    break
                writes += 1
                # Yield in small groups: one LCD draw between every byte can
                # starve a156-byte image for many seconds. A failed write still
                # aborts immediately, so a fault never waits for the group.
                if writes % 8 == 0:
                    await asyncio.sleep(0)
        finally:
            self._flushing = False
        return writes

    def close(self):
        if self._closed:
            return
        # Never block scheduler shutdown or touch hardware after ownership
        # changes. The external processor keeps its last complete/partial
        # frame, just as it does when the manufacturer's app is stopped.
        self._closed = True
        self._drop("MATRIX OFF")
