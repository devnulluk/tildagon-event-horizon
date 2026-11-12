"""Native API and geometry-budget guards without a badge or firmware changes."""
import importlib.util
import math
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "fx_geometry.py"
SPEC = importlib.util.spec_from_file_location("event_horizon_geometry", PATH)
geometry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(geometry)


class Canvas:
    ARITIES = {"save": 0, "restore": 0, "rgb": 3, "rectangle": 4, "fill": 0,
               "move_to": 2, "line_to": 2, "close_path": 0, "stroke": 0,
               "arc": 6, "rotate": 1}
    def __init__(self):
        self.calls = []
        self.depth = 0
        self.maximum_depth = 0
        self.path_segments = 0
        self.stroke_segments = []
        self.fill_edges = []
    def __getattr__(self, name):
        if name not in self.ARITIES:
            raise AttributeError("Unsupported native ctx method: " + name)
        def draw(*values):
            if len(values) != self.ARITIES[name]:
                raise TypeError("Wrong native ctx arity: " + name)
            self.calls.append((name, values))
            for value in values:
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Non-finite native argument")
            if name == "rgb" and any(not 0 <= value <= 1 for value in values):
                raise ValueError("Invalid RGB channel")
            if name == "save":
                self.depth += 1
                self.maximum_depth = max(self.maximum_depth, self.depth)
            elif name == "restore":
                self.depth -= 1
                if self.depth < 0:
                    raise ValueError("Unbalanced native save/restore")
            elif name in ("line_to", "close_path"):
                self.path_segments += 1
            elif name == "rectangle":
                self.path_segments += 4
            elif name == "stroke":
                self.stroke_segments.append(self.path_segments)
                self.path_segments = 0
            elif name == "fill":
                self.fill_edges.append(self.path_segments)
                self.path_segments = 0
            return self
        return draw


def render(scene, now=1234, phase=.5, quality=1):
    canvas = Canvas()
    handled = geometry.render(canvas, scene, now, phase, quality)
    return handled, canvas


class GeometryTests(unittest.TestCase):
    def test_unknown_scene_leaves_native_context_untouched(self):
        for scene in (None, "unknown", [], True):
            handled, canvas = render(scene)
            self.assertFalse(handled)
            self.assertEqual(canvas.calls, [])

    def test_each_scene_uses_only_supported_native_methods_and_balances_state(self):
        for scene in geometry.SCENES:
            handled, canvas = render(scene)
            self.assertTrue(handled)
            self.assertEqual(canvas.depth, 0)
            self.assertLessEqual(canvas.maximum_depth, 2)
            self.assertTrue(canvas.stroke_segments)

    def test_all_path_batches_stay_conservatively_under_native_edge_limit(self):
        for scene in geometry.SCENES:
            for now in (0, 250, 1699, 1700, 5999999):
                with self.subTest(scene=scene, now=now):
                    handled, canvas = render(scene, now=now)
                    # Four raster edges per disconnected stroked segment is
                    # the conservative budget used for the badge's line paths.
                    self.assertLessEqual(max(canvas.stroke_segments, default=0) * 4, 192)
                    self.assertLess(max(canvas.fill_edges, default=0), 255)
                    primitives = sum(name in ("fill", "stroke") for name, values in canvas.calls)
                    self.assertLess(primitives, 110)

    def test_low_quality_reduces_native_command_count(self):
        for scene in geometry.SCENES:
            high = render(scene, quality=1)[1]
            low = render(scene, quality=0)[1]
            self.assertLess(len(low.calls), len(high.calls) * .8)

    def test_scenes_animate_from_time_without_changing_the_cache_geometry(self):
        table, tunnel_x, grid_x = geometry._UNIT, geometry._T_X, geometry._G_X
        for scene in geometry.SCENES:
            self.assertNotEqual(render(scene, now=0)[1].calls, render(scene, now=1234)[1].calls)
        self.assertIs(geometry._UNIT, table)
        self.assertIs(geometry._T_X, tunnel_x)
        self.assertIs(geometry._G_X, grid_x)

    def test_numeric_inputs_are_bounded_and_malformed_values_are_safe(self):
        for scene in geometry.SCENES:
            for invalid in (None, "bad", float("nan"), float("inf"), True):
                handled, canvas = render(scene, now=invalid, phase=invalid, quality=invalid)
                self.assertTrue(handled)
                self.assertEqual(canvas.depth, 0)
            render(scene, now=-1, phase=-3, quality=-2)
            render(scene, now=100000000, phase=6, quality=6)

    def test_every_frame_starts_with_one_opaque_full_display_clear(self):
        for scene in geometry.SCENES:
            handled, canvas = render(scene)
            # The camera can translate ±14px: opaque coverage extends20px
            # beyond the LCD so no old pixels leak around the moving scene.
            self.assertEqual(canvas.calls[2], ("rectangle", (-140, -140, 280, 280)))
            self.assertEqual(canvas.calls[3], ("fill", ()))

    def test_native_exception_still_restores_the_caller_context(self):
        canvas = Canvas()
        original = canvas.__getattr__
        def fail(*args):
            raise RuntimeError("test native error")
        canvas.rectangle = fail
        with self.assertRaises(RuntimeError):
            geometry.render(canvas, "tunnel", 0, 0)
        self.assertEqual(canvas.depth, 0)


if __name__ == "__main__":
    unittest.main()
