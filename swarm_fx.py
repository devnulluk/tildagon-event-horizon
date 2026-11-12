"""Gravitational Choir: bounded vector art for real nearby badge snapshots.

draw() owns a complete background only for frame.scene == 'swarm'. For other
chapters it paints a sparse interaction overlay, and touches nothing when no
peers or join/boost event exists. Positions are artistic, never RF distances.
RGB input is byte-valued; all energies/phases are normalized0..1. Explicitly
expired peers (>6000ms) are omitted. No radio, file, framebuffer or texture API.
One synchronous foreground draw owner reuses the small geometry/colour caches.
"""
import math

TAU = math.pi * 2
MAX_PEERS = 12
_SCAN = 32
_UNIT = tuple((math.cos(index * TAU / 256), math.sin(index * TAU / 256)) for index in range(256))
_PALETTE = ((48, 223, 255), (138, 96, 255), (255, 78, 181), (255, 170, 72),
            (88, 255, 189), (92, 155, 255), (226, 145, 255), (255, 231, 140))
_SKY = tuple((.004 + .013 * index / 13, .009 + .003 * index / 13,
              .031 + .025 * index / 13) for index in range(14))
_STARS = tuple((((index * 83 + 17) % 231) - 115,
                ((index * 57 + 29) % 219) - 109, index % 3) for index in range(42))
_DUST = ((.055, .12, .23), (.12, .25, .37), (.27, .46, .59))
_RIBBON_X = tuple(-126 + index * 252 / 17 for index in range(18))
_TRAVEL = tuple((3 * (1 - index / 32) ** 2 * (index / 32),
                 3 * (1 - index / 32) * (index / 32) ** 2,
                 (index / 32) ** 3) for index in range(32))
_IDS, _RX, _RY = [None] * MAX_PEERS, [None] * MAX_PEERS, [None] * MAX_PEERS
_BX, _BY, _PX, _PY = ([0.0] * MAX_PEERS for unused in range(4))
_ENERGY, _JOIN, _SEED = [0.0] * MAX_PEERS, [0.0] * MAX_PEERS, [0] * MAX_PEERS
_STRENGTH, _BEAT, _PHASE = [0.0] * MAX_PEERS, [0.0] * MAX_PEERS, [0] * MAX_PEERS
_KEY = [-1] * (MAX_PEERS + 1)
_COLOUR, _DIM, _MID = ([None] * (MAX_PEERS + 1) for unused in range(3))


def _finite(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value == value and -1e14 < value < 1e14)


def _level(value, default=0):
    return max(0, min(1, value)) if _finite(value) else default


def _identity(value):
    return ((type(value) is int and 0 <= value <= 0xffffffff)
            or (type(value) in (str, bytes) and 1 <= len(value) <= 24))


def _seed(value):
    if type(value) is int:
        return (value ^ (value >> 16)) & 0xffff
    result = 5381
    for item in value:
        result = (result * 33 + (ord(item) if isinstance(item, str) else item)) & 0xffff
    return result


def _colour(slot, raw, seed):
    if (not isinstance(raw, (list, tuple)) or len(raw) != 3
            or any(type(channel) is not int or not 0 <= channel <= 255 for channel in raw)):
        raw = _PALETTE[seed & 7]
    key = (raw[0] << 16) | (raw[1] << 8) | raw[2]
    if _KEY[slot] != key:
        _KEY[slot] = key
        _COLOUR[slot] = tuple(.14 + .86 * channel / 255 for channel in raw)
        _DIM[slot] = tuple(.025 + .17 * channel / 255 for channel in raw)
        _MID[slot] = tuple(.07 + .38 * channel / 255 for channel in raw)


