"""Shared ESP-NOW broker, with an inactive-singleton fallback for older OSes."""
SERVICE_UUID = '8dd8332c-6329-45dc-a01b-d0dd6688e1f0'

SERVICE_UUID_LE = b'\xf0\xe1\x88f\xdd\xd0\x1b\xa0\xdcE)c,3\xd8\x8d'

PAYLOAD_SIZE = 10

MAX_QUEUE = 16

MIN_UPDATE_MS = 500

ADV_PREFIX = b'\x02\x01\x06\x1b!' + SERVICE_UUID_LE

def advertisement(payload):
    """A legacy31-byte packet: Flags plus one128-bit service-data section."""
    if not isinstance(payload, (bytes, bytearray, memoryview)) or len(payload) != PAYLOAD_SIZE:
        raise ValueError('Nearby payload must contain exactly10 bytes')
    payload = bytes(payload)
    if len(payload) != PAYLOAD_SIZE:
        raise ValueError('Nearby payload must contain exactly10 bytes')
    return ADV_PREFIX + payload

def extract(data):
    """Copy only matching service data from a bounded legacy advertisement.

    A broadcaster may omit Flags, so a28-byte service-data-only packet is also
    valid. Malformed lengths, oversized/extended frames and other UUIDs fail
    closed. The caller never retains a transient BLE memoryview.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)) or not 28 <= len(data) <= 31:
        return None
    at, end, found = (0, len(data), None)
    while at < end:
        length = data[at]
        if length == 0:
            return found if all((value == 0 for value in data[at:])) else None
        stop = at + length + 1
        if length < 1 or stop > end:
            return None
        if data[at + 1] == 33 and length == 27:
            matches = True
            for index in range(16):
                if data[at + 2 + index] != SERVICE_UUID_LE[index]:
                    matches = False
                    break
            if matches:
                if found is not None:
                    return None
                found = bytes(data[at + 18:stop])
                if len(found) != PAYLOAD_SIZE:
                    return None
        at = stop
    return found

BROADCAST_MAC=b"\xff\xff\xff\xff\xff\xff"
_MESSAGES={"idle":"NEARBY IDLE","disabled":"NEARBY OFF","ready":"NEARBY ESP-NOW READY",
           "unavailable":"ESP-NOW UNAVAILABLE","busy":"ESP-NOW IN USE",
           "error":"ESP-NOW RADIO ERROR","closed":"NEARBY CLOSED"}
_RAW_OWNER=None


class ESPNowNearbyRadio:
    """Prefer the OS broker; own raw ESP-NOW only if that broker is absent.

    Packets are the same31-byte application envelope used by the visual model
    and simulator. They travel over ESP-NOW, not Bluetooth. Peers must share
    the current2.4GHz channel. Neither path changes the channel, connection or
    AP. The older-OS fallback claims only an inactive singleton, enables STA
    if needed, and temporarily disables station power saving when readable.
    It never deactivates STA and restores its PM change only if unchanged.
    """
    transport="espnow"

    def __init__(self,owner=None,enabled=True,backend=None,event_bus=None,event_type=None,
                 raw_backend=None,network_backend=None):
        self.owner=self if owner is None else owner
        self.enabled=enabled is True
        self._broker=backend
        self._bus=event_bus
        self._event_type=event_type
        self._wrapped=None
        self._running=self._closed=False
        self._queue=[]
        self._last_tx=None
        self._last_payload=None
        self.tx_count=self.rx_count=self.dropped=0
        self.last_error=None
        self.status_code="idle" if self.enabled else "disabled"
        self.status=_MESSAGES[self.status_code]
        self._handler=self._on_event
        self._filter=self._predicate
        self._raw_backend=raw_backend
        self._network_backend=network_backend
        self._raw=None
        self._sta=None
        self._raw_owned=False
        self._old_pm=self._set_pm=self._old_rxbuf=None
        self.adapter_mode=None

    @property
    def running(self):return self._running

    @property
    def physical_active(self):return False  # This adapter never owns Bluetooth.

    @property
    def closing(self):return (self._wrapped is not None or self._raw_owned) and not self._running

    @property
    def cleanup_timed_out(self):return False

    @property
    def tx(self):return self.tx_count

    @property
    def rx(self):return self.rx_count

    @property
    def channel(self):
        if self._sta is not None:
            try:value=self._sta.config("channel") if self._sta.active() else None
            except Exception:return None
            return value if type(value) is int and 1<=value<=14 else None
        if self._broker is None:return None
        try:value=self._broker.wifi_channel
        except Exception:return None
        return value if type(value) is int and 1<=value<=14 else None

    @property
    def wifi_channel(self):return self.channel

    def _status(self,code):
        self.status_code,self.status=code,_MESSAGES[code]

    def _dependencies(self):
        if self._broker is None:
            from system.espnow import espnow_service
            self._broker=espnow_service
        if self._bus is None:
            from system.eventbus import eventbus
            self._bus=eventbus
        if self._event_type is None:
            from system.espnow.events import EspNowReceiveEvent
            self._event_type=EspNowReceiveEvent
        return (callable(getattr(self._broker,"subscribe",None))
                and callable(getattr(self._broker,"send",None))
                and callable(getattr(self._bus,"remove",None)))

    def start(self):
        if self._closed:self._status("closed");return False
        if not self.enabled:self._status("disabled");return False
        if self._running:return True
        if self._wrapped is not None:
            self._detach()
            if self._wrapped is not None:return False
        try:
            if not self._dependencies():self._status("unavailable");return False
            wrapped=self._broker.subscribe(handler=self._handler,app=self.owner,predicate=self._filter)
            if not callable(wrapped):
                self.last_error="unsupported_subscription";self._status("unavailable");return False
            self._wrapped=wrapped
        except ImportError:
            if self._broker is None:return self._start_raw()
            self.last_error="missing_firmware";self._status("unavailable");return False
        except Exception:
            self.last_error="subscribe_failed";self._status("error");return False
        self._running=True
        self.adapter_mode="broker"
        self.last_error=None
        self._status("ready")
        return True

    def _start_raw(self):
        global _RAW_OWNER
        if _RAW_OWNER is not None and _RAW_OWNER is not self:
            self.last_error="foreign_owner";self._status("busy");return False
        if self._raw_owned and not self._release_raw():return False
        try:
            raw=self._raw_backend
            if raw is None:
                import espnow
                raw=espnow.ESPNow()
            if raw.active():
                self.last_error="foreign_owner";self._status("busy");return False
            network=self._network_backend
            if network is None:import network
            sta=network.WLAN(network.STA_IF)
            self._raw,self._sta=raw,sta
            _RAW_OWNER=self
            self._raw_owned=True
            # The inactive singleton is ours before any configuration changes.
            # ESP-NOW deinit retains its Python callback; prevent a previous
            # owner's inactive handler from firing when our radio starts.
            raw.irq(None)
            self._old_rxbuf=raw.config("rxbuf")
            raw.config(rxbuf=2048)
            if not sta.active():sta.active(True)
            try:
                old=sta.config("pm")
                awake=getattr(sta,"PM_NONE",None)
                if type(old) is int and type(awake) is int and old!=awake:
                    self._old_pm=old
                    sta.config(pm=awake)
                    self._set_pm=awake
            except (OSError,ValueError,AttributeError):pass
            raw.active(True)
            raw.add_peer(BROADCAST_MAC)
        except ImportError:
            self._release_raw();self.last_error="missing_firmware"
            self._status("unavailable");return False
        except BaseException as error:
            self._release_raw();self.last_error="raw_start_failed";self._status("error")
            if not isinstance(error,Exception):raise
            return False
        self._running=True
        self.adapter_mode="raw"
        self.last_error=None
        self._status("ready")
        return True

    def _release_raw(self):
        global _RAW_OWNER
        if not self._raw_owned:return True
        if _RAW_OWNER is not self:return False
        try:self._raw.active(False)
        except Exception:
            self.last_error="raw_close_failed";self._status("error");return False
        # Restore only values we changed and which nobody changed afterwards.
        try:
            if self._set_pm is not None and self._sta.config("pm")==self._set_pm:
                self._sta.config(pm=self._old_pm)
        except Exception:pass
        try:
            if self._old_rxbuf is not None and self._raw.config("rxbuf")==2048:
                self._raw.config(rxbuf=self._old_rxbuf)
        except Exception:pass
        self._raw_owned=False
        self._old_pm=self._set_pm=self._old_rxbuf=None
        _RAW_OWNER=None
        return True

    def _predicate(self,event):
        try:
            message=event.msg
            return isinstance(message,(bytes,bytearray,memoryview)) and len(message)==31 and message[:21]==ADV_PREFIX
        except Exception:return False

    def _on_event(self,event):
        if not self._running or self._closed or not self.enabled:return
        try:
            if not self._predicate(event):return
            payload=extract(event.msg)
            if payload is None:return
            rssi=getattr(event,"rssi",None)
            rssi=rssi if type(rssi) is int and -127<=rssi<=20 else None
            if len(self._queue)>=MAX_QUEUE:
                self._queue.pop(0);self.dropped+=1
            self._queue.append((payload,rssi))
            self.rx_count+=1
        except Exception:self.dropped+=1

    def send(self,payload,now_ms):
        if (not self._running or self._closed or not self.enabled
                or not isinstance(payload,(bytes,bytearray,memoryview)) or len(payload)!=PAYLOAD_SIZE
                or isinstance(now_ms,bool) or not isinstance(now_ms,(int,float))
                or not 0<=now_ms<=9007199254740991):return False
        try:payload=bytes(payload)
        except (TypeError,ValueError):return False
        if len(payload)!=PAYLOAD_SIZE:return False
        now_ms=int(now_ms)
        if self._last_tx is not None and now_ms-self._last_tx<MIN_UPDATE_MS:
            return payload==self._last_payload
        try:
            if self.adapter_mode=="raw":
                accepted=self._raw.send(BROADCAST_MAC,advertisement(payload),False)
            else:accepted=self._broker.send(advertisement(payload),mac=BROADCAST_MAC,sync=False)
            if accepted is not True:raise OSError("ESP-NOW send not queued")
        except Exception:
            self._running=False;self.last_error="send_failed"
            self._detach();self._status("error")
            return False
        self._last_tx,self._last_payload=now_ms,payload
        self.tx_count+=1
        return True

    def poll(self):
        if not self._running or self._closed or not self.enabled:
            self._queue=[];return []
        if self.adapter_mode=="raw":
            result=[]
            try:
                for unused in range(MAX_QUEUE):
                    received=self._raw.irecv(0)
                    message=received[1]
                    if message is None:break
                    if (isinstance(message,(bytes,bytearray,memoryview))
                            and len(message)==31 and message[:21]==ADV_PREFIX):
                        payload=extract(message)
                        if payload is not None:
                            result.append((payload,None));self.rx_count+=1
            except Exception:
                self._running=False;self.last_error="receive_failed"
                self._detach();self._status("error")
            return result
        result,self._queue=self._queue,[]
        return result

    def _detach(self):
        if self._raw_owned:return self._release_raw()
        if self._wrapped is None:return True
        try:
            self._bus.remove(self._event_type,self._wrapped,self.owner)
        except Exception:
            # Retain exact callback identity so close/retry can finish later.
            self.last_error="unsubscribe_failed";self._status("error");return False
        self._wrapped=None
        return True

    def set_enabled(self,enabled):
        if type(enabled) is not bool or self._closed:return False
        self.enabled=enabled
        if enabled:return self.start()
        self._running=False;self._queue=[]
        removed=self._detach()
        if removed:self._status("disabled")
        return removed

    def close(self):
        self._closed=True;self._running=False;self._queue=[]
        removed=self._detach()
        if removed:self._status("closed")


NearbyRadio=ESPNowNearbyRadio
