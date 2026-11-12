"""Native-like BLE lifecycle/parser checks; no actual Bluetooth or network."""
from array import array
import importlib.util
from pathlib import Path
import unittest
import uuid

PATH = Path(__file__).resolve().parents[1] / "ble_link.py"
spec = importlib.util.spec_from_file_location("nearby_ble_under_test", PATH)
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


class BLE:
    def __init__(self, active=False):
        self.on = active
        self.calls = []
        self.handler = None
        self.fail = None
    def active(self, value=None, /):
        self.calls.append(("active", value))
        if value is not None:
            self.on = value
            if self.fail == "activate" and value: raise OSError("Sensitive synthetic error")
        return self.on
    def irq(self, handler, /):
        self.calls.append(("irq", handler))
        self.handler = handler
        if self.fail == "irq" and handler is not None: raise OSError("Sensitive synthetic error")
    def gap_scan(self, duration, interval=1280000, window=11250, active=False, /):
        self.calls.append(("scan", duration, interval, window, active))
        if self.fail == "scan" and duration is not None: raise OSError("Sensitive synthetic error")
        if self.fail == "scan_stop" and duration is None: raise OSError("Sensitive synthetic error")
        if duration is None and self.handler: self.handler(6, None)
    def gap_advertise(self, interval, data=None, *, connectable=True):
        self.calls.append(("advertise", interval, data, connectable))
        if self.fail == "advertise" and interval is not None: raise OSError("Sensitive synthetic error")
    def config(self, *args, **kwargs):
        raise AssertionError("Transport must not alter BLE global configuration")