def _peers(raw, now, limit):
    count = 0
    if not isinstance(raw, (list, tuple)):
        raw = ()
    for index in range(min(_SCAN, len(raw))):
        if count == limit:
            break
        peer = raw[index]
        if not isinstance(peer, dict) or not _identity(peer.get("id")):
            continue
        age = peer.get("age_ms", 0)
        if not _finite(age) or not 0 <= age <= 6000:
            continue
        ident = peer["id"]
        duplicate = False
        for prior in range(count):
            if _IDS[prior] == ident:
                duplicate = True
                break
        if duplicate:
            continue
        if _IDS[count] != ident:
            _IDS[count], _RX[count], _RY[count] = ident, None, None
            _SEED[count] = _seed(ident)
        seed = _SEED[count]
        x, y = peer.get("x"), peer.get("y")
        if not _finite(x) or not _finite(y):
            x, y = _UNIT[seed & 255]
        x, y = max(-1, min(1, x)), max(-1, min(1, y))
        if _RX[count] != x or _RY[count] != y:
            _RX[count], _RY[count] = x, y
            length = x * x + y * y
            if length < .001:
                x, y = _UNIT[seed & 255]
            elif length > 1:
                inverse = 1 / math.sqrt(length)
                x, y = x * inverse, y * inverse
            elif length < .25:
                inverse = .5 / math.sqrt(length)
                x, y = x * inverse, y * inverse
            _BX[count], _BY[count] = x * 92, y * 92
        # The model's peer.energy is presence freshness, while peer.burst is
        # the event envelope and pulse is the ordinary musical beat.
        energy = _level(peer.get("burst"))
        _STRENGTH[count] = _level(peer.get("energy"), 1)
        _BEAT[count] = _level(peer.get("pulse"))
        phase = peer.get("phase")
        _PHASE[count] = int(_level(phase) * 32) if _finite(phase) else (now // 39)
        _ENERGY[count], _JOIN[count] = energy, _level(peer.get("joined"))
        c, s = _UNIT[(now // 91 + seed) & 255]
        _PX[count] = _BX[count] * (1 - .07 * energy) + c * (1 + energy * 2)
        _PY[count] = _BY[count] * (1 - .07 * energy) + s * (1 + energy * 2)
        _colour(count, peer.get("colour"), seed)
        count += 1
    for index in range(count, MAX_PEERS):
        _IDS[index], _RX[index], _RY[index] = None, None, None
    return count


def _circle(ctx, x, y, radius, colour):
    ctx.rgb(*colour).arc(x, y, radius, 0, TAU, False).fill()


def _ring(ctx, x, y, radius, colour, width=1):
    ctx.line_width = width
    ctx.rgb(*colour).arc(x, y, radius, 0, TAU, False).stroke()


def _sky(ctx, now, detail):
    for index, colour in enumerate(_SKY):
        ctx.rgb(*colour).rectangle(-140, -140 + index * 20, 280, 20).fill()
    for shade, colour in enumerate(_DUST):
        ctx.rgb(*colour)
        for index in range(shade, 42 if detail else 21, 3):
            x, y, group = _STARS[index]
            size = 1.3 if (index + now // 700) % 11 == 0 else .7
            ctx.rectangle(x, y, size, size)
        ctx.fill()


def _aurora(ctx, now, count, energy, detail, phase):
    ribbons = 3 if detail and count else 2 if detail else 1
    step = 1 if detail else 2
    for ribbon in range(ribbons):
        for glow in (True, False):
            ctx.line_width = (5.0 if glow else 1.3) + energy * (2 if glow else .5)
            ctx.rgb(*(_DIM[MAX_PEERS] if glow else _COLOUR[MAX_PEERS]))
            first = True
            for index in range(0, 18, step):
                x = _RIBBON_X[index]
                wave = _UNIT[(index * 10 + now // 43 + ribbon * 57 + phase) & 255][1]
                fold = _UNIT[(index * 17 - now // 77 + ribbon * 83) & 255][1]
                y = -56 + ribbon * 21 + wave * (13 + count * .5) + fold * 6
                if first:
                    ctx.move_to(x, y)
                    first = False
                else:
                    ctx.line_to(x, y)
            ctx.stroke()


def _filament(ctx, index, now, energy, full):
    x, y, seed = _PX[index], _PY[index], _SEED[index]
    bend = .14 + .12 * _UNIT[(now // 97 + seed) & 255][1]
    ax, ay = -y * bend, x * bend
    bx, by = x * .58 - y * bend, y * .58 + x * bend
    ctx.line_width = 1.3 if full else .65
    ctx.rgb(*(_COLOUR[index] if _ENERGY[index] > .15 else _MID[index] if full else _DIM[index]))
    ctx.move_to(0, 2).curve_to(ax, ay, bx, by, x, y).stroke()
    q = (_PHASE[index] + seed) & 31
    a, b, c = _TRAVEL[q]
    px, py = a * ax + b * bx + c * x, a * ay + b * by + c * y + 2 * (1 - q / 32) ** 3
    _circle(ctx, px, py, .9 + energy * 1.4 + _ENERGY[index], _COLOUR[index])


def _star(ctx, index, full):
    x, y = _PX[index], _PY[index]
    active = max(_ENERGY[index], _JOIN[index])
    _circle(ctx, x, y, (7.0 if full else 2.8) + active * (4 if full else 3), _DIM[index])
    if full:
        _circle(ctx, x, y, 2.5 + active * 1.4, _COLOUR[index])
    size = (1.7 if full else 1.1) + active * 1.4 + _BEAT[index] * (.25 if full else .12)
    strength = .2 + _STRENGTH[index] * .8
    colour = (.84, .98, 1) if full else _COLOUR[index]
    ctx.rgb(colour[0] * strength, colour[1] * strength, colour[2] * strength).rectangle(x - size * .45, y - size * 2, size * .9, size * 4)
    ctx.rectangle(x - size * 2, y - size * .45, size * 4, size * .9).fill()
    if active > .06:
        _ring(ctx, x, y, (10 if full else 7) + active * (6 if full else 7), _COLOUR[index], .8)


def _resonator(ctx, now, energy, count, detail, phase):
    vertices = 24 if detail else 16
    for layer in range(3 if detail else 2):
        radius = 27 + layer * 12 + energy * 5
        ctx.line_width = 2.8 if layer == 0 else 1.0
        ctx.rgb(*(_COLOUR[MAX_PEERS] if layer == 0 else _MID[MAX_PEERS] if layer == 1 else _DIM[MAX_PEERS]))
        for index in range(vertices + 1):
            c, s = _UNIT[(index * 256 // vertices + now // 47 + phase + layer * 37) & 255]
            x, y = c * radius, s * radius * (.41 + layer * .06)
            y += x * (.17 if layer % 2 else -.17)
            if index:
                ctx.line_to(x, y)
            else:
                ctx.move_to(x, y)
        ctx.stroke()
    _circle(ctx, 0, 2, 18 + energy * 6, (.012, .035, .079))
    _circle(ctx, 0, 2, 10 + energy * 5, _MID[MAX_PEERS])
    _circle(ctx, 0, 2, 4.0 + energy * 3, _COLOUR[MAX_PEERS])
    _circle(ctx, -.8, 1, 2.0 + energy, (.84, .98, 1))


def _nova(ctx, now, pulse, joined, detail):
    if joined > .015:
        radius = 21 + (1 - joined) * 83
        _ring(ctx, 0, 2, radius, _COLOUR[MAX_PEERS], .7 + joined)
    if pulse <= .015:
        return
    radius = 26 + (1 - pulse) * 88
    _ring(ctx, 0, 2, radius, _COLOUR[MAX_PEERS], 1.1 + pulse * 1.6)
    if detail:
        _ring(ctx, 0, 2, max(9, radius - 9), _DIM[MAX_PEERS], 2.2)
    ctx.line_width = .8 + pulse
    ctx.rgb(*_COLOUR[MAX_PEERS])
    rays = 16 if detail else 8
    angle = now // 23
    for index in range(rays):
        c, s = _UNIT[(index * 256 // rays + angle) & 255]
        inner = 18 + (index % 3) * 7
        outer = inner + (39 + (index % 4) * 9) * pulse
        ctx.move_to(c * inner, 2 + s * inner).line_to(c * outer, 2 + s * outer)
    ctx.stroke()


def draw(ctx, frame, swarm, now_ms, quality=1):
    """Draw a whole swarm scene or a sparse overlay; return whether handled.

    count alone cannot create peer nodes. Only valid, unique, nonexpired IDs
    produce stars, at most12(6 at lowdetail). All animation uses elapsed time,
    never frame counters. Failed native drawing still restores caller state.
    """
    frame = frame if isinstance(frame, dict) else {}
    swarm = swarm if isinstance(swarm, dict) else {}
    now = int(now_ms) if _finite(now_ms) and now_ms >= 0 else 0
    detail = _level(quality, 1) >= .5
    full = frame.get("scene") == "swarm"
    count = _peers(swarm.get("peers"), now, MAX_PEERS if detail else 6)
    # swarm.pulse is a continuous beat, not a radio-hit signal. Quiet solo
    # playback must keep its original chapters entirely free of overlays.
    pulse = max(_level(frame.get("burst")), _level(swarm.get("energy")))
    joined = _level(swarm.get("joined"))
    if not full and not count and pulse <= .015 and joined <= .015:
        return False
    phase = int(_level(swarm.get("phase")) * 256) & 255
    energy = max(pulse, count / MAX_PEERS * .48) + _level(swarm.get("pulse")) * .06
    energy = min(1, energy)
    _colour(MAX_PEERS, swarm.get("colour"), phase >> 5)
    ctx.save()
    try:
        if full:
            _sky(ctx, now, detail)
            _aurora(ctx, now, count, energy, detail, phase)
        links = min(count, 8 if full and detail else 4 if full or detail else 2)
        for index in range(links):
            _filament(ctx, index, now, energy, full)
        for index in range(count):
            _star(ctx, index, full)
        if full:
            _resonator(ctx, now, energy, count, detail, phase)
        _nova(ctx, now, pulse, joined, detail)
    finally:
        ctx.restore()
    return True
