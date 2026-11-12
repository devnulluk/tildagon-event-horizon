"""A deterministic two-minute score: no frame-count-dependent animation."""
import math

BPM = 120
SCENES = (
    ("intro", "EVENT HORIZON", 8000),
    ("starflight", "01 / DEPARTURE", 16000),
    ("tunnel", "02 / HYPERSPACE", 16000),
    ("terrain", "03 / SIGNAL LOST", 16000),
    ("planet", "04 / NEW WORLDS", 16000),
    ("kaleidoscope", "05 / CRYSTAL MIND", 16000),
    ("blackhole", "06 / EVENT HORIZON", 20000),
    ("finale", "WE ARE MADE OF STARS", 12000),
)
TOTAL_MS = sum(row[2] for row in SCENES)
STARTS = tuple(sum(row[2] for row in SCENES[:index]) for index in range(len(SCENES)))
_SIN = tuple(math.sin(index * math.pi * 2 / 256) for index in range(256))


def sine(turns):
    return _SIN[int(turns * 256) & 255]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and -1e14 < value < 1e14


class Show:
    def __init__(self):
        self.position = 0
        self.paused = False
        self.burst_until = 0
        self.elapsed = 0

    def advance(self, delta_ms):
        if not finite(delta_ms) or delta_ms < 0:
            return
        delta_ms = int(delta_ms)
        self.elapsed += delta_ms
        if not self.paused:
            self.position = (self.position + delta_ms) % TOTAL_MS

    def frame(self):
        for index in range(len(SCENES) - 1, -1, -1):
            if self.position >= STARTS[index]:
                scene, title, duration = SCENES[index]
                local = self.position - STARTS[index]
                return {"scene": scene, "title": title, "index": index, "local_ms": local,
                        "phase": local / duration, "duration_ms": duration,
                        "time_ms": self.position, "elapsed_ms": self.elapsed, "beat": (self.position % 500) / 500,
                        "pulse": (1 + sine(self.position / 500 - .25)) / 2,
                        "burst": max(0, min(1, (self.burst_until - self.elapsed) / 900))}

    def select(self, index):
        self.position = STARTS[int(index) % len(SCENES)]

    def next(self, direction):
        self.select(self.frame()["index"] + (1 if direction > 0 else -1 if direction < 0 else 0))

    def toggle(self):
        self.paused = not self.paused

    def burst(self):
        self.burst_until = self.elapsed + 900


def hsv(h, saturation=1, value=1):
    h = (h % 1) * 6
    sector, fraction = int(h), h % 1
    p, q, t = value * (1-saturation), value * (1-saturation*fraction), value * (1-saturation*(1-fraction))
    colour = ((value,t,p),(q,value,p),(p,value,t),(p,q,value),(t,p,value),(value,p,q))[sector % 6]
    return tuple(int(max(0, min(1, channel)) * 255) for channel in colour)


# The live shader uses constant saturation. A tiny RGB wheel avoids building
# six unused HSV tuples for every LED and triggering frequent full collections.
_PALETTE = bytearray()
for _index in range(256):
    _PALETTE.extend(hsv(_index/256, .8, 1))
del _index


def light_frame(frame, brightness=.15, count=12):
    """Smooth spectral choreography, bounded by the user's brightness ceiling."""
    brightness = max(0, min(1, brightness)) if finite(brightness) else .15
    scene, now, pulse = frame["scene"], frame["time_ms"], frame["pulse"]
    result = []
    for index in range(count):
        orbit = .5 + .5 * sine(index/count - now/3200)
        if scene in ("intro", "planet"):
            hue, level = .53 + index/count*.13, .12 + .6*orbit + .15*pulse
        elif scene == "terrain":
            hue, level = .77 + index/count*.16, .18 + .6*orbit
        elif scene == "blackhole":
            hue, level = .035 + .08*orbit, .12 + .75*orbit
        elif scene in ("kaleidoscope", "finale"):
            hue, level = index/count + now/10000, .25 + .6*orbit
        else:
            hue, level = .51 + .4*orbit, .12 + .7*orbit + .08*pulse
        level = min(1, level + frame.get("burst", 0)*.2)
        at=(int(hue*256)&255)*3
        scale=int(brightness*level*255)
        result.append((_PALETTE[at]*scale//255,_PALETTE[at+1]*scale//255,_PALETTE[at+2]*scale//255))
    return result
