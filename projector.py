"""Bounded Q15 sphere projection with a four-buffer native Viper kernel.

Source records are (xQ15,yQ15,zQ15,material0..2). Output has six fixed
308-point buckets, each record (x16,y16,size16); counts are POINT counts.
params: count,step,cQ15,sQ15,ctQ15,stQ15,radius16,sizeDepth16,centreY16.

Only project()/Projector are public safe entry points. They validate array
types, lengths, disjoint buffers and scalar bounds before pointer execution.
Each source record is also range/material/unit-checked inside the kernel.
No framebuffer, hardware, unchecked user pointer or native allocation is used.
Buffers belong to one synchronous draw owner and must not be mutated by any
other task/thread between validation and completion of a projection.
"""
from array import array
import struct
import sys

if struct.calcsize("i") != 4:
    raise RuntimeError("The sphere projector requires signed32 array('i')")

Q = 32768
MAX_POINTS = 308
BUCKETS = 6
STRIDE = MAX_POINTS * 3
OUTPUT_SIZE = BUCKETS * STRIDE
PARAMETER_COUNT = 9
PERSPECTIVE_Q15 = 111411       # round(3.4*32768)
PERSPECTIVE_ROOT_Q15 = 106483 # round(sqrt(3.4**2-1)*32768)
TANGENT_Q15 = 9637            # floor(32768**2/PERSPECTIVE_Q15)
LIGHT_THRESHOLD = 515396075   # floor(.48*32768**2)


def project_reference(src, out, counts, params):
    """Integer reference kernel; the Viper body below uses the same steps."""
    n, step, c, s, ct, st, radius16, depth16, cy16 = params[:9]
    for bucket in range(6):
        counts[bucket] = 0
    numerator = radius16 * 106483
    index = 0
    while index < n:
        at = index * 4
        x, y, z, material = src[at], src[at + 1], src[at + 2], src[at + 3]
        index += step
        if not (-32768 <= x <= 32768 and -32768 <= y <= 32768 and -32768 <= z <= 32768 and 0 <= material <= 2):
            continue
        # Halve before squaring: even invalid(1,1,1) input cannot overflow
        # signed32 arithmetic. Valid rounded sphere records fit this bound.
        half_norm = (x >> 1) * (x >> 1) + (y >> 1) * (y >> 1) + (z >> 1) * (z >> 1)
        if half_norm < 268369924 or half_norm > 268500996:
            continue
        rx = (x * c + z * s) >> 15
        rz = (z * c - x * s) >> 15
        ry = (y * ct - rz * st) >> 15
        rz = (y * st + rz * ct) >> 15
        if rz <= 9637:
            continue
        light = rx * -15729 + ry * -11469 + rz * 26214
        bucket = material * 2 + (1 if light > 515396075 else 0)
        count = counts[bucket]
        if count >= 308:
            continue
        scale16 = numerator // (111411 - rz)
        size16 = 20 + ((rz * depth16) >> 15)
        target = bucket * 924 + count * 3
        out[target] = ((rx * scale16) >> 15) - (size16 >> 1)
        out[target + 1] = ((ry * scale16) >> 15) + cy16 - (size16 >> 1)
        out[target + 2] = size16
        counts[bucket] = count + 1


if sys.implementation.name == "micropython":
    import micropython

    @micropython.viper
    def _project_viper(src: ptr32, out: ptr32, counts: ptr32, params: ptr32):
        n = int(params[0])
        step = int(params[1])
        c = int(params[2])
        s = int(params[3])
        ct = int(params[4])
        st = int(params[5])
        radius16 = int(params[6])
        depth16 = int(params[7])
        cy16 = int(params[8])
        bucket = 0
        while bucket < 6:
            counts[bucket] = 0
            bucket += 1
        numerator = radius16 * 106483
        index = 0
        while index < n:
            at = index * 4
            x = int(src[at])
            y = int(src[at + 1])
            z = int(src[at + 2])
            material = int(src[at + 3])
            index += step
            if x < -32768 or x > 32768 or y < -32768 or y > 32768 or z < -32768 or z > 32768 or material < 0 or material > 2:
                continue
            half_norm = (x >> 1) * (x >> 1) + (y >> 1) * (y >> 1) + (z >> 1) * (z >> 1)
            if half_norm < 268369924 or half_norm > 268500996:
                continue
            rx = (x * c + z * s) >> 15
            rz = (z * c - x * s) >> 15
            ry = (y * ct - rz * st) >> 15
            rz = (y * st + rz * ct) >> 15
            if rz <= 9637:
                continue
            light = rx * -15729 + ry * -11469 + rz * 26214
            bucket = material * 2
            if light > 515396075:
                bucket += 1
            count = int(counts[bucket])
            if count >= 308:
                continue
            scale16 = numerator // (111411 - rz)
            size16 = 20 + ((rz * depth16) >> 15)
            target = bucket * 924 + count * 3
            out[target] = ((rx * scale16) >> 15) - (size16 >> 1)
            out[target + 1] = ((ry * scale16) >> 15) + cy16 - (size16 >> 1)
            out[target + 2] = size16
            counts[bucket] = count + 1
