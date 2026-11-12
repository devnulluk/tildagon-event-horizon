"""Procedural cosmic scenes for native 240px ctx; no images or framebuffer API.

The point planet uses a rotated sphere and perspective/tangent culling. The
black hole is cinematic artwork, not a ray-traced physical simulation.
Geometry, colours and pseudo-random particle seeds are cached at import.
"""
import math
from .projector import Projector

import sys
if sys.implementation.name == "micropython":
    import micropython
else:
    class micropython:
        @staticmethod
        def native(function):
            return function

SCENES = ("blackhole", "planet", "starflight")
TAU = 2 * math.pi
_UNIT = tuple((math.cos(i * TAU / 256), math.sin(i * TAU / 256)) for i in range(256))
_SKY = tuple((.003 + .010 * i / 11, .006 + .007 * i / 11, .025 + .029 * i / 11) for i in range(12))
_STARS = tuple((((i * 83 + 19) % 222) - 111, ((i * 59 + 31) % 222) - 111) for i in range(28))
_STAR_COLOURS = ((.12, .22, .39), (.28, .42, .60), (.59, .72, .89))
_WARP = tuple((_UNIT[(i * 97 + 11) & 255][0], _UNIT[(i * 97 + 11) & 255][1],
               14 + (i * 29 % 25), (i * 137 % 997) / 997) for i in range(72))
_TILT_C, _TILT_S = math.cos(.34), math.sin(.34)
_PERSPECTIVE = 3.4
_SPHERE_SCALE = math.sqrt(_PERSPECTIVE * _PERSPECTIVE - 1) / _PERSPECTIVE
_PLANET_COLOURS = ((.025, .17, .30), (.055, .39, .52), (.10, .57, .62),
                   (.39, .94, .82), (.30, .48, .62), (.76, .95, 1.0))


def _sphere_points():
    points = []
    for row in range(1, 12):
        latitude = (row / 12 - .5) * math.pi
        y, ring = math.sin(latitude), math.cos(latitude)
        for column in range(28):
            longitude = column * TAU / 28
            # Analytic, synthetic land masses; no map, API or raster data.
            terrain = (math.sin(longitude * 2 + latitude * 3)
                       + .57 * math.cos(longitude * 3 - latitude * 5)
                       + .32 * math.sin(longitude * 5 + latitude * 2))
            material = 2 if abs(y) > .91 else 1 if terrain > .23 else 0
            points.append((ring * math.sin(longitude), y, ring * math.cos(longitude), material))
    return tuple(points)


_SPHERE = _sphere_points()
_PROJECTOR = Projector(_SPHERE)
_VIEW = (0.0, 0.0)


def set_view(x, y):
    global _VIEW
    _VIEW = (max(-1, min(1, x)), max(-1, min(1, y)))


def _level(value, default):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not -1000000 <= value <= 1000000):
        return default
    return max(0, min(1, value))


def _clock(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 <= value <= 9007199254740991):
        return 0
    return int(value)


def _circle(ctx, x, y, radius, colour):
    ctx.rgb(*colour).arc(x, y, radius, 0, TAU, False).fill()


