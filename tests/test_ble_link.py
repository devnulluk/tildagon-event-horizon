"""Shared ESP-NOW broker adapter checks; no actual radio, USB or network."""
from array import array
import importlib.util
import uuid
from pathlib import Path
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


link=load("nearby_espnow_adapter_under_test",ROOT/"ble_link.py")
wire=link
model=load("nearby_espnow_visual_model",ROOT/"swarm.py")


class Event:
    def __init__(self,msg,rssi=-50):self.msg,self.rssi=msg,rssi
    @property
    def mac(self):raise AssertionError("Adapter must not inspect device addresses")


class Bus:
    def __init__(self):self.listeners=[];self.removed=[];self.fail=False
    def remove(self,event_type,callback,owner):
        if self.fail:raise OSError("Sensitive synthetic remove failure")
        self.removed.append((event_type,callback,owner))
        item=(event_type,callback,owner)
        if item in self.listeners:self.listeners.remove(item)


class Broker:
    def __init__(self,bus):
        self.bus=bus;self.calls=[];self.wifi_channel=6
        self.fail_subscribe=False;self.fail_send=False;self.accept_send=True
    def subscribe(self,handler,app,predicate=None):
        if self.fail_subscribe:raise OSError("Sensitive synthetic subscribe failure")
        def wrapped(event):
            if predicate is None or predicate(event):handler(event)
        self.calls.append(("subscribe",wrapped,app,predicate))
        self.bus.listeners.append((Event,wrapped,app))
        return wrapped
    def send(self,data,mac=None,sync=True):
        self.calls.append(("send",bytes(data),mac,sync))
        if self.fail_send:raise OSError("Sensitive synthetic send failure")
        return self.accept_send
    def deliver(self,event):
        for event_type,callback,owner in tuple(self.bus.listeners):
            if isinstance(event,event_type):callback(event)
    def __getattr__(self,name):
        if name in ("active","deinit","irq","add_peer","del_peer","config","recv","irecv","aen"):
            raise AssertionError("Shared radio operation forbidden: "+name)
        raise AttributeError(name)