class NearbyRadioTests(unittest.TestCase):
    def setUp(self): self.radios = []
    def tearDown(self):
        for radio in self.radios: radio.close()
        self.assertIsNone(link._OWNER)

    def radio(self, backend=None, enabled=True):
        backend = BLE() if backend is None else backend
        radio = link.NearbyRadio(enabled=enabled, backend=backend)
        self.radios.append(radio)
        return radio, backend

    def receive(self, ble, payload=b"0123456789", rssi=-61, adv_type=3):
        ble.handler(5, (0, memoryview(b"123456"), adv_type, rssi, memoryview(link.advertisement(payload))))

    def test_legacy_advertisement_is_exactly31_bytes_with_correct_full_uuid_endian(self):
        wire = link.advertisement(b"0123456789")
        self.assertEqual(len(wire), 31)
        self.assertEqual(wire[:5], b"\x02\x01\x06\x1b\x21")
        self.assertEqual(link.SERVICE_UUID_LE, uuid.UUID(link.SERVICE_UUID).bytes[::-1])
        self.assertNotEqual(link.SERVICE_UUID_LE, uuid.UUID(link.SERVICE_UUID).bytes_le)
        self.assertEqual(link.extract(wire), b"0123456789")
        self.assertEqual(link.extract(wire[3:]), b"0123456789")
        self.assertEqual(link.extract(wire[3:] + wire[:3]), b"0123456789")

    def test_parser_rejects_wrong_uuid_lengths_extended_frames_and_malformed_ads(self):
        wire = link.advertisement(b"0123456789")
        cases = (None, [], b"", wire[:-1], wire + b"x", b"\x40" + wire[1:],
                 b"\x02\x01\x06\x1b\x20" + wire[5:],
                 wire[:5] + bytes([wire[5] ^ 1]) + wire[6:],
                 b"\x00" + wire[1:], b"\x02\x01\x06\x1a\x21" + wire[5:])
        for data in cases:
            with self.subTest(data=data): self.assertIsNone(link.extract(data))
        with self.assertRaises(ValueError): link.advertisement(b"too-short")
        with self.assertRaises(ValueError): link.advertisement(memoryview(array("I", [0] * 10)))

    def test_constructor_is_lazy_and_start_claims_only_an_inactive_radio(self):
        radio, ble = self.radio()
        self.assertEqual(ble.calls, [])
        self.assertTrue(radio.start())
        self.assertTrue(radio.running)
        self.assertEqual(radio.status_code, "ready")
        self.assertEqual([c for c in ble.calls if c[0] == "scan"], [("scan", 0, 240000, 40000, False)])
        self.assertEqual([c for c in ble.calls if c[0] == "advertise"], [])
        calls = len(ble.calls)
        self.assertTrue(radio.start())
        self.assertEqual(len(ble.calls), calls)

    def test_active_foreign_singleton_is_not_modified_even_on_close(self):
        foreign = BLE(active=True)
        radio, ble = self.radio(foreign)
        self.assertFalse(radio.start())
        self.assertEqual(radio.status_code, "busy")
        radio.close()
        self.assertEqual(ble.calls, [("active", None)])
        self.assertTrue(ble.on)

    def test_two_instances_cannot_claim_and_clobber_each_other(self):
        first, ble1 = self.radio()
        second, ble2 = self.radio()
        self.assertTrue(first.start())
        self.assertFalse(second.start())
        self.assertEqual(ble2.calls, [])
        first.close()
        self.assertTrue(second.start())
        self.assertTrue(ble2.on)

    def test_start_failures_cleanup_all_owned_steps_and_hide_exception_text(self):
        for failure in ("activate", "irq", "scan"):
            with self.subTest(failure=failure):
                radio, ble = self.radio()
                ble.fail = failure
                self.assertFalse(radio.start())
                self.assertFalse(radio.running)
                self.assertFalse(ble.on)
                self.assertIsNone(ble.handler)
                self.assertIsNone(link._OWNER)
                self.assertEqual(radio.status_code, "error")
                self.assertNotIn("Sensitive", radio.status)

    def test_advertising_is_non_connectable_and_updates_no_more_than_twice_per_second(self):
        radio, ble = self.radio()
        radio.start()
        self.assertTrue(radio.send(b"0123456789", 0))
        self.assertFalse(radio.send(b"1123456789", 499))
        self.assertTrue(radio.send(b"0123456789", 499))
        self.assertTrue(radio.send(b"1123456789", 500))
        sends = [call for call in ble.calls if call[0] == "advertise"]
        self.assertEqual(len(sends), 2)
        self.assertTrue(all(call[1] == 250000 and call[3] is False for call in sends))
        self.assertTrue(all(len(call[2]) == 31 for call in sends))
        self.assertEqual((radio.tx, radio.tx_count), (2, 2))
        self.assertEqual(radio.status_code, "ready")

    def test_invalid_send_values_do_not_touch_the_radio_or_oversize_the_packet(self):
        radio, ble = self.radio()
        radio.start()
        before = list(ble.calls)
        for data in (None, b"short", b"x" * 11, "0123456789", memoryview(array("I", [0] * 10))):
            self.assertFalse(radio.send(data, 0))
        for now in (None, True, -1, "500", float("nan"), float("inf")):
            self.assertFalse(radio.send(b"0123456789", now))
        self.assertEqual(ble.calls, before)

    def test_received_transient_memoryviews_are_copied_and_no_address_is_returned(self):
        radio, ble = self.radio()
        radio.start()
        backing = bytearray(link.advertisement(b"0123456789"))
        ble.handler(5, (0, memoryview(b"123456"), 3, -61, memoryview(backing)))
        backing[:] = b"\0" * len(backing)
        self.assertEqual(radio.poll(), [(b"0123456789", -61)])
        self.assertEqual(radio.poll(), [])
        self.assertEqual((radio.rx, radio.rx_count), (1, 1))

    def test_rx_queue_is_bounded_and_keeps_freshest_frames(self):
        radio, ble = self.radio()
        radio.start()
        for index in range(20): self.receive(ble, bytes([index]) * 10)
        received = radio.poll()
        self.assertEqual(len(received), 16)
        self.assertEqual([value[0][0] for value in received], list(range(4, 20)))
        self.assertEqual((radio.rx_count, radio.dropped), (20, 4))

    def test_other_events_scan_responses_and_malformed_peers_do_not_escape_irq(self):
        radio, ble = self.radio()
        radio.start()
        for event, data in ((1, None), (5, None), (5, ()), (5, (0, b"a", 3, -50, b"bad"))):
            ble.handler(event, data)
        self.receive(ble, adv_type=4)
        self.assertEqual(radio.poll(), [])
        self.receive(ble, rssi="bad")
        self.assertEqual(radio.poll(), [(b"0123456789", None)])

    def test_scan_completion_is_restarted_only_outside_callback(self):
        radio, ble = self.radio()
        radio.start()
        before = len(ble.calls)
        ble.handler(6, None)
        self.assertEqual(len(ble.calls), before)
        radio.poll()
        self.assertEqual(len([call for call in ble.calls if call[0] == "scan"]), 2)
        radio.poll()
        self.assertEqual(len([call for call in ble.calls if call[0] == "scan"]), 2)

    def test_disable_can_restart_but_terminal_close_never_resurrects(self):
        radio, ble = self.radio()
        radio.start()
        self.assertTrue(radio.set_enabled(False))
        self.assertFalse(ble.on)
        self.assertEqual(radio.status_code, "disabled")
        self.assertTrue(radio.set_enabled(True))
        self.assertTrue(ble.on)
        handler = ble.handler
        radio.close()
        calls = len(ble.calls)
        handler(5, (0, b"123456", 3, -50, link.advertisement(b"0123456789")))
        radio.close()
        self.assertFalse(radio.start())
        self.assertFalse(radio.set_enabled(True))
        self.assertEqual(len(ble.calls), calls)
        self.assertEqual(radio.poll(), [])
        self.assertIsNone(ble.handler)

    def test_one_cleanup_failure_cannot_skip_remaining_cleanup(self):
        radio, ble = self.radio()
        radio.start()
        ble.fail = "scan_stop"
        radio.close()
        self.assertFalse(ble.on)
        self.assertIsNone(ble.handler)
        self.assertTrue(any(call[0] == "advertise" and call[1] is None for call in ble.calls))

    def test_failed_advertise_discards_ownership_and_returns_fixed_status(self):
        radio, ble = self.radio()
        radio.start()
        ble.fail = "advertise"
        self.assertFalse(radio.send(b"0123456789", 0))
        self.assertFalse(radio.running)
        self.assertFalse(ble.on)
        self.assertEqual(radio.status, "NEARBY RADIO ERROR")


if __name__ == "__main__": unittest.main()
