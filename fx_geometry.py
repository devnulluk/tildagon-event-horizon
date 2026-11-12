"""Bounded native-ctx geometry scenes for the Tildagon Event Horizon demo.

All coordinates are centred on the240px display. The caller owns text/chrome.
No textures, framebuffer tricks, power or firmware changes. Selected hot loops
use the standard MicroPython native emitter with an ordinary-Python simulator fallback.
Geometry and trigonometric tables are cached once; reusable projection buffers
keep per-frame allocation small. Render on one foreground task, not concurrently.
"""
import math

import sys
if sys.implementation.name == "micropython":
    import micropython
else:
    class micropython:
        @staticmethod
        def native(function):
            return function

SCENES = ("tunnel", "terrain", "kaleidoscope")
TAU = math.pi * 2
_SIZE = 512
_UNIT = tuple((math.cos(index * TAU / _SIZE), math.sin(index * TAU / _SIZE)) for index in range(_SIZE))
_NEON = ((.12, .88, 1), (.35, .57, 1), (.72, .30, 1), (1, .19, .66),
         (1, .35, .29), (1, .72, .20), (.43, 1, .66), (.12, .88, 1))
_DARK_NEON = tuple(tuple(channel * .20 for channel in colour) for colour in _NEON)
_TUNNEL_CORE = tuple((.12 + index * .028, .72 - index * .022, 1 - index * .006) for index in range(16))
_TUNNEL_GLOW = tuple(tuple(channel * .22 for channel in colour) for colour in _TUNNEL_CORE)
_FLOOR_COLOURS = tuple((.12 + index * .018, .23 + index * .045, .48 + index * .040) for index in range(10))
_STARS = ((-91, -67), (-76, -31), (-57, -97), (-36, -62), (-18, -101), (7, -91),
          (35, -83), (57, -102), (76, -68), (96, -33), (-111, -14), (110, -16))
_RIDGE_FAR = ((-140, -20), (-112, -57), (-91, -39), (-69, -68), (-46, -43),
              (-27, -26), (8, -40), (29, -54), (52, -37), (73, -64), (97, -46), (133, -61))
_RIDGE_NEAR = ((-140, 1), (-116, -24), (-95, -13), (-75, -42), (-58, -26),
               (-31, -9), (-4, -16), (27, -4), (51, -27), (79, -14), (103, -32), (141, -9))
_T_X, _T_Y = [0.0] * 112, [0.0] * 112
_G_X, _G_Y = [0.0] * 110, [0.0] * 110


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value == value and abs(value) < 1000000000000000)


def _wave(index):
    return _UNIT[int(index) & 511][1]


def _background(ctx, colour):
    ctx.rgb(*colour).rectangle(-140, -140, 280, 280).fill()


def _circle(ctx, x, y, radius, colour):
    ctx.rgb(*colour).arc(x, y, radius, 0, TAU, False).fill()


def _polygon(ctx, points, colour):
    ctx.rgb(*colour).move_to(*points[0])
    for x, y in points[1:]:
        ctx.line_to(x, y)
    ctx.close_path().fill()


def _ring_path(ctx, start, vertices):
    ctx.move_to(_T_X[start], _T_Y[start])
    for vertex in range(1, vertices):
        ctx.line_to(_T_X[start + vertex], _T_Y[start + vertex])
    ctx.close_path()