else:
    _project_viper = project_reference


def _int_array(value, minimum, name):
    # Native MicroPython arrays expose neither typecode nor itemsize. An empty
    # slice retains its exact typecode, prints in a stable native format, and
    # never copies the potentially large source/output buffers. Requiring the
    # exact array class also excludes aliasing memoryviews and custom proxies.
    if type(value) is not array or len(value) < minimum or repr(value[:0]) != "array('i')":
        raise ValueError(name + " must be a sufficiently large signed32 array('i')")


def project(src, out, counts, params):
    """Validate public buffers before executing the allocation-free kernel."""
    _int_array(params, 9, "params")
    n, step, c, s, ct, st, radius16, depth16, cy16 = params[:9]
    if not 0 <= n <= 308 or step not in (1, 2):
        raise ValueError("Point count or step outside the bounded kernel contract")
    if not (0 < radius16 <= 1536 and depth16 in (17, 22) and -1920 <= cy16 <= 1920):
        raise ValueError("Projection size outside the bounded kernel contract")
    for first, second in ((c, s), (ct, st)):
        if not (-32768 <= first <= 32768 and -32768 <= second <= 32768
                and first * first + second * second <= 1073872900):
            raise ValueError("Rotation coefficients exceed unit-vector bounds")
    _int_array(src, n * 4, "src")
    _int_array(out, OUTPUT_SIZE, "out")
    _int_array(counts, 6, "counts")
    if src is out or src is counts or src is params or out is counts or out is params or counts is params:
        raise ValueError("Kernel buffers must not alias")
    _project_viper(src, out, counts, params)
    return out, counts


def pack_points(points):
    """Validate and quantize one immutable sphere table at module setup time."""
    result = array("i")
    count = 0
    for point in points:
        if count >= MAX_POINTS or not isinstance(point, (tuple, list)) or len(point) != 4:
            raise ValueError("Expected at most308 sphere/material records")
        x, y, z, material = point
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not -1 <= value <= 1 for value in (x, y, z)):
            raise ValueError("Sphere coordinates must be finite unit coordinates")
        if not .9998 <= x * x + y * y + z * z <= 1.0002:
            raise ValueError("Sphere coordinate is not on the unit sphere")
        if not isinstance(material, int) or isinstance(material, bool) or not 0 <= material <= 2:
            raise ValueError("Sphere material must be0..2")
        result.extend((round(x * Q), round(y * Q), round(z * Q), material))
        count += 1
    return result


class Projector:
    """Reusable validated source and bounded output buffers for one sphere."""
    def __init__(self, points):
        self.source = pack_points(points)
        self.output = array("i", [0] * OUTPUT_SIZE)
        self.counts = array("i", [0] * 6)
        self.params = array("i", [len(self.source) // 4, 1, Q, 0, Q, 0, 1120, 17, -64])

    def project(self, cosine, sine, tilt_cosine, tilt_sine, radius, detail=True):
        values = (cosine, sine, tilt_cosine, tilt_sine, radius)
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not -1000 < value < 1000 for value in values):
            raise ValueError("Non-finite projection parameter")
        self.params[1] = 1 if detail else 2
        self.params[2] = round(cosine * Q)
        self.params[3] = round(sine * Q)
        self.params[4] = round(tilt_cosine * Q)
        self.params[5] = round(tilt_sine * Q)
        self.params[6] = round(radius * 16)
        self.params[7] = 17 if detail else 22
        return project(self.source, self.output, self.counts, self.params)