class BrokerAdapterTests(unittest.TestCase):
    def radio(self,enabled=True):
        bus=Bus();broker=Broker(bus);owner=object()
        radio=link.ESPNowNearbyRadio(owner,enabled,broker,bus,Event)
        self.addCleanup(radio.close)
        return radio,broker,bus,owner

    def test_legacy_advertisement_is_exactly31_bytes_with_correct_full_uuid_endian(self):
        wire = link.advertisement(b'0123456789')
        self.assertEqual(len(wire), 31)
        self.assertEqual(wire[:5], b'\x02\x01\x06\x1b!')
        self.assertEqual(link.SERVICE_UUID_LE, uuid.UUID(link.SERVICE_UUID).bytes[::-1])
        self.assertNotEqual(link.SERVICE_UUID_LE, uuid.UUID(link.SERVICE_UUID).bytes_le)
        self.assertEqual(link.extract(wire), b'0123456789')
        self.assertEqual(link.extract(wire[3:]), b'0123456789')
        self.assertEqual(link.extract(wire[3:] + wire[:3]), b'0123456789')

    def test_parser_rejects_wrong_uuid_lengths_extended_frames_and_malformed_ads(self):
        wire = link.advertisement(b'0123456789')
        cases = (None, [], b'', wire[:-1], wire + b'x', b'@' + wire[1:], b'\x02\x01\x06\x1b ' + wire[5:], wire[:5] + bytes([wire[5] ^ 1]) + wire[6:], b'\x00' + wire[1:], b'\x02\x01\x06\x1a!' + wire[5:])
        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(link.extract(data))
        with self.assertRaises(ValueError):
            link.advertisement(b'too-short')
        with self.assertRaises(ValueError):
            link.advertisement(memoryview(array('I', [0] * 10)))

    def test_constructor_is_lazy_and_start_subscribes_once(self):
        radio,broker,bus,owner=self.radio()
        self.assertEqual(broker.calls,[])
        self.assertTrue(radio.start());self.assertTrue(radio.start())
        self.assertEqual(len(broker.calls),1)
        self.assertEqual(bus.listeners[0][2],owner)
        self.assertTrue(radio.running)
        self.assertEqual(radio.transport,"espnow")
        self.assertFalse(radio.physical_active)

    def test_disabled_and_missing_firmware_are_graceful(self):
        radio,broker,bus,owner=self.radio(False)
        self.assertFalse(radio.start());self.assertEqual(broker.calls,[])
        missing=link.ESPNowNearbyRadio()
        self.assertFalse(missing.start())
        self.assertEqual(missing.status_code,"unavailable")
        self.assertNotIn("Bluetooth",missing.status)

    def test_broadcast_uses_exact_existing31_byte_envelope_and_nonblocking_send(self):
        radio,broker,bus,owner=self.radio();radio.start()
        self.assertTrue(radio.send(b"0123456789",0))
        self.assertEqual(broker.calls[-1],("send",wire.advertisement(b"0123456789"),b"\xff"*6,False))
        self.assertEqual(radio.tx_count,1)

    def test_changes_are_rate_limited_but_duplicate_success_does_not_retransmit(self):
        radio,broker,bus,owner=self.radio();radio.start()
        self.assertTrue(radio.send(b"0123456789",0))
        self.assertFalse(radio.send(b"1123456789",499))
        self.assertTrue(radio.send(b"0123456789",499))
        self.assertEqual(radio.tx_count,1)
        self.assertTrue(radio.send(b"1123456789",500))
        self.assertEqual(radio.tx_count,2)

    def test_receive_copies_transient_message_and_never_accesses_mac(self):
        radio,broker,bus,owner=self.radio();radio.start()
        backing=bytearray(wire.advertisement(b"0123456789"))
        broker.deliver(Event(memoryview(backing),-48))
        backing[:]=b"\0"*31
        self.assertEqual(radio.poll(),[(b"0123456789",-48)])
        self.assertEqual(radio.poll(),[])

    def test_other_application_packets_and_malformed_envelopes_are_filtered(self):
        radio,broker,bus,owner=self.radio();radio.start()
        good=wire.advertisement(b"0123456789")
        for packet in (None,b"hello from another app",good[:-1],good+b"x",b"X"+good[1:],good[:5]+bytes([good[5]^1])+good[6:]):
            broker.deliver(Event(packet))
        self.assertEqual(radio.poll(),[])
        self.assertEqual(radio.rx_count,0)

    def test_queue_is_bounded16_and_rssi_is_optional(self):
        radio,broker,bus,owner=self.radio();radio.start()
        for index in range(30):broker.deliver(Event(wire.advertisement(bytes([index])*10),"invalid"))
        received=radio.poll()
        self.assertEqual([item[0][0] for item in received],list(range(14,30)))
        self.assertTrue(all(item[1] is None for item in received))
        self.assertEqual(radio.dropped,14)

    def test_off_and_close_remove_only_our_wrapped_callback_and_ignore_late_delivery(self):
        radio,broker,bus,owner=self.radio()
        foreign=(Event,lambda event:None,object());bus.listeners.append(foreign)
        radio.start();wrapped=radio._wrapped
        self.assertTrue(radio.set_enabled(False))
        self.assertEqual(bus.listeners,[foreign])
        wrapped(Event(wire.advertisement(b"0123456789")))
        self.assertEqual(radio.poll(),[])
        self.assertTrue(radio.set_enabled(True))
        self.assertIsNot(radio._wrapped,wrapped)
        radio.close();radio.close()
        self.assertEqual(bus.listeners,[foreign])
        self.assertFalse(radio.start() or radio.set_enabled(True))
        self.assertTrue(all(item[2] is owner for item in bus.removed))

    def test_failed_unsubscribe_keeps_identity_for_retry_without_double_registration(self):
        radio,broker,bus,owner=self.radio();radio.start();wrapped=radio._wrapped
        bus.fail=True
        self.assertFalse(radio.set_enabled(False))
        self.assertIs(radio._wrapped,wrapped)
        self.assertFalse(radio.set_enabled(True))
        self.assertEqual(len(broker.calls),1)
        wrapped(Event(wire.advertisement(b"0123456789")))
        self.assertEqual(radio.poll(),[])
        bus.fail=False;radio.close()
        self.assertEqual(bus.listeners,[])

    def test_send_failures_detach_our_listener_without_resetting_shared_radio(self):
        for throws in (False,True):
            radio,broker,bus,owner=self.radio();radio.start()
            foreign=(Event,lambda event:None,object());bus.listeners.append(foreign)
            broker.fail_send=throws;broker.accept_send=False
            self.assertFalse(radio.send(b"0123456789",0))
            self.assertFalse(radio.running)
            self.assertEqual(bus.listeners,[foreign])
            self.assertEqual(radio.last_error,"send_failed")
            self.assertNotIn("Sensitive",radio.status)

    def test_subscribe_failure_is_sanitized(self):
        radio,broker,bus,owner=self.radio();broker.fail_subscribe=True
        self.assertFalse(radio.start())
        self.assertEqual(bus.listeners,[])
        self.assertEqual(radio.status_code,"error")
        self.assertNotIn("Sensitive",radio.status)

    def test_channel_property_is_read_only_and_does_not_assume_disconnected_channel(self):
        radio,broker,bus,owner=self.radio()
        for value,expected in ((1,1),(6,6),(14,14),(0,None),(-1,None),(15,None),(True,None),("6",None),(None,None)):
            broker.wifi_channel=value;self.assertEqual(radio.channel,expected)
        with self.assertRaises(AttributeError):radio.channel=7
        self.assertEqual(broker.calls,[])

    def test_real_model_packet_round_trip_uses_production_decoder(self):
        radio,broker,bus,owner=self.radio();radio.start()
        sender=model.Swarm(b"aaaa",120);receiver=model.Swarm(b"bbbb",40)
        payload=sender.packet({"time_ms":1000},0)
        radio.send(payload,0)
        broker.deliver(Event(broker.calls[-1][1]))
        for packet,rssi in radio.poll():self.assertTrue(receiver.receive(packet,0,rssi))
        self.assertEqual(receiver.view({"time_ms":0},0)["count"],1)


