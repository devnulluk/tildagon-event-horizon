"""Wall-clock choreography, pause and brightness ceilings; no hardware."""
import importlib.util
import math
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "show.py"
spec = importlib.util.spec_from_file_location("horizon_show_under_test", PATH)
show = importlib.util.module_from_spec(spec)
spec.loader.exec_module(show)


class ShowTests(unittest.TestCase):
    def test_scene_durations_and_boundaries_match_the_two_minute_score(self):
        self.assertEqual(show.TOTAL_MS, 120000)
        self.assertEqual([row[2] for row in show.SCENES], [8000, 16000, 16000, 16000, 16000, 16000, 20000, 12000])
        performance = show.Show()
        for index, start in enumerate(show.STARTS):
            performance.position = start
            frame = performance.frame()
            self.assertEqual((frame["index"], frame["local_ms"], frame["phase"]), (index, 0, 0))
            performance.position = start + show.SCENES[index][2] - 1
            self.assertEqual(performance.frame()["index"], index)
            self.assertLess(performance.frame()["phase"], 1)

    def test_skipped_frames_advance_by_elapsed_time_and_wrap_without_extra_cues(self):
        direct, fragmented = show.Show(), show.Show()
        direct.advance(120000 * 3 + 97000)
        for delta in (17000, 50000, 30000, 120000, 120000, 120000):
            fragmented.advance(delta)
        self.assertEqual(direct.frame(), fragmented.frame())
        self.assertEqual(direct.frame()["scene"], "blackhole")

    def test_pause_preserves_scene_and_phase_but_expires_interactive_burst(self):
        performance = show.Show()
        performance.advance(9500)
        performance.toggle()
        before = performance.frame()
        performance.burst()
        self.assertEqual(performance.frame()["burst"], 1)
        performance.advance(5000)
        after = performance.frame()
        self.assertEqual((after["time_ms"], after["phase"]), (before["time_ms"], before["phase"]))
        self.assertEqual(after["elapsed_ms"], before["elapsed_ms"] + 5000)
        self.assertEqual(after["burst"], 0)
        performance.toggle()
        performance.advance(500)
        self.assertEqual(performance.position, 10000)

    def test_manual_scene_selection_wraps_without_unpausing(self):
        performance = show.Show()
        performance.toggle()
        performance.next(-1)
        self.assertEqual(performance.frame()["scene"], "finale")
        performance.next(1)
        self.assertEqual(performance.frame()["scene"], "intro")
        performance.select(4)
        self.assertEqual(performance.frame()["scene"], "planet")
        self.assertEqual(performance.frame()["phase"], 0)
        self.assertTrue(performance.paused)

    def test_invalid_or_negative_delta_never_corrupts_the_score(self):
        performance = show.Show()
        performance.advance(750)
        before = performance.frame()
        for value in (-1, True, None, "500", math.inf, math.nan):
            performance.advance(value)
            self.assertEqual(performance.frame(), before)

    def test_beat_frequency_is_120_bpm_and_independent_of_frame_rate(self):
        performance = show.Show()
        samples = []
        for value in (0, 125, 250, 375, 500):
            performance.position = value
            frame = performance.frame()
            self.assertEqual(frame["beat"], (value % 500) / 500)
            self.assertTrue(0 <= frame["pulse"] <= 1)
            samples.append(frame["pulse"])
        self.assertEqual(samples[0], samples[-1])
        self.assertGreater(max(samples) - min(samples), .9)

    def test_every_light_scene_respects_each_independent_brightness_ceiling(self):
        performance = show.Show()
        for scene in range(len(show.SCENES)):
            performance.select(scene)
            performance.burst()
            for brightness in (0, .03, .15, .5, 1):
                for count in (12, 14):
                    frame = show.light_frame(performance.frame(), brightness, count)
                    self.assertEqual(len(frame), count)
                    self.assertTrue(all(type(channel) is int and 0 <= channel <= int(brightness * 255)
                                        for colour in frame for channel in colour))

    def test_light_animation_is_deterministic_and_contains_no_unbounded_channels(self):
        performance = show.Show()
        first = show.light_frame(performance.frame())
        performance.advance(650)
        self.assertNotEqual(first, show.light_frame(performance.frame()))
        performance.position = 0
        self.assertEqual(first, show.light_frame(performance.frame()))
        for brightness in (math.inf, math.nan, True, "bad", None):
            frame = show.light_frame(performance.frame(), brightness)
            self.assertTrue(all(0 <= value <= 38 for colour in frame for value in colour))


if __name__ == "__main__":
    unittest.main()
