"""Choreographed light layers on recognized optional expansions."""
from .matrix import MatrixDisplay, GRID, WIDTH, HEIGHT, LED_COUNT
from .show import light_frame, sine


class DemoMatrix(MatrixDisplay):
    def queue(self, frame, brightness=.12, dark=False):
        """Queue a complete procedural goal; transfers stay in the worker."""
        now = frame["time_ms"]
        clock = frame.get("elapsed_ms", now)
        if not self.refresh(clock):
            return False
        self._clock_ms = clock
        mode = "dark" if dark else frame["scene"]
        peak = int(max(0,min(1,brightness))*255)
        if self.pending and self.last_mode == mode and self._goal_peak == peak:
            return True
        if self.last_mode == mode and self._last_write_ms is not None and 0 <= clock-self._last_write_ms < 160:
            return True
        self._packet[1:] = self._zero
        if not dark:
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    physical = GRID[y*WIDTH+x]
                    if physical < 0:
                        continue
                    dx, dy = (x-8.5)/8.5, (y-4)/4
                    radius = (dx*dx+dy*dy)**.5
                    if mode == "swarm":
                        pulse=frame["pulse"]
                        strength=max(0,1-abs(radius-(.25+.55*frame.get("beat",0)))*5)
                        strength=max(strength,.45*max(0,1-radius)*pulse)
                    elif mode == "blackhole":
                        strength = max(0,1-abs(radius-(.54+.08*sine(now/2600)))*7)
                    elif mode in ("planet","intro","finale"):
                        strength = max(0,1-radius)*(.65+.35*sine(x/18+now/3500))
                    elif mode == "terrain":
                        horizon = 4 + 2*sine(x/12+now/4000)
                        strength = max(0,1-abs(y-horizon))
                    elif mode == "kaleidoscope":
                        strength = .5+.5*sine(abs(dx)*2-abs(dy)*2+now/2000)
                        strength = strength**3
                    else:
                        strength = max(0,1-abs((radius+now/1400)%1-.5)*4)
                    self._packet[physical+1] = int(peak*strength)
        self._goal_peak, self.last_mode = peak, mode
        self._last_write_ms = clock
        self._goal_pending = True
        return True


def write_eeh(expansions, frame, brightness=.03, dark=False):
    if not expansions.eeh_ready or expansions._pixels is None:
        return False
    colours = [(0,0,0)]*expansions._count if dark else light_frame(frame,brightness,expansions._count)
    try:
        for index, colour in enumerate(colours):
            expansions._pixels[index] = colour
        expansions._pixels.write()
        return True
    except Exception:
        expansions._drop_pixels("EEH DISCONNECTED")
        expansions._dirty = True
        return False