class Station:
    PM_NONE=0
    def __init__(self,active=False):
        self.enabled=active;self.pm=3;self.channel=6;self.calls=[]
        self.fail_pm=False
    def active(self,*args):
        if args:
            if args!=(True,):raise AssertionError("Must leave shared STA active")
            self.enabled=True;self.calls.append(("active",True))
        return self.enabled
    def config(self,name=None,**kwargs):
        if kwargs:
            if set(kwargs)!={"pm"}:raise AssertionError("Must not change Wi-Fi channel or credentials")
            self.calls.append(("pm",kwargs["pm"]));self.pm=kwargs["pm"]
            return None
        if name=="pm":
            if self.fail_pm:raise ValueError("Unsupported PM getter")
            return self.pm
        if name=="channel":return self.channel
        raise AssertionError("Unexpected Wi-Fi config")
    def __getattr__(self,name):raise AssertionError("Forbidden Wi-Fi access: "+name)


class RawESPNow:
    def __init__(self,active=False):
        self.enabled=active;self.rxbuf=526;self.calls=[];self.incoming=[]
        self.callback=None
        self.fail_add=self.fail_send=self.fail_receive=self.fail_close=False
        self.accept=True
    def active(self,*args):
        if args:
            self.calls.append(("active",args[0]))
            if not args[0] and self.fail_close:raise OSError("Sensitive raw close")
            self.enabled=args[0]
        return self.enabled
    def config(self,name=None,**kwargs):
        if kwargs:
            if set(kwargs)!={"rxbuf"}:raise AssertionError("Unexpected raw configuration")
            self.calls.append(("rxbuf",kwargs["rxbuf"]));self.rxbuf=kwargs["rxbuf"]
        elif name=="rxbuf":return self.rxbuf
        else:raise AssertionError("Unexpected raw configuration getter")
    def add_peer(self,mac):
        self.calls.append(("peer",mac))
        if self.fail_add:raise OSError("Sensitive peer failure")
    def irq(self,callback):
        if callback is not None:raise AssertionError("No Python receive IRQ may be installed")
        if self.enabled:raise AssertionError("Cannot clear a foreign active receiver")
        self.calls.append(("irq",callback));self.callback=callback
    def send(self,*args):
        self.calls.append(("send",)+args)
        if self.fail_send:raise OSError("Sensitive send failure")
        return self.accept
    def irecv(self,timeout):
        if timeout!=0:raise AssertionError("Receive must never wait")
        self.calls.append(("irecv",timeout))
        if self.fail_receive:raise OSError("Sensitive receive failure")
        return self.incoming.pop(0) if self.incoming else (None,None)
    def __getattr__(self,name):raise AssertionError("Forbidden raw operation: "+name)


