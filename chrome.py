"""Small typographic/iris choreography around the procedural worlds."""
import math
from .show import sine

TAU = math.pi * 2
WHITE = (.90, .96, 1)
CYAN = (.22, .86, 1)
_HEX = tuple((math.sin(i*TAU/6), -math.cos(i*TAU/6)) for i in range(7))


def text(ctx, value, y, size, width=210, colour=WHITE, minimum=10, x=0):
    value = str(value)
    ctx.font_size = size
    while size > minimum and ctx.text_width(value) > width:
        size -= 1
        ctx.font_size = size
    ctx.rgb(*colour).move_to(x, y).text(value)


def polygon(ctx, points, colour, width=1):
    ctx.line_width = width
    ctx.rgb(*colour).move_to(*points[0])
    for point in points[1:]:
        ctx.line_to(*point)
    ctx.stroke()


def title(ctx, frame, finale=False):
    now, phase = frame["time_ms"], frame["phase"]
    ctx.rgb(.004, .008, .022).rectangle(-120,-120,240,240).fill()
    for index in range(6):
        radius = 32 + ((index * 19 + now/50) % 114)
        colour = (.03 + .02*index, .12 + .04*index, .19 + .06*index)
        points = [(x*radius, y*radius) for x,y in _HEX]
        ctx.save()
        ctx.rotate(now/8000 + index*.12)
        polygon(ctx, points, colour, 1 if index%2 else 2)
        ctx.restore()
    ctx.rgb(.006,.012,.03).round_rectangle(-113,-55,226,105,18).fill()
    if finale:
        text(ctx, "WE ARE MADE", -24, 27, 212)
        text(ctx, "OF STARS", 14, 36, 208, CYAN)
        text(ctx, "SPACEAGON / REALTIME DEMO", 66, 11, 180, (.43,.65,.76))
        text(ctx, "DEVNULLUK", 86, 15, 150, (.80,.56,1))
    else:
        text(ctx, "EVENT", -25, 43, 207, CYAN)
        text(ctx, "HORIZON", 18, 43, 218)
        text(ctx, "A SPACEAGON ODYSSEY", 65, 12, 182, (.55,.69,.8))
        text(ctx, "TILT / TOUCH / EXPLORE", 84, 10, 170, (.44,.56,.69))
    # Smooth orbit rather than full-screen flashes.
    angle = now/1300
    for side in (-1,1):
        x, y = math.cos(angle)*102*side, math.sin(angle)*102*side
        ctx.rgb(.25,.9,1).arc(x,y,3,0,TAU,False).fill()


def overlay(ctx, frame, hud=False, paused=False, metrics=None):
    local, duration = frame["local_ms"], frame["duration_ms"]
    if frame["scene"] not in ("intro", "finale") and (local < 2600 or hud):
        ctx.rgb(.005,.012,.035).round_rectangle(-92,-103,184,23,9).fill()
        text(ctx, frame["title"], -91, 12, 174, CYAN)
    if hud or paused:
        ctx.rgb(.005,.012,.035).round_rectangle(-89,80,178,22,8).fill()
        value = "PAUSED / C TO RESUME" if paused else "B / E: SCENE   A: BOOST"
        text(ctx, value, 91, 10, 164, (.58,.76,.85))
    if hud and metrics:
        text(ctx, "%d FPS / %d MS" % (metrics.get("fps",0), metrics.get("draw_ms",0)), 67, 10, 180, (.54,.72,.80))
    # A segmented orbital chapter gauge along the bottom rim.
    for index in range(8):
        angle = math.pi*.34 + index*math.pi*.046
        x,y = math.cos(angle)*110,math.sin(angle)*110
        colour = CYAN if index == frame["index"] else (.10,.18,.28)
        ctx.rgb(*colour).arc(x,y,2,0,TAU,False).fill()


def iris_radius(frame):
    """Single-scene iris: no expensive second world is drawn during changes."""
    local, remaining = frame["local_ms"], frame["duration_ms"]-frame["local_ms"]
    if local < 650:
        progress = local/650
    elif remaining < 450:
        progress = remaining/450
    else:
        return None
    progress = max(0, min(1, progress))
    return 2 + 175*(1-(1-progress)**3)
