"""Native API, bounded geometry and deterministic procedural-scene checks."""
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "fx_cosmos.py"
package = types.ModuleType("cosmos_fixture")
package.__path__ = [str(PATH.parent)]
spec = importlib.util.spec_from_file_location("cosmos_fixture.fx_cosmos", PATH)
fx = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"cosmos_fixture": package}):
    spec.loader.exec_module(fx)


class NativeCanvas:
    ARITIES = {"save": 0, "restore": 0, "rgb": 3, "rectangle": 4,
               "arc": 6, "move_to": 2, "line_to": 2, "fill": 0, "stroke": 0}

    def __init__(self):
        self.operations = []
        self.depth = 0
        self.max_depth = 0
        self.path_edges = 0
        self.max_edges = 0

    def __getattr__(self, name):
        if name not in self.ARITIES:
            raise AssertionError("Unsupported native ctx API: " + name)

        def method(*values):
            if len(values) != self.ARITIES[name]:
                raise AssertionError("Incorrect native ctx arity: " + name)
            for value in values:
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise AssertionError("Non-finite native draw argument")
            if name == "save":
                self.depth += 1
                self.max_depth = max(self.max_depth, self.depth)
            elif name == "restore":
                self.depth -= 1
                if self.depth < 0:
                    raise AssertionError("Unbalanced native ctx state")
            elif name == "rgb":
                if not all(0 <= value <= 1 for value in values):
                    raise AssertionError("Out-of-range colour")
            elif name == "rectangle":
                self.path_edges += 4
                if values[2] <= 0 or values[3] <= 0:
                    raise AssertionError("Invalid rectangle")
            elif name == "line_to":
                self.path_edges += 1
            elif name == "arc":
                if values[2] <= 0 or type(values[5]) is not bool:
                    raise AssertionError("Invalid native arc")
                # Conservative logical curve budget; hardware measurements are
                # still needed to establish actual tessellation/render latency.
                self.path_edges += max(1, math.ceil(abs(values[4] - values[3]) * math.sqrt(values[2])))
            if name in ("fill", "stroke"):
                self.max_edges = max(self.max_edges, self.path_edges)
                self.path_edges = 0
            self.operations.append((name, values))
            return self

        return method


def draw(scene, now=12345, phase=.5, quality=1):
    ctx = NativeCanvas()
    result = fx.render(ctx, scene, now, phase, quality)
    return result, ctx