class RawFallbackTests(unittest.TestCase):
    def radio(self,active=False,sta_active=False):
        raw=RawESPNow(active);sta=Station(sta_active)
        network=types.SimpleNamespace(STA_IF=0,WLAN=lambda interface:sta)
        radio=link.NearbyRadio(raw_backend=raw,network_backend=network)
        self.addCleanup(radio.close)
        return radio,raw,sta

    def test_raw_path_is_lazy_and_claims_only_inactive_singleton(self):
        radio,raw,sta=self.radio()
        self.assertEqual(raw.calls,[]);self.assertEqual(sta.calls,[])
        self.assertTrue(radio.start());self.assertTrue(radio.start())
        self.assertEqual(radio.adapter_mode,"raw")
        self.assertEqual(raw.calls,[("irq",None),("rxbuf",2048),("active",True),("peer",link.BROADCAST_MAC)])
        self.assertEqual(sta.calls,[("active",True),("pm",0)])
        self.assertEqual(radio.channel,6)
        self.assertFalse(radio.physical_active)

    def test_foreign_active_singleton_is_untouched_including_on_close(self):
        radio,raw,sta=self.radio(active=True)
        self.assertFalse(radio.start());radio.close()
        self.assertEqual(radio.last_error,"foreign_owner")
        self.assertEqual(raw.calls,[]);self.assertEqual(sta.calls,[])
        self.assertTrue(raw.enabled)

    def test_stale_inactive_irq_is_cleared_only_after_exclusive_claim(self):
        radio,raw,sta=self.radio()
        previous=lambda unused:None
        raw.callback=previous
        self.assertTrue(radio.start())
        self.assertIsNone(raw.callback)
        self.assertLess(raw.calls.index(("irq",None)),raw.calls.index(("active",True)))
        radio.close()
        foreign,foreign_raw,foreign_sta=self.radio(active=True)
        foreign_raw.callback=previous
        self.assertFalse(foreign.start());foreign.close()
        self.assertIs(foreign_raw.callback,previous)
        self.assertEqual(foreign_raw.calls,[])

    def test_second_adapter_cannot_claim_or_close_owned_singleton(self):
        first,raw,sta=self.radio();self.assertTrue(first.start())
        second=link.NearbyRadio(raw_backend=raw,network_backend=first._network_backend)
        self.addCleanup(second.close)
        calls=list(raw.calls)
        self.assertFalse(second.start());second.close()
        self.assertEqual(calls,raw.calls);self.assertTrue(raw.enabled)
        first.close();self.assertFalse(raw.enabled)

    def test_exact_envelope_nonblocking_send_and_existing_rate_limit(self):
        radio,raw,sta=self.radio();radio.start()
        self.assertTrue(radio.send(b"0123456789",0))
        self.assertEqual(raw.calls[-1],("send",link.BROADCAST_MAC,link.advertisement(b"0123456789"),False))
        self.assertFalse(radio.send(b"1123456789",499))
        self.assertTrue(radio.send(b"0123456789",499))
        self.assertEqual(radio.tx_count,1)
        self.assertTrue(radio.send(b"1123456789",500))
        self.assertEqual(radio.tx_count,2)

    def test_poll_is_bounded_nonblocking_copies_data_and_never_reads_addresses(self):
        radio,raw,sta=self.radio();radio.start()
        class Packet:
            def __init__(self,message):self.message=message
            def __getitem__(self,index):
                if index!=1:raise AssertionError("Never read peer address")
                return self.message
        backing=bytearray(link.advertisement(b"0123456789"))
        raw.incoming=[Packet(memoryview(backing)) for unused in range(20)]
        result=radio.poll()
        self.assertEqual(len(result),16);self.assertEqual(len(raw.incoming),4)
        backing[:]=b"\x00"*31
        self.assertEqual(result,[(b"0123456789",None)]*16)
        self.assertEqual(radio.rx_count,16)
        self.assertEqual(len([call for call in raw.calls if call[0]=="irecv"]),16)

    def test_raw_receive_rejects_other_apps_and_noncanonical_frames(self):
        radio,raw,sta=self.radio();radio.start()
        good=link.advertisement(b"0123456789")
        raw.incoming=[(object(),message) for message in (b"Other app",good[3:],good[:-1],good+b"x",b"X"+good[1:],good)]
        self.assertEqual(radio.poll(),[(b"0123456789",None)])

    def test_close_restores_only_our_pm_and_buffer_and_leaves_sta_active(self):
        radio,raw,sta=self.radio();radio.start();radio.close();radio.close()
        self.assertFalse(raw.enabled);self.assertEqual(raw.rxbuf,526)
        self.assertEqual(sta.pm,3);self.assertTrue(sta.enabled)
        self.assertFalse(radio.start())
        self.assertEqual(len([call for call in raw.calls if call==("active",False)]),1)

    def test_foreign_pm_change_is_preserved_and_initially_awake_pm_not_written(self):
        radio,raw,sta=self.radio(sta_active=True);radio.start()
        sta.pm=7;raw.rxbuf=4096;radio.close()
        self.assertEqual(sta.pm,7);self.assertEqual(raw.rxbuf,4096)
        radio2,raw2,sta2=self.radio(sta_active=True);sta2.pm=0
        self.assertTrue(radio2.start());radio2.close()
        self.assertEqual(sta2.calls,[])

    def test_unsupported_pm_getter_never_causes_an_unrestorable_pm_write(self):
        radio,raw,sta=self.radio();sta.fail_pm=True
        self.assertTrue(radio.start());radio.close()
        self.assertEqual(sta.calls,[("active",True)])

    def test_start_failure_releases_only_owned_raw_and_sanitizes_message(self):
        radio,raw,sta=self.radio();raw.fail_add=True
        self.assertFalse(radio.start())
        self.assertFalse(raw.enabled);self.assertEqual(sta.pm,3)
        self.assertEqual(raw.rxbuf,526);self.assertNotIn("Sensitive",radio.status)
        self.assertEqual(radio.last_error,"raw_start_failed")

    def test_send_and_receive_failures_release_owned_resources(self):
        for kind in ("send","receive"):
            with self.subTest(kind=kind):
                radio,raw,sta=self.radio();radio.start()
                setattr(raw,"fail_"+kind,True)
                if kind=="send":self.assertFalse(radio.send(b"0123456789",0))
                else:self.assertEqual(radio.poll(),[])
                self.assertFalse(radio.running);self.assertFalse(raw.enabled)
                self.assertEqual(sta.pm,3);self.assertNotIn("Sensitive",radio.status)

    def test_failed_raw_close_retains_ownership_for_retry(self):
        radio,raw,sta=self.radio();radio.start();raw.fail_close=True
        radio.close();self.assertTrue(radio.closing);self.assertTrue(raw.enabled)
        raw.fail_close=False;radio.close()
        self.assertFalse(radio.closing);self.assertFalse(raw.enabled)

    def test_disable_then_enable_reacquires_safely(self):
        radio,raw,sta=self.radio();radio.start()
        self.assertTrue(radio.set_enabled(False));self.assertFalse(raw.enabled)
        self.assertEqual(radio.poll(),[])
        self.assertTrue(radio.set_enabled(True));self.assertTrue(raw.enabled)


if __name__=="__main__":unittest.main()
