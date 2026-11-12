"""Production wire/state tests with synthetic sessions; no radio or hardware."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "swarm.py"
SPEC = importlib.util.spec_from_file_location("horizon_swarm_under_test", PATH)
swarm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(swarm)


def frame(position=0, paused=False):
    return {"time_ms": position, "paused": paused}


def node(value, hue=40):
    return swarm.Swarm(bytes((0, 0, 0, value)), hue)


def packet(sender=2, sequence=0, burst=0, position=0, paused=False, hue=90):
    units = position // 8
    return bytes((0x11 if paused else 0x10, 0, 0, 0, sender, sequence, burst,
                  units >> 8, units & 255, hue))


class SwarmTests(unittest.TestCase):
    def test_exact_ten_byte_layout_quantization_paused_flag_and_sequence_wrap(self):
        value = swarm.Swarm(b"\x01\x02\x03\x04", 255)
        self.assertEqual(value.packet(frame(139999, True), 0), b"\x11\x01\x02\x03\x04\x00\x00\x44\x5b\xff")
        for now in range(1, 256):
            self.assertEqual(value.packet(frame(), now)[5], now)
        self.assertEqual(value.packet(frame(), 256)[5], 0)

    def test_bad_constructor_values_are_rejected(self):
        for identifier in (b"", b"123", b"12345", "1234", 12, bytearray(4)):
            with self.assertRaises(ValueError):
                swarm.Swarm(identifier)
        for hue in (-1, 256, True, "1", None):
            if hue is not None:
                with self.assertRaises(ValueError):
                    swarm.Swarm(b"1234", hue)

    def test_packet_rejects_invalid_local_time_and_frame(self):
        value = node(1)
        for local in (None, {}, frame(-1), frame(140000), frame(True), frame(1, "yes")):
            with self.assertRaises(ValueError):
                value.packet(local, 0)
        for now in (None, True, -1, float("nan")):
            with self.assertRaises(ValueError):
                value.packet(frame(), now)

    def test_version_reserved_flags_length_and_score_bounds_fail_closed(self):
        value = node(1)
        good = packet()
        for payload in (None, "x" * 10, b"", good[:-1], good + b"x",
                        bytes((0x20,)) + good[1:], bytes((0x12,)) + good[1:],
                        packet(position=140000), packet(position=524280)):
            self.assertFalse(value.receive(payload, 0))
        self.assertEqual(value.view(frame(), 0)["count"], 0)

    def test_first_sequence_zero_is_valid_and_self_echo_is_ignored(self):
        value = node(1)
        self.assertFalse(value.receive(packet(sender=1), 0))
        self.assertTrue(value.receive(packet(sequence=0), 0))
        self.assertEqual(value.view(frame(), 0)["count"], 1)

    def test_duplicate_out_of_order_and_half_window_packets_do_not_refresh_ttl(self):
        value = node(1)
        self.assertTrue(value.receive(packet(sequence=20), 0))
        for sequence in (20, 19, 148):
            self.assertFalse(value.receive(packet(sequence=sequence), 5000))
        self.assertEqual(value.view(frame(), 5999)["count"], 1)
        self.assertEqual(value.view(frame(), 6000)["count"], 0)
        self.assertFalse(value.receive(packet(sequence=20), 6001))
        self.assertTrue(value.receive(packet(sequence=21), 6002))

    def test_valid_sequence_wrap_and_largest_forward_delta_are_accepted(self):
        value = node(1)
        for sequence in (254, 255, 0, 127):
            self.assertTrue(value.receive(packet(sequence=sequence), sequence + 1000 if sequence >= 254 else sequence + 2000))

    def test_invalid_or_backwards_receive_clock_cannot_change_state(self):
        value = node(1)
        self.assertTrue(value.receive(packet(), 100))
        for now in (99, -1, True, None, float("nan")):
            self.assertFalse(value.receive(packet(sequence=1), now))
        self.assertEqual(value.view(frame(), 100)["peers"][0]["age_ms"], 0)

    def test_first_burst_counter_is_baseline_then_remote_event_is_consumed_once(self):
        value = node(1)
        value.receive(packet(burst=99), 0)
        self.assertFalse(value.consume_burst(0))
        self.assertTrue(value.receive(packet(sequence=1, burst=100), 500))
        self.assertTrue(value.consume_burst(500))
        self.assertFalse(value.consume_burst(500))
        self.assertEqual(value.packet(frame(), 500)[6], 0)

    def test_local_bursts_are_advertised_and_remote_echoes_never_increment_them(self):
        value = node(1)
        value.burst(0)
        self.assertEqual(value.packet(frame(), 0)[6], 1)
        value.receive(packet(), 0)
        value.receive(packet(sequence=1, burst=1), 500)
        self.assertTrue(value.consume_burst(500))
        self.assertEqual(value.packet(frame(), 500)[6], 1)

    def test_burst_wrap_rate_limit_and_repeat_do_not_create_delayed_echoes(self):
        value = node(1)
        value.receive(packet(burst=255), 0)
        value.receive(packet(sequence=1, burst=0), 1)
        self.assertTrue(value.consume_burst(1))
        value.receive(packet(sequence=2, burst=1), 100)
        self.assertFalse(value.consume_burst(100))
        value.receive(packet(sequence=3, burst=1), 501)
        self.assertFalse(value.consume_burst(501))
        value.receive(packet(sequence=4, burst=2), 502)
        self.assertTrue(value.consume_burst(502))

    def test_pending_remote_events_coalesce_and_expire_without_a_queue(self):
        value = node(1)
        for sender in (2, 3, 4):
            value.receive(packet(sender=sender), 0)
            value.receive(packet(sender=sender, sequence=1, burst=1), 500)
        self.assertTrue(value.consume_burst(500))
        self.assertFalse(value.consume_burst(500))
        value.receive(packet(sequence=2, burst=2), 1000)
        self.assertFalse(value.consume_burst(2501))

    def test_backwards_burst_counter_cannot_rewind_the_event_baseline(self):
        value = node(1)
        value.receive(packet(burst=10), 0)
        value.receive(packet(sequence=1, burst=9), 500)
        self.assertFalse(value.consume_burst(500))
        value.receive(packet(sequence=2, burst=10), 1000)
        self.assertFalse(value.consume_burst(1000))
        value.receive(packet(sequence=3, burst=11), 1500)
        self.assertTrue(value.consume_burst(1500))

    def test_peer_and_sequence_history_memory_remain_bounded_under_many_sessions(self):
        value = node(0)
        for sender in range(1, 90):
            value.receive(packet(sender=sender), sender * 6000)
            self.assertLessEqual(len(value._peers), 12)
            self.assertLessEqual(len(value._history), 24)
        crowded = node(0)
        for sender in range(1, 40):
            crowded.receive(packet(sender=sender), 0)
        self.assertEqual(crowded.view(frame(), 0)["count"], 12)

    def test_lowest_unpaused_node_is_conductor_without_rewriting_local_scene_or_pause(self):
        value = node(3, 30)
        value.receive(packet(sender=1, position=1000, hue=20), 0)
        value.receive(packet(sender=2, position=2000, hue=90), 0)
        local = frame(99000)
        result = value.view(local, 250)
        self.assertEqual(result["leader_id"], "00000001")
        self.assertEqual(result["role"], "follower")
        self.assertEqual(result["phase"], .5)
        self.assertEqual(local, frame(99000))
        value.receive(packet(sender=1, sequence=1, position=1000, paused=True), 250)
        self.assertEqual(value.view(local, 250)["leader_id"], "00000002")

    def test_solo_and_all_paused_roles_are_explicit(self):
        value = node(1)
        self.assertEqual(value.view(frame(), 0)["role"], "solo")
        self.assertEqual(value.view(frame(1232, True), 0)["role"], "paused")
        value.receive(packet(sender=2, paused=True), 0)
        self.assertEqual(value.view(frame(1232, True), 0)["role"], "paused")

    def test_artistic_coordinates_are_stable_independent_of_rssi_and_colours_are_bounded(self):
        left, right = node(1), node(1)
        left.receive(packet(), 0, rssi=-20)
        right.receive(packet(), 0, rssi=-99)
        a, b = left.view(frame(), 0)["peers"][0], right.view(frame(), 0)["peers"][0]
        self.assertEqual((a["x"], a["y"]), (b["x"], b["y"]))
        self.assertTrue(-1 <= a["x"] <= 1 and -1 <= a["y"] <= 1)
        self.assertTrue(all(type(channel) is int and 0 <= channel <= 255 for channel in a["colour"]))

    def test_view_joins_bursts_and_energy_fade_but_paused_peer_phase_does_not_advance(self):
        value = node(1)
        value.receive(packet(paused=True, position=1232), 0)
        first = value.view(frame(), 0)
        later = value.view(frame(), 1600)
        self.assertEqual(first["joined"], 1)
        self.assertEqual(later["joined"], 0)
        self.assertEqual(first["peers"][0]["phase"], later["peers"][0]["phase"])
        for state in (first, later):
            for key in ("phase", "pulse", "joined", "energy"):
                self.assertTrue(0 <= state[key] <= 1)

    def test_clear_discards_remote_state_and_keeps_own_session_hue_and_counters(self):
        value = node(1, 123)
        value.burst(0)
        before = value.packet(frame(), 0)
        value.receive(packet(), 0)
        value.receive(packet(sequence=1, burst=1), 500)
        value.clear()
        self.assertFalse(value.consume_burst(500))
        self.assertEqual(value.view(frame(), 500)["count"], 0)
        self.assertEqual(value.view(frame(), 500)["joined"], 0)
        self.assertEqual(value._history, {})
        after = value.packet(frame(), 500)
        self.assertEqual(after[1:5], before[1:5])
        self.assertEqual(after[9], before[9])
        self.assertEqual(after[6], before[6])
        self.assertEqual(after[5], (before[5] + 1) & 255)

    def test_expired_sequence_history_eventually_allows_a_legitimate_long_absence(self):
        value = node(1)
        value.receive(packet(sequence=50), 0)
        self.assertFalse(value.receive(packet(sequence=200), 6000))
        self.assertTrue(value.receive(packet(sequence=200), 30000))
        self.assertFalse(value.consume_burst(30000))


if __name__ == "__main__":
    unittest.main()