class CosmosSceneTests(unittest.TestCase):
    def setUp(self):
        fx.set_view(0, 0)

    def test_unknown_scene_returns_untouched_fallback(self):
        for scene in (None, "clock", "BLACKHOLE", [], {}, True):
            with self.subTest(scene=scene):
                result, ctx = draw(scene)
                self.assertFalse(result)
                self.assertEqual(ctx.operations, [])

    def test_all_scenes_use_only_bounded_native_geometry_and_balanced_state(self):
        for scene in fx.SCENES:
            for now in (0, 500, 18000, 120000, 1073741824):
                for quality in (0, 1):
                    with self.subTest(scene=scene, now=now, quality=quality):
                        result, ctx = draw(scene, now, 1, quality)
                        self.assertTrue(result)
                        self.assertEqual(ctx.depth, 0)
                        self.assertLessEqual(ctx.max_depth, 2)
                        self.assertLess(ctx.max_edges, 255)
                        primitives = sum(name in ("fill", "stroke") for name, args in ctx.operations)
                        self.assertLess(primitives, 65)

    def test_lower_quality_reduces_draw_geometry_in_every_scene(self):
        for scene in fx.SCENES:
            with self.subTest(scene=scene):
                _, high = draw(scene, quality=1)
                _, low = draw(scene, quality=0)
                high_count = sum(name in ("rectangle", "line_to") for name, args in high.operations)
                low_count = sum(name in ("rectangle", "line_to") for name, args in low.operations)
                self.assertLess(low_count, high_count)

    def test_malformed_timing_phase_and_quality_never_reach_native_draw_as_nan(self):
        malformed = (None, True, "bad", [], math.nan, math.inf, -math.inf)
        for scene in fx.SCENES:
            for value in malformed:
                with self.subTest(scene=scene, value=value):
                    result, ctx = draw(scene, value, value, value)
                    self.assertTrue(result)
                    self.assertEqual(ctx.depth, 0)

    def test_elapsed_time_animates_each_scene_without_frame_history(self):
        for scene in fx.SCENES:
            with self.subTest(scene=scene):
                _, first = draw(scene, 12345)
                _, changed = draw(scene, 16000)
                _, repeated = draw(scene, 12345)
                self.assertNotEqual(first.operations, changed.operations)
                self.assertEqual(first.operations, repeated.operations)

    def test_render_uses_cached_trigonometry(self):
        with patch.object(fx.math, "sin", side_effect=AssertionError("Per-frame sine")), \
                patch.object(fx.math, "cos", side_effect=AssertionError("Per-frame cosine")):
            for scene in fx.SCENES:
                result, _ = draw(scene)
                self.assertTrue(result)

    def test_native_state_is_restored_even_when_rendering_fails(self):
        class FailingCanvas(NativeCanvas):
            def rgb(self, *values):
                raise RuntimeError("Synthetic driver failure")

        for scene in fx.SCENES:
            ctx = FailingCanvas()
            with self.assertRaisesRegex(RuntimeError, "Synthetic driver failure"):
                fx.render(ctx, scene, 1000, .5)
            self.assertEqual(ctx.depth, 0)

    def test_planet_points_lie_on_a_real_sphere_and_project_within_its_limb(self):
        self.assertGreater(len(fx._SPHERE), 250)
        for x, y, z, material in fx._SPHERE:
            self.assertAlmostEqual(x * x + y * y + z * z, 1, places=12)
            self.assertIn(material, (0, 1, 2))
        for now in (0, 2500, 12000):
            draw("planet", now, 1)
            self.assertGreater(sum(fx._PROJECTOR.counts), 75)
            buffer = fx._PROJECTOR.output
            for bucket, count in enumerate(fx._PROJECTOR.counts):
                for point in range(count):
                    offset = bucket * 924 + point * 3
                    size = buffer[offset + 2] / 16
                    x, y = buffer[offset] / 16 + size / 2, buffer[offset + 1] / 16 + size / 2 + 4
                    # Q15 projection is checked independently against the
                    # float reference; allow its subpixel limb quantization.
                    self.assertLessEqual(x * x + y * y, 72.3 * 72.3)

    def test_projection_buffers_are_reused_and_material_paths_stay_short(self):
        buffers = tuple(map(id, (fx._PROJECTOR.source, fx._PROJECTOR.output,
                                fx._PROJECTOR.counts, fx._PROJECTOR.params)))
        for now in (0, 5000, 15000):
            _, ctx = draw("planet", now)
            self.assertEqual(tuple(map(id, (fx._PROJECTOR.source, fx._PROJECTOR.output,
                                           fx._PROJECTOR.counts, fx._PROJECTOR.params))), buffers)
            self.assertLessEqual(ctx.max_edges, 100)

    def test_background_covers_round_viewport_under_full_camera_translation(self):
        for scene in fx.SCENES:
            _, ctx = draw(scene)
            bands = [args for name, args in ctx.operations if name == "rectangle"][:12]
            self.assertEqual(len(bands), 12)
            self.assertTrue(all(x <= -134 and x + width >= 134 for x, y, width, height in bands))
            self.assertLessEqual(bands[0][1], -134)
            self.assertGreaterEqual(bands[-1][1] + bands[-1][3], 134)
            self.assertTrue(all(first[1] + first[3] == second[1] for first, second in zip(bands, bands[1:])))

    def test_planet_view_rotates_projected_surface_in_both_axes(self):
        _, centre = draw("planet", 12000)
        fx.set_view(1, 0)
        _, yaw = draw("planet", 12000)
        fx.set_view(0, 1)
        _, pitch = draw("planet", 12000)
        surface = lambda ctx: [args for name, args in ctx.operations if name == "rectangle" and args[2] < 4]
        self.assertNotEqual(surface(centre), surface(yaw))
        self.assertNotEqual(surface(centre), surface(pitch))
        self.assertNotEqual(surface(yaw), surface(pitch))

    def test_starflight_view_moves_its_vanishing_point_without_frame_history(self):
        fx.set_view(-1, 0)
        _, left = draw("starflight", 12000)
        fx.set_view(1, 0)
        _, right = draw("starflight", 12000)
        left_tip = [args for name, args in left.operations if name == "line_to"][-1]
        right_tip = [args for name, args in right.operations if name == "line_to"][-1]
        self.assertAlmostEqual(right_tip[0] - left_tip[0], 36)
        self.assertAlmostEqual(right_tip[1], left_tip[1])

    def test_blackhole_has_a_dark_core_and_sparks_cannot_cross_it(self):
        _, ctx = draw("blackhole", 1000)
        dark = next(index for index, (name, values) in enumerate(ctx.operations)
                    if name == "rgb" and values == (.001, .002, .008))
        self.assertEqual(ctx.operations[dark + 1][0], "arc")
        self.assertAlmostEqual(ctx.operations[dark + 1][1][2], 29.7)
        # Spark paths are the last disconnected move/line pairs. They are
        # restricted outside the core, unlike a decorative hand through it.
        stroke = max(index for index, (name, args) in enumerate(ctx.operations) if name == "stroke")
        start = max(index for index, (name, args) in enumerate(ctx.operations[:stroke]) if name == "rgb")
        for name, values in ctx.operations[start:stroke]:
            if name == "line_to":
                x, y = values
                self.assertGreaterEqual(x * x + (y + 2) * (y + 2), 1200)


if __name__ == "__main__":
    unittest.main()
