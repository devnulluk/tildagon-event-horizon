"""Actual Event Horizon lifecycle and controls against firmware fakes."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def runtime(config=None):
    modules = {}
    def module(name, **values):
        result = types.ModuleType(name)
        result.__dict__.update(values)
        modules[name] = result
        return result
    class App:
        def __init__(self):
            self.terminations = []
            self._focused = True
        def terminate(self, restore_pattern=False):
            self.terminations.append(restore_pattern)
    class Buttons:
        def __init__(self, owner): self.values = set()
        def get(self, key): return key in self.values or key.replace("PHYSICAL_", "") in self.values
    class Leds(list):
        def __init__(self):
            super().__init__([(1, 2, 3)] * 19)
            self.writes = 0
        def write(self): self.writes += 1
    class Expansions:
        def __init__(self, owner, config):
            self.backend = object()
            self.keys = []
            self.closed = False
            self.eeh_frames = []
        def refresh(self, now): pass
        def pop_keys(self):
            keys, self.keys = self.keys, []
            return keys
        def close(self): self.closed = True
    class Space:
        def __init__(self, owner, config, **kwargs):
            self.config, self.events, self.tilt = config, [], (0, 0)
            self.closed = False
        def update(self): pass
        def pop(self):
            events, self.events = self.events, []
            return events
        def close(self): self.closed = True
    class Matrix:
        def __init__(self, *args, **kwargs):
            self.pending = False
            self.closed = False
            self.queued = []
            self.flushes = 0
            self.error = None
            self.entered = None
            self.release = None
            self.flushing = False
        def queue(self, frame, brightness, dark=False):
            self.queued.append((dict(frame), brightness, dark))
            self.pending = True
            return True
        async def flush(self):
            if self.closed or self.flushing: return 0
            self.flushing = True
            try:
                self.flushes += 1
                if self.entered: self.entered.set()
                if self.release: await self.release.wait()
                else: await asyncio.sleep(0)
                if self.error: raise self.error
                self.pending = False
                return 8
            finally:
                self.flushing = False
        def close(self): self.closed, self.pending = True, False
    def write_eeh(expansions, frame, brightness, dark=False):
        expansions.eeh_frames.append((dict(frame), brightness, dark))
        return not expansions.closed
    hardware = types.SimpleNamespace(leds=Leds(), set_led_power=lambda value: None)
    module("app", App=App)
    module("events")
    module("events.input", Buttons=Buttons)
    module("frontboards")
    module("frontboards.common", FRONTBOARD_BUTTON_TYPES={key: "PHYSICAL_" + key for key in "ABCDEF"})
    module("system")
    module("system.eventbus", eventbus=types.SimpleNamespace(emit=lambda event: None))
    module("system.patterndisplay")
    module("system.patterndisplay.events", PatternDisable=type("PatternDisable", (), {}))
    module("tildagonos", tildagonos=hardware)
    clock = module("time", now=0, microseconds=0)
    clock.ticks_ms = lambda: clock.now
    clock.ticks_us = lambda: clock.microseconds
    clock.ticks_diff = lambda current, previous: current - previous
    package = module("horizon_fixture")
    package.__path__ = [str(ROOT)]
    module("horizon_fixture.expansions", ExpansionManager=Expansions)
    module("horizon_fixture.space_inputs", SpaceInputs=Space)
    module("horizon_fixture.lights", DemoMatrix=Matrix, write_eeh=write_eeh)
    spec = importlib.util.spec_from_file_location("horizon_fixture.app", ROOT / "app.py")
    source = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(source)
    values = dict(source.DEFAULTS, **(config or {}))
    with patch.object(source, "load_config", return_value=values):
        instance = source.EventHorizon()
    return source, instance, hardware, clock


class Canvas:
    CENTER = 1
    MIDDLE = 2
    METHODS = {"rectangle": 4, "round_rectangle": 5, "arc": 6, "move_to": 2, "line_to": 2,
               "close_path": 0, "fill": 0, "stroke": 0, "rotate": 1, "translate": 2,
               "clip": 0, "text": 1}
    def __init__(self):
        self.depth = 0
        self.calls = []
        self.font_size = 12
    def save(self): self.depth += 1; return self
    def restore(self): self.depth -= 1; return self
    def rgb(self, *values): return self
    def text_width(self, value): return len(str(value)) * self.font_size * .5
    def __getattr__(self, name):
        if name not in self.METHODS: raise AssertionError("Unsupported API: " + name)
        def method(*args):
            if len(args) != self.METHODS[name]: raise AssertionError("Wrong API arity: " + name)
            self.calls.append((name, args))
            return self
        return method


class AppControlTests(unittest.TestCase):
    def test_export_and_timebase_use_wall_clock_not_update_argument_or_frame_count(self):
        source, app, hardware, clock = runtime()
        self.assertIs(source.__app_export__, source.EventHorizon)
        app.update(0)
        clock.now = 8500
        app.update(999999)
        self.assertEqual(app.show.position, 8500)
        self.assertEqual(app.show.frame()["scene"], "starflight")
        app.draw(Canvas())
        app.draw(Canvas())
        self.assertEqual(app.show.position, 8500)

    def test_keyboard_and_canonical_sensors_share_display_controls(self):
        source, app, hardware, clock = runtime()
        app.expansions.keys = ["RIGHT", "SPACE"]
        app.update(0)
        self.assertEqual(app.show.frame()["scene"], "starflight")
        self.assertTrue(app.show.paused)
        app.space.events = [{"kind": "joystick", "action": "left"}, {"kind": "joystick", "action": "confirm"}]
        app.update(0)
        self.assertEqual(app.show.frame()["scene"], "intro")
        self.assertFalse(app.show.paused)
        app.space.events = [{"kind": "touch", "action": "select", "pad": 12}]
        app.update(0)
        self.assertEqual(app.show.frame()["scene"], "finale")

    def test_button_held_from_menu_launch_requires_release_before_toggling_pause(self):
        source, app, hardware, clock = runtime()
        app.buttons.values = {"C"}
        app.update(0)
        self.assertFalse(app.show.paused)
        app.buttons.values.clear()
        app.update(0)
        app.buttons.values = {"C"}
        app.update(0)
        self.assertTrue(app.show.paused)
        app.update(0)
        self.assertTrue(app.show.paused)

    def test_hold_a_opens_settings_without_firing_a_short_boost(self):
        source, app, hardware, clock = runtime()
        app.update(0)
        app.buttons.values = {"A"}
        app.update(0)
        clock.now = 850
        app.update(0)
        self.assertTrue(app._settings)
        self.assertEqual(app.show.burst_until, 0)
        app.buttons.values.clear()
        app.update(0)
        self.assertEqual(app.show.burst_until, 0)

    def test_settings_capture_navigation_and_keep_independent_ceiling_values(self):
        source, app, hardware, clock = runtime()
        app._key("S")
        app.space.events = [{"kind": "joystick", "action": "down"}, {"kind": "joystick", "action": "right"}]
        app.update(0)
        self.assertEqual(app.config["ring_brightness"], .15)
        self.assertEqual(app.config["eeh_brightness"], .04)
        self.assertEqual(app.show.frame()["scene"], "intro")
        app._setting_row = 4
        app._setting_key("LEFT")
        self.assertFalse(app.config["space_tilt"])
        self.assertFalse(app.space.config["space_tilt"])
        app._setting_key("ENTER")
        self.assertFalse(app._settings)

    def test_light_writes_own_only_outer_ring_and_respect_separate_settings(self):
        source, app, hardware, clock = runtime({"ring_brightness": .10, "eeh_brightness": .03, "matrix_brightness": .07})
        app._write_lights()
        self.assertEqual(hardware.leds[0], (1, 2, 3))
        self.assertEqual(hardware.leds[13:], [(1, 2, 3)] * 6)
        self.assertTrue(all(0 <= channel <= 25 for colour in hardware.leds[1:13] for channel in colour))
        self.assertEqual(app.expansions.eeh_frames[-1][1], .03)
        self.assertEqual(app.matrix.queued[-1][1], .07)

    def test_all_cues_render_with_balanced_native_state(self):
        source, app, hardware, clock = runtime()
        for index in range(len(source.SCENES)):
            app.show.select(index)
            canvas = Canvas()
            app.draw(canvas)
            self.assertEqual(canvas.depth, 0)
        app._settings = True
        canvas = Canvas()
        app.draw(canvas)
        self.assertEqual(canvas.depth, 0)

    def test_render_failure_restores_both_context_layers(self):
        source, app, hardware, clock = runtime()
        app.show.select(1)
        canvas = Canvas()
        with patch.object(source.fx_cosmos, "render", side_effect=RuntimeError("Synthetic shader failure")):
            with self.assertRaisesRegex(RuntimeError, "Synthetic shader failure"):
                app.draw(canvas)
        self.assertEqual(canvas.depth, 0)

    def test_adaptive_quality_cannot_exceed_a_low_user_detail_ceiling(self):
        source, app, hardware, clock = runtime({"quality": .1})
        app.show.select(1)
        app.clock_ms = 1000
        def slow(*args):
            clock.microseconds += 100000
            return True
        with patch.object(source.fx_cosmos, "render", side_effect=slow):
            app.draw(Canvas())
        self.assertLessEqual(app._quality, .1)


class AppShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_stop_queues_one_dark_frame_and_terminates_once(self):
        source, app, hardware, clock = runtime()
        app._stop()
        app._stop()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(sum(dark for frame, brightness, dark in app.matrix.queued), 1)
        self.assertTrue(app.space.closed)
        self.assertTrue(app.expansions.closed)
        self.assertTrue(app.matrix.closed)
        self.assertEqual(app.terminations, [True])
        self.assertEqual(hardware.leds[1:13], [(0, 0, 0)] * 12)

    async def test_finish_stop_closes_and_terminates_even_if_flush_raises(self):
        source, app, hardware, clock = runtime()
        app._stopping = True
        app.matrix.pending = True
        app.matrix.error = RuntimeError("Synthetic matrix failure")
        try:
            await app._finish_stop()
        except RuntimeError:
            pass
        self.assertTrue(app.matrix.closed)
        self.assertEqual(app.terminations, [True])

    async def test_background_cancellation_closes_expansions_and_darkens_only_owned_leds(self):
        source, app, hardware, clock = runtime()
        app._write_lights()
        app.matrix.entered, app.matrix.release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(app.background_task())
        await app.matrix.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(app.matrix.closed and app.space.closed and app.expansions.closed)
        self.assertEqual(hardware.leds[1:13], [(0, 0, 0)] * 12)
        self.assertEqual(hardware.leds[0], (1, 2, 3))
        self.assertEqual(hardware.leds[13:], [(1, 2, 3)] * 6)
        self.assertEqual(app.terminations, [True])

    async def test_stop_while_worker_flush_is_pending_does_not_double_terminate(self):
        source, app, hardware, clock = runtime()
        app.matrix.entered, app.matrix.release = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(app.background_task())
        await app.matrix.entered.wait()
        app._stop()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        app.matrix.release.set()
        await asyncio.wait_for(task, 1)
        self.assertTrue(app.matrix.closed)
        self.assertEqual(app.terminations, [True])


if __name__ == "__main__":
    unittest.main()