@micropython.native
def _tunnel(ctx, now, phase, quality):
    _background(ctx, (.004, .007, .025))
    rings, vertices = 7 + int(7 * quality), 8
    travel = (now % 1700) / 1700
    roll = int(now / 39 + phase * 48)
    for ring in range(rings):
        depth = (ring + travel) / rings
        radius = 19 / (.10 + depth)
        cx = _wave(now / 23 + depth * 120) * 21 * (1 - depth)
        cy = _wave(now / 31 + depth * 81 + 128) * 15 * (1 - depth)
        twist = roll + int(depth * 105 + _wave(now / 19 + ring * 17) * 6)
        for vertex in range(vertices):
            x, y = _UNIT[(twist + vertex * 64) & 511]
            index = ring * vertices + vertex
            _T_X[index] = cx + x * radius
            _T_Y[index] = cy + y * radius
    # Rails establish depth before the bright cross-sections. Each independent
    # path has at most13 segments: comfortably below the native255-edge limit.
    ctx.line_width = 1
    for vertex in range(0, vertices, 1 if quality >= .45 else 2):
        ctx.rgb(.055, .18, .34).move_to(_T_X[vertex], _T_Y[vertex])
        for ring in range(1, rings):
            index = ring * vertices + vertex
            ctx.line_to(_T_X[index], _T_Y[index])
        ctx.stroke()
    for ring in range(rings - 1, -1, -1):
        colour = (ring * 15 // rings + int(now // 800)) & 15
        if ring < 3 and quality > .4:
            ctx.line_width = 3.1
            ctx.rgb(*_TUNNEL_GLOW[colour])
            _ring_path(ctx, ring * vertices, vertices)
            ctx.stroke()
        ctx.line_width = 1.25 if ring < rings // 2 else .9
        ctx.rgb(*_TUNNEL_CORE[colour])
        _ring_path(ctx, ring * vertices, vertices)
        ctx.stroke()
    # Small opaque sparks, rather than full-frame alpha trails.
    ctx.rgb(.75, .95, 1)
    for index in range(3 + int(3 * quality)):
        ring = (index * 3 + int(now // 400)) % rings
        vertex = (index * 3 + 1) % vertices
        at = ring * vertices + vertex
        ctx.rectangle(_T_X[at] - 1, _T_Y[at] - 1, 2, 2)
    ctx.fill()


def _ridge(ctx, points, shift, fill, edge):
    ctx.rgb(*fill).move_to(points[0][0] + shift, points[0][1])
    for x, y in points[1:]:
        ctx.line_to(x + shift, y)
    ctx.line_to(140, 21).line_to(-140, 21).close_path().fill()
    ctx.line_width = 1
    ctx.rgb(*edge).move_to(points[0][0] + shift, points[0][1])
    for x, y in points[1:]:
        ctx.line_to(x + shift, y)
    ctx.stroke()


@micropython.native
def _terrain(ctx, now, phase, quality):
    sky = (.006, .008, .029)
    _background(ctx, sky)
    ctx.rgb(.27, .42, .67)
    for x, y in _STARS:
        ctx.rectangle(x, y, 1.3, 1.3)
    ctx.fill()
    sun_y = -48 + _wave(now / 90) * 2
    _circle(ctx, 0, sun_y, 32, (1, .34, .27))
    _circle(ctx, 0, sun_y - 7, 24, (1, .58, .25))
    ctx.rgb(*sky)
    for index in range(5):
        ctx.rectangle(-35, sun_y - 1 + index * 6, 70, 2 + index * .45)
    ctx.fill()
    _ridge(ctx, _RIDGE_FAR, _wave(now / 140) * 5, (.045, .021, .10), (.27, .09, .36))
    _ridge(ctx, _RIDGE_NEAR, _wave(now / 95) * 8, (.018, .017, .065), (.42, .10, .42))
    _polygon(ctx, ((-8, -17), (8, -17), (49, 120), (-49, 120)), (.012, .025, .065))
    rows, columns = 6 + int(4 * quality), 7 + int(4 * quality)
    travel = (now % 1400) / 1400
    for row in range(rows):
        z = .38 + (row + travel) * (5.2 / rows)
        perspective = 1 / (z + .28)
        row_phase = int(now / 17 + z * 49)
        for column in range(columns):
            world_x = (column - (columns - 1) / 2) * (10 / (columns - 1))
            bank = max(0, abs(world_x) - 1.2)
            height = bank * (7 + _wave(row_phase + column * 39) * 4)
            height += _wave(row_phase // 2 + column * 21) * (2 + phase * 2)
            index = row * columns + column
            _G_X[index] = world_x * 43 * perspective
            _G_Y[index] = -28 + 129 * perspective - height * perspective
    # Individual row/column paths stay small; no giant combined mesh path.
    for row in range(rows - 1, -1, -1):
        colour = _FLOOR_COLOURS[(rows - 1 - row) * 9 // max(1, rows - 1)]
        ctx.rgb(*colour)
        ctx.line_width = 1.15 if row < 3 else .8
        first = row * columns
        ctx.move_to(_G_X[first], _G_Y[first])
        for column in range(1, columns):
            ctx.line_to(_G_X[first + column], _G_Y[first + column])
        ctx.stroke()
    ctx.line_width = .9
    for column in range(columns):
        ctx.rgb(.08, .33, .50).move_to(_G_X[column], _G_Y[column])
        for row in range(1, rows):
            index = row * columns + column
            ctx.line_to(_G_X[index], _G_Y[index])
        ctx.stroke()
    # A moving center lane makes the camera's forward movement unambiguous.
    for index in range(4):
        z = .7 + ((index + travel) % 4) * 1.05
        near, far = 1 / z, 1 / (z + .16)
        _polygon(ctx, ((-1.3 * near, -28 + 126 * near), (1.3 * near, -28 + 126 * near),
                       (1.3 * far, -28 + 126 * far), (-1.3 * far, -28 + 126 * far)), (.42, .79, .91))


def _kaleidoscope(ctx, now, phase, quality):
    _background(ctx, (.012, .006, .035))
    arms, layers = (8 if quality >= .45 else 6), 2 + int(2 * quality)
    breath = 1 + _wave(now / 15) * .06
    for layer in range(layers):
        radius = 109 * (.64 ** layer) * breath
        width = radius * (.22 + _wave(now / 24 + layer * 83) * .045)
        spin = now / (11000 - layer * 1100) * TAU * (-1 if layer % 2 else 1)
        ctx.save()
        try:
            ctx.rotate(spin + phase * .34 + layer * .31)
            for arm in range(arms):
                colour = (arm + layer * 2 + int(now // 2300)) & 7
                # Each shard has just five vertices, even at maximum quality.
                ctx.rgb(*_DARK_NEON[colour]).move_to(radius * .10, 0)
                ctx.line_to(radius * .58, -width).line_to(radius, -width * .18)
                ctx.line_to(radius * .76, width).line_to(radius * .35, width * .65).close_path().fill()
                ctx.line_width = 1.3 if layer == 0 else 1
                ctx.rgb(*_NEON[colour]).move_to(radius * .10, 0)
                ctx.line_to(radius * .58, -width).line_to(radius, -width * .18)
                ctx.line_to(radius * .76, width).line_to(radius * .35, width * .65).close_path().stroke()
                # A contrasting bright facet creates a cut-glass appearance.
                if quality > .65 and (arm + layer) % 2 == 0:
                    ctx.rgb(*_NEON[(colour + 2) & 7]).move_to(radius * .58, -width)
                    ctx.line_to(radius * .70, width * .10).line_to(radius * .35, width * .65).close_path().fill()
                ctx.rotate(TAU / arms)
        finally:
            ctx.restore()
    _circle(ctx, 0, 0, 11, (.06, .04, .18))
    ctx.line_width = 1.8
    ctx.rgb(.38, .92, 1).arc(0, 0, 10, 0, TAU, False).stroke()
    _circle(ctx, 0, 0, 4 + _wave(now / 8) * 1.1, (.86, .47, 1))


_DRAWERS = {"tunnel": _tunnel, "terrain": _terrain, "kaleidoscope": _kaleidoscope}


def render(ctx, scene, now_ms, phase, quality=1):
    """Draw one known scene; unknown scenes leave the context untouched."""
    drawer = _DRAWERS.get(scene) if isinstance(scene, str) else None
    if drawer is None:
        return False
    now = max(0, now_ms) if _number(now_ms) else 0
    progress = max(0, min(1, phase)) if _number(phase) else 0
    detail = max(0, min(1, quality)) if _number(quality) else 1
    ctx.save()
    try:
        drawer(ctx, now, progress, detail)
    finally:
        ctx.restore()
    return True
