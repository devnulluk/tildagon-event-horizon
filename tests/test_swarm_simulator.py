"""Virtual peer bus uses production wire/model data; no physical-radio claims."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


lab_module = load("horizon_virtual_air_test", "simulator/swarm_lab.py")
protocol = load("horizon_virtual_protocol_test", "swarm.py")
show = load("horizon_virtual_show_test", "show.py")
wire = load("horizon_virtual_peer_wire_test", "ble_link.py")


class AirTests(unittest.TestCase):
    def test_real_service_data_wrapper_and_parser_are_used(self):
        air = lab_module.Air(wire)
        sender, receiver = air.radio("A"), air.radio("B")
        sender.start(); receiver.start()
        payload = protocol.Swarm(b"abcd").packet({"time_ms": 0}, 0)
        self.assertTrue(sender.send(payload, 0))
        self.assertEqual(len(sender.advert), 31)
        self.assertEqual(wire.extract(sender.advert), payload)
        air.tick(0)
        self.assertEqual(receiver.poll(), [(payload, -52)])

    def test_repeated_advertising_is_visible_but_does_not_refresh_model_ttl(self):
        air = lab_module.Air(wire)
        sender, receiver = air.radio("A"), air.radio("B")
        sender.start(); receiver.start()
        payload = protocol.Swarm(b"abcd").packet({"time_ms": 0}, 0)
        model = protocol.Swarm(b"efgh")
        sender.send(payload, 0)
        for now in range(0, 6250, 250):
            air.tick(now)
            for message, rssi in receiver.poll():
                model.receive(message, now, rssi)
        self.assertGreater(receiver.rx, 20)
        self.assertEqual(model.view({"time_ms": 0}, 6000)["count"], 0)

    def test_changes_are_limited_to_two_hz_and_payloads_are_copied(self):
        air = lab_module.Air()
        radio = air.radio("A"); radio.start()
        payload = bytearray(b"0123456789")
        self.assertTrue(radio.send(payload, 0))
        payload[0] = 99
        self.assertEqual(radio.advert, b"0123456789")
        self.assertFalse(radio.send(payload, 499))
        self.assertTrue(radio.send(payload, 500))
        self.assertTrue(radio.send(payload, 501))
        self.assertEqual(radio.tx, 2)

    def test_receive_and_delayed_air_queues_are_bounded(self):
        air = lab_module.Air(jitter_ms=1000)
        radios = [air.radio(str(index)) for index in range(16)]
        for radio in radios:
            radio.start(); radio.send(b"0123456789", 0)
        for now in range(0, 20000, 250):
            air.tick(now)
            self.assertLessEqual(len(air.pending), 64)
            self.assertTrue(all(len(radio.queue) <= 16 for radio in radios))
        self.assertGreater(air.dropped + sum(radio.dropped for radio in radios), 0)

    def test_loss_and_jitter_are_deterministic_and_poll_is_bounded(self):
        def run():
            air = lab_module.Air(drop_every=3, jitter_ms=400)
            sender, receiver = air.radio("A"), air.radio("B")
            sender.start(); receiver.start(); sender.send(b"0123456789", 0)
            outcomes = []
            for now in range(0, 3000, 100):
                air.tick(now)
                outcomes.append((now, len(receiver.poll()), air.dropped))
            return outcomes
        self.assertEqual(run(), run())
        self.assertTrue(any(count == 0 for now, count, dropped in run()))

    def test_disable_clears_air_and_close_is_terminal(self):
        air = lab_module.Air()
        radio = air.radio("A"); radio.start(); radio.send(b"0123456789", 0)
        self.assertTrue(radio.set_enabled(False))
        self.assertIsNone(radio.advert)
        self.assertFalse(radio.running)
        self.assertTrue(radio.set_enabled(True))
        radio.close()
        self.assertFalse(radio.start())
        self.assertFalse(radio.set_enabled(True))
        self.assertFalse(radio.send(b"0123456789", 1000))


class LabTests(unittest.TestCase):
    def test_three_production_models_join_burst_handover_and_expire_through_real_packets(self):
        lab = lab_module.SwarmLab(protocol.Swarm, show.Show, wire)
        radio = lab.factory(); radio.start()
        main = protocol.Swarm(lab.MAIN_ID, 200)
        main_show = show.Show()
        counts, roles, echoes, packet_counter = {}, {}, 0, 0
        for now in range(0, 60001, 100):
            main_show.advance(100)
            lab.advance(now)
            frame = dict(main_show.frame(), paused=main_show.paused)
            if now % 500 == 0:
                message = main.packet(frame, now)
                packet_counter = message[6]
                radio.send(message, now)
            for message, rssi in radio.poll()[:4]:
                main.receive(message, now, rssi)
            if main.consume_burst(now):
                echoes += 1
                main_show.burst()
            state = main.view(frame, now)
            if now in (0, 13000, 22000, 46000, 60000):
                counts[now], roles[now] = state["count"], state["role"]
        self.assertEqual(counts, {0: 0, 13000: 1, 22000: 2, 46000: 1, 60000: 0})
        self.assertEqual(roles[22000], "follower")
        self.assertEqual(roles[46000], "conductor")
        self.assertEqual(roles[60000], "solo")
        self.assertEqual(echoes, 2)
        self.assertEqual(packet_counter, 0, "Remote echoes must never be re-advertised as local bursts")
        snapshot = lab.snapshot(60000)
        self.assertTrue(snapshot["synthetic_radio"])
        self.assertFalse(snapshot["physical_multibadge_test"])
        lab.close()
        self.assertTrue(all(radio.closed for radio in lab.air.radios))
        self.assertEqual(lab.air.pending, [])

    def test_warmup_does_not_start_the_peer_script_until_capture_is_ready(self):
        lab = lab_module.SwarmLab(protocol.Swarm, show.Show, wire)
        for now in (0, 5000, 10000):
            lab.advance(now, active=False)
        self.assertEqual(lab.elapsed, 0)
        self.assertTrue(all(not peer["radio"].running for peer in lab.peers))
        lab.advance(10000)
        lab.advance(16000)
        self.assertEqual(lab.elapsed, 6000)
        self.assertTrue(lab.peers[0]["radio"].running)

    def test_channel_is_explicitly_synthetic_and_no_radio_scheduler_is_claimed(self):
        lab = lab_module.SwarmLab(protocol.Swarm, show.Show, wire)
        radio = lab.factory(clock=lambda: 0)
        self.assertEqual(radio.channel, 1)
        self.assertEqual(radio.transport, "virtual-espnow")
        self.assertFalse(radio.physical_active)
        snapshot = lab.snapshot(0)
        self.assertEqual(snapshot["synthetic_channel"], 1)
        self.assertIn("ESP-NOW", snapshot["reference_transport"])
        self.assertFalse(snapshot["real_radio_adapter_used"])
        self.assertFalse(snapshot["native_radio_scheduler_exercised"])


if __name__ == "__main__":
    unittest.main()
