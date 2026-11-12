"""Pure geometry/input budgets for the nearby-badge visual layer."""
import copy
import importlib.util
import math
from pathlib import Path
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "swarm_fx.py"
spec = importlib.util.spec_from_file_location("swarm_fx_under_test", PATH)
fx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fx)
model_spec = importlib.util.spec_from_file_location("swarm_model_visual_contract", PATH.with_name("swarm.py"))
model = importlib.util.module_from_spec(model_spec)
model_spec.loader.exec_module(model)


class Canvas:
    ARITIES = {"save": 0, "restore": 0, "rgb": 3, "rectangle": 4,
               "arc": 6, "move_to": 2, "line_to": 2, "curve_to": 6,
               "fill": 0, "stroke": 0}

    def __init__(self):
        self.calls = []
        self.depth = self.maximum_depth = 0
        self.path_edges = self.maximum_edges = 0

    def __getattr__(self, name):
        if name not in self.ARITIES:
            raise AssertionError("Unsupported native ctx method: " + name)

        def method(*values):
            if len(values) != self.ARITIES[name]:
                raise AssertionError("Wrong native ctx arity: " + name)
            for value in values:
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise AssertionError("Nonfinite native argument")
            if name == "rgb" and any(not 0 <= value <= 1 for value in values):
                raise AssertionError("Invalid colour")
            if name == "arc" and (values[2] <= 0 or type(values[5]) is not bool):
                raise AssertionError("Invalid native arc")
            if name == "rectangle" and (values[2] <= 0 or values[3] <= 0):
                raise AssertionError("Invalid rectangle")
            if name == "save":
                self.depth += 1
                self.maximum_depth = max(self.maximum_depth, self.depth)
            elif name == "restore":
                self.depth -= 1
                if self.depth < 0:
                    raise AssertionError("Unbalanced caller state")
            elif name == "rectangle":
                self.path_edges += 4
            elif name == "line_to":
                self.path_edges += 4
            elif name in ("curve_to", "arc"):
                # A single native curve/circle is bounded separately, rather
                # than merging many curves into the255-edge native cache.
                self.path_edges += 128
            elif name in ("fill", "stroke"):
                self.maximum_edges = max(self.maximum_edges, self.path_edges)
                self.path_edges = 0
            self.calls.append((name, values))
            return self

        return method


def peers(count=12, active=True):
    return [{"id": "%08x" % index, "x": math.cos(index * math.tau / count),
             "y": math.sin(index * math.tau / count), "colour": (60, 120 + index * 8, 240),
             "energy": 1 if active else 0, "burst": .7 if active else 0,
             "joined": .5 if active else 0, "age_ms": 10} for index in range(count)]


def draw(scene="swarm", swarm=None, now=1234, quality=1, burst=0):
    canvas = Canvas()
    handled = fx.draw(canvas, {"scene": scene, "burst": burst}, swarm, now, quality)
    return handled, canvas