def _background(ctx, now, detail):
    for index, colour in enumerate(_SKY):
        ctx.rgb(*colour).rectangle(-140, -140 + index * 24, 280, 24).fill()
    # Separate short paths keep the native edge cache bounded.
    for shade, colour in enumerate(_STAR_COLOURS):
        ctx.rgb(*colour)
        for index in range(shade, 28 if detail else 16, 3):
            x, y = _STARS[index]
            size = 1.3 if (index + now // 900) % 7 == 0 else .8
            ctx.rectangle(x, y, size, size)
        ctx.fill()


def _ellipse(ctx, cx, cy, rx, ry, start, count, tilt, colour, width):
    """At most65 connected vertices; tilt is a sine-like shear, not ctx state."""
    ctx.rgb(*colour)
    ctx.line_width = width
    for index in range(count + 1):
        c, s = _UNIT[((start + index) * 4) & 255]
        x, y = rx * c, ry * s
        x, y = cx + x, cy + y + x * tilt
        if index:
            ctx.line_to(x, y)
        else:
            ctx.move_to(x, y)
    ctx.stroke()


def _blackhole(ctx, now, phase, detail):
    _background(ctx, now, detail)
    pulse = _UNIT[(now // 31) & 255][1]
    tilt = -.19 + _UNIT[(now // 173) & 255][1] * .025 + _VIEW[1] * .12
    # Wide faint lens first; no translucent full-frame overdraw.
    _ellipse(ctx, 0, 2, 101, 27, 0, 64, tilt, (.085, .045, .12), 9)
    _ellipse(ctx, 0, 1, 98, 23, 0, 64, tilt, (.25, .10, .16), 5)
    _ellipse(ctx, 0, 0, 96, 20, 32, 32, tilt, (.77, .27, .16), 3.8)
    # The secondary image is bent over the dark core.
    _ellipse(ctx, 0, -1, 43, 52, 32, 32, -.035, (.27, .11, .20), 7)
    _ellipse(ctx, 0, -1, 41, 50, 32, 32, -.035, (.94, .39, .19), 2.6)
    _ellipse(ctx, 0, -1, 39.5, 48, 34, 28, -.035, (1.0, .77, .48), 1.3)
    # Foreground disk: thin white-hot core with a warmer outer trail.
    _ellipse(ctx, 0, 2, 95, 19, 0, 32, tilt, (.76, .20, .12), 7)
    _ellipse(ctx, 0, 2, 94, 18, 0, 32, tilt, (1.0, .50, .21), 3.8)
    _ellipse(ctx, 0, 2, 93, 17, 0, 32, tilt, (1.0, .88, .64), 1.5)
    # An unbroken dark horizon hides disk geometry that crosses its core.
    _circle(ctx, 0, -2, 32, (.015, .007, .025))
    _circle(ctx, 0, -2, 29.7, (.001, .002, .008))
    ctx.line_width = 1.2 + phase * .45
    ctx.rgb(1.0, .62 + pulse * .035, .32).arc(0, -2, 31.2, 0, TAU, False).stroke()
    ctx.line_width = .7
    ctx.rgb(.91, .86, .81).arc(0, -2, 33, 3.4, 5.9, False).stroke()
    # Orbiting sparks are constrained to the disk, so they cannot flash in the
    # black centre. Tangential trails imply rotation rather than a clock hand.
    count = 12 if detail else 6
    ctx.line_width = 1.25
    ctx.rgb(1.0, .77, .45)
    for index in range(count):
        angle = (now // (20 + index % 3 * 3) + index * 37) & 255
        c, s = _UNIT[angle]
        pc, ps = _UNIT[(angle - 3) & 255]
        radius = 64 + index % 4 * 8
        x, y = c * radius, 2 + s * radius * .18 + c * radius * tilt
        if x * x + (y + 2) * (y + 2) < 1200:
            continue
        ctx.move_to(pc * radius, 2 + ps * radius * .18 + pc * radius * tilt).line_to(x, y)
    ctx.stroke()


def _satellite(ctx, angle, foreground):
    c, s = _UNIT[angle]
    if (s >= 0) != foreground:
        return
    x, y = c * 99, -18 + s * 35
    _circle(ctx, x, y, 5.2, (.12, .22, .39))
    _circle(ctx, x - 1, y - 1, 3.6, (.60, .83, .94))


@micropython.native
def _planet(ctx, now, phase, detail):
    _background(ctx, now, detail)
    c, s = _UNIT[((now // 75) + int(_VIEW[0] * 32)) & 255]
    tc, ts = _UNIT[(14 + int(_VIEW[1] * 24)) & 255]
    radius = 66 + phase * 6
    tilt = .29
    orbit = (now // 33) & 255
    _ellipse(ctx, 0, 2, 104, 24, 32, 32, tilt, (.17, .22, .46), 1.3)
    _satellite(ctx, orbit, False)
    # Solid body conceals the back orbit and all far-side surface points.
    _circle(ctx, 0, -4, radius + 3.6, (.025, .12, .24))
    _circle(ctx, 0, -4, radius + 1.3, (.07, .32, .46))
    _circle(ctx, 0, -4, radius, (.004, .027, .075))
    # Each material/depth path is periodically flushed at24 rectangles
    # (96edges). No per-frame point cloud or sort list is allocated.
    points, counts = _PROJECTOR.project(c, s, tc, ts, radius, detail)
    for bucket, colour in enumerate(_PLANET_COLOURS):
        ctx.rgb(*colour)
        pending = 0
        base = bucket * 924
        for point in range(counts[bucket]):
            offset = base + point * 3
            size = points[offset + 2] / 16
            ctx.rectangle(points[offset] / 16, points[offset + 1] / 16, size, size)
            pending += 1
            if pending == 24:
                ctx.fill()
                ctx.rgb(*colour)
                pending = 0
        if pending:
            ctx.fill()
    # Sharp atmosphere at the illuminated limb; no expensive translucent glow.
    ctx.line_width = 1.4
    ctx.rgb(.28, .87, .98).arc(0, -4, radius + .5, 3.45, 5.48, False).stroke()
    _ellipse(ctx, 0, 2, 104, 24, 0, 32, tilt, (.33, .47, .76), 1.3)
    _ellipse(ctx, 0, 2, 100, 23, 4, 18, tilt, (.59, .49, .90), .7)
    _satellite(ctx, orbit, True)


@micropython.native
def _starflight(ctx, now, phase, detail):
    _background(ctx, now, detail)
    c, s = _UNIT[(now // 401) & 255]
    centre_x = _UNIT[(now // 97) & 255][1] * 7 + _VIEW[0] * 18
    centre_y = -5 + _UNIT[(now // 149) & 255][0] * 4 + _VIEW[1] * 18
    travel = (now % 5400) / 5400
    count = 72 if detail else 36
    colours = ((.15, .24, .46), (.18, .56, .82), (.69, .88, 1.0))
    for bucket, colour in enumerate(colours):
        ctx.rgb(*colour)
        ctx.line_width = .65 + bucket * .48
        for index in range(count):
            dx, dy, aperture, seed = _WARP[index]
            z = 1.05 - ((travel + seed) % 1)
            category = 2 if z < .39 else 1 if z < .74 else 0
            if category != bucket:
                continue
            rx, ry = dx * c - dy * s, dx * s + dy * c
            radius = aperture / z
            if radius > 150:
                continue
            tail = aperture / (z + .055 + phase * .10)
            ctx.move_to(centre_x + rx * tail, centre_y + ry * tail)
            ctx.line_to(centre_x + rx * radius, centre_y + ry * radius)
        ctx.stroke()
    # A compact vanishing-point reticle reads as a destination, not a dial.
    ctx.rgb(.19, .34, .55)
    ctx.line_width = .8
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ctx.move_to(centre_x + dx * 4, centre_y + dy * 4)
        ctx.line_to(centre_x + dx * 9, centre_y + dy * 9)
    ctx.stroke()


def render(ctx, scene, now_ms, phase, quality=1):
    """Paint a scene and restore ctx state. Unknown scenes leave ctx untouched.

    phase is normalized show/beat energy, not elapsed time. quality below0.5
    halves particles/points; malformed values use a safe default. The app
    owns labels, transitions, frame submission and all hardware interaction.
    """
    if scene not in SCENES:
        return False
    now, phase = _clock(now_ms), _level(phase, 0)
    detail = _level(quality, 1) >= .5
    ctx.save()
    try:
        if scene == "blackhole":
            _blackhole(ctx, now, phase, detail)
        elif scene == "planet":
            _planet(ctx, now, phase, detail)
        else:
            _starflight(ctx, now, phase, detail)
    finally:
        ctx.restore()
    return True