class SwarmVisualTests(unittest.TestCase):
    def test_disconnected_quiet_overlay_is_truly_untouched(self):
        for value in (None, {}, {"peers": [], "count": 500, "pulse": 1}, {"peers": "bad"}):
            handled, canvas = draw("planet", value)
            self.assertFalse(handled)
            self.assertEqual(canvas.calls, [])
            self.assertTrue(all(value is None for value in fx._IDS))

    def test_solo_scene_and_local_boost_still_have_real_visuals(self):
        handled, canvas = draw()
        self.assertTrue(handled)
        self.assertEqual(canvas.calls[:4], [("save", ()), ("rgb", fx._SKY[0]),
                                           ("rectangle", (-140, -140, 280, 20)), ("fill", ())])
        quiet = draw("planet")[1]
        handled, burst = draw("planet", burst=1)
        self.assertTrue(handled)
        self.assertGreater(len(burst.calls), len(quiet.calls))
        self.assertFalse(any(name == "rectangle" and values[2] >= 240 for name, values in burst.calls))

    def test_full_scene_and_overlay_have_strict_native_budgets(self):
        view = {"peers": peers(), "count": 12, "pulse": 1, "joined": 1, "energy": 1,
                "phase": .4, "colour": (160, 80, 255)}
        for scene, maximum in (("swarm", 104), ("blackhole", 52)):
            for now in (0, 499, 1200, 99999999):
                handled, canvas = draw(scene, view, now)
                self.assertTrue(handled)
                self.assertEqual(canvas.depth, 0)
                self.assertEqual(canvas.maximum_depth, 1)
                self.assertLessEqual(canvas.maximum_edges, 192)
                primitives = sum(name in ("fill", "stroke") for name, values in canvas.calls)
                self.assertLessEqual(primitives, maximum)
                if scene != "swarm":
                    self.assertFalse(any(name == "rectangle" and values[2] >= 240 for name, values in canvas.calls))

    def test_duplicate_expired_invalid_and_excess_nodes_do_not_create_ghosts(self):
        supplied = peers(3)
        supplied += [dict(supplied[0]), dict(supplied[1], age_ms=6001),
                     dict(supplied[2], id=True), {"id": "x" * 25}, {"id": -1}]
        draw(swarm={"peers": supplied, "count": 99})
        self.assertEqual(sum(value is not None for value in fx._IDS), 3)
        draw(swarm={"peers": peers(40), "count": 40})
        self.assertEqual(sum(value is not None for value in fx._IDS), 12)
        draw(swarm={"peers": peers(40)}, quality=0)
        self.assertEqual(sum(value is not None for value in fx._IDS), 6)
        draw(swarm={"peers": []})
        self.assertEqual(sum(value is not None for value in fx._IDS), 0)

    def test_lower_detail_reduces_geometry_without_inventing_nodes(self):
        view = {"peers": peers(), "pulse": .8, "joined": .5}
        for scene in ("swarm", "planet"):
            high = draw(scene, view, quality=1)[1]
            low = draw(scene, view, quality=0)[1]
            self.assertLess(len(low.calls), len(high.calls) * .8)

    def test_malformed_wire_values_never_reach_native_ctx_as_nan(self):
        for bad in (None, "bad", True, float("nan"), float("inf"), -1e200):
            value = {"peers": [{"id": "abcd1234", "x": bad, "y": bad,
                                "colour": bad, "energy": bad, "joined": bad}],
                     "pulse": bad, "joined": bad, "phase": bad, "colour": bad}
            handled, canvas = draw(swarm=value, now=bad, quality=bad, burst=bad)
            self.assertTrue(handled)
            self.assertEqual(canvas.depth, 0)

    def test_peer_positions_are_artistic_bounded_and_cannot_hide_at_centre(self):
        source = [{"id": index, "x": x, "y": y, "colour": (0, 255, 255)}
                  for index, (x, y) in enumerate(((0, 0), (.01, .01), (1, 1), (-10000, 10000)))]
        draw(swarm={"peers": source})
        for index in range(4):
            radius = math.hypot(fx._PX[index], fx._PY[index])
            self.assertGreater(radius, 43)
            self.assertLess(radius, 98)

    def test_cached_geometry_is_time_based_and_inputs_are_unchanged(self):
        frame = {"scene": "swarm", "burst": .2}
        view = {"peers": peers(5), "energy": .5, "pulse": .2, "joined": .4, "colour": (180, 75, 255)}
        original = copy.deepcopy((frame, view))
        before = draw(swarm=view, now=2345)[1].calls
        identities = tuple(map(id, (fx._PX, fx._PY, fx._BX, fx._BY, fx._UNIT, fx._TRAVEL)))
        colours = tuple(map(id, fx._COLOUR[:5]))
        with patch.object(fx.math, "sin", side_effect=AssertionError("runtime trig")), \
             patch.object(fx.math, "cos", side_effect=AssertionError("runtime trig")), \
             patch.object(fx.math, "sqrt", side_effect=AssertionError("uncached position")):
            again = draw(swarm=view, now=2345)[1].calls
        self.assertEqual(before, again)
        self.assertEqual(colours, tuple(map(id, fx._COLOUR[:5])))
        self.assertEqual(identities, tuple(map(id, (fx._PX, fx._PY, fx._BX, fx._BY, fx._UNIT, fx._TRAVEL))))
        self.assertNotEqual(before, draw(swarm=view, now=3456)[1].calls)
        fx.draw(Canvas(), frame, view, 4000)
        self.assertEqual((frame, view), original)

    def test_remote_join_and_boost_are_visible_on_other_chapters(self):
        quiet = draw("terrain", {"peers": peers(2, False)})[1].calls
        join = draw("terrain", {"peers": peers(2, False), "joined": 1})[1].calls
        hit = draw("terrain", {"peers": peers(2), "pulse": 1})[1].calls
        self.assertNotEqual(quiet, join)
        self.assertNotEqual(quiet, hit)
        self.assertGreater(len(hit), len(quiet))

    def test_actual_model_beat_does_not_trigger_permanent_solo_nova(self):
        swarm = model.Swarm(b"loca", hue=32)
        frame = {"time_ms": 0, "paused": False}
        view = swarm.view(frame, 0)
        self.assertEqual(view["pulse"], 1)
        self.assertEqual(view["energy"], 0)
        self.assertFalse(draw("planet", view, now=0)[0])
        swarm.burst(1)
        self.assertTrue(draw("planet", swarm.view(frame, 1), now=1)[0])

    def test_actual_model_peer_freshness_is_distinct_from_join_and_hit(self):
        local, remote = model.Swarm(b"loca"), model.Swarm(b"peer")
        frame = {"time_ms": 0, "paused": False}
        self.assertTrue(local.receive(remote.packet(frame, 0), 0))
        arrival = local.view(frame, 0)
        self.assertEqual(arrival["joined"], 1)
        self.assertEqual(arrival["energy"], 0)
        draw("planet", arrival, now=0)
        self.assertEqual(fx._ENERGY[0], 0)
        self.assertEqual(fx._STRENGTH[0], 1)
        quiet_at = model.PULSE_MS + 1
        self.assertTrue(local.receive(remote.packet(frame, quiet_at), quiet_at))
        quiet = draw("planet", local.view(frame, quiet_at), now=quiet_at)[1]
        self.assertEqual(fx._ENERGY[0], 0)
        self.assertEqual(fx._JOIN[0], 0)
        self.assertEqual(fx._STRENGTH[0], 1)
        self.assertFalse(any(name == "arc" and values[2] > 10 for name, values in quiet.calls))
        hit_at = quiet_at + 100
        remote.burst(hit_at)
        self.assertTrue(local.receive(remote.packet(frame, hit_at), hit_at))
        hit = local.view(frame, hit_at)
        self.assertEqual(hit["energy"], 1)
        draw("planet", hit, now=hit_at)
        self.assertEqual(fx._ENERGY[0], 1)

    def test_native_failure_restores_parent_context(self):
        canvas = Canvas()
        def fail(*args):
            raise RuntimeError("native draw failure")
        canvas.arc = fail
        with self.assertRaises(RuntimeError):
            fx.draw(canvas, {"scene": "swarm"}, {"peers": peers(1)}, 0)
        self.assertEqual(canvas.depth, 0)


if __name__ == "__main__":
    unittest.main()
