"""Production app/radio boundary: local flares, remote echoes and ownership."""
import unittest
from unittest.mock import patch
from test_app import runtime


class FakeRadio:
    def __init__(self, owner=None, enabled=True):
        self.enabled, self.running, self.closed = enabled, False, False
        self.status_code, self.status = 'idle', 'NEARBY IDLE'
        self.tx, self.rx, self.stops = 0, 0, 0
        self.queue, self.sent = [], []
    def set_enabled(self, value):
        self.enabled = value
        self.running = value and not self.closed
        self.status_code = 'ready' if self.running else 'disabled'
        if not value: self.stops += 1
        return self.running
    def start(self): return self.set_enabled(True)
    def poll(self):
        queue, self.queue = self.queue, []
        self.rx += len(queue)
        return queue
    def send(self, packet, now):
        self.sent.append((bytes(packet), now)); self.tx += 1
        return self.running
    def close(self):
        self.closed, self.running = True, False
        self.status_code = 'closed'


class SwarmAppTests(unittest.TestCase):
    def app(self):
        module, app, hardware, clock = runtime()
        app.radio = FakeRadio(app)
        app.swarm = module.Swarm(node_id=b'\x80\0\0\1', hue=80)
        app._swarm_view = app.swarm.view(app._local_frame(), 0)
        return module, app, hardware, clock

    def test_only_local_boost_is_advertised_and_peer_echo_never_relays_it(self):
        module, app, hardware, clock = self.app()
        peer = module.Swarm(node_id=b'\0\0\0\1', hue=180)
        clock.now = 500
        app.radio.queue.append((peer.packet({'time_ms': 500}, 500), -50))
        app.update(0)
        self.assertEqual(app._swarm_view['count'], 1)
        self.assertEqual(app._swarm_view['role'], 'follower')
        self.assertEqual(app.show.frame()['burst'], 0)
        peer.burst(1000)
        clock.now = 1000
        packet = peer.packet({'time_ms': 1000}, 1000)
        app.radio.queue.append((packet, -50))
        app.update(0)
        self.assertGreater(app.show.frame()['burst'], .9)
        self.assertEqual(app.radio.sent[-1][0][6], 0)
        clock.now = 2200
        app.radio.queue.append((packet, -50))
        app.update(0)
        self.assertEqual(app.show.frame()['burst'], 0)
        app._key('UP')
        clock.now = 2800
        app.update(0)
        self.assertEqual(app.radio.sent[-1][0][6], 1)

    def test_beacons_are_bounded_and_local_chapters_are_not_remote_commands(self):
        module, app, hardware, clock = self.app()
        peer = module.Swarm(node_id=b'\0\0\0\1')
        for now in range(0, 2001, 100):
            clock.now = now
            if now == 500:
                app.radio.queue.append((peer.packet({'time_ms': 130000, 'paused': True}, 500), -40))
            app.update(0)
        self.assertLessEqual(app.radio.tx, 5)
        self.assertFalse(app.show.paused)
        self.assertEqual(app.show.position, 2000)
        self.assertTrue(all(b-a >= 500 for a,b in zip([at for packet,at in app.radio.sent],
                                                    [at for packet,at in app.radio.sent][1:])))

    def test_disabling_or_losing_focus_clears_neighbours_and_releases_transport(self):
        module, app, hardware, clock = self.app()
        peer = module.Swarm(node_id=b'\0\0\0\1')
        clock.now = 500
        app.radio.queue.append((peer.packet({'time_ms': 500}, 500), -40))
        app.update(0)
        app._focused = False
        clock.now = 700
        app.update(0)
        self.assertFalse(app.radio.running)
        self.assertEqual(app._swarm_view['count'], 0)
        app._focused = True
        clock.now = 3000
        app.update(0)
        self.assertTrue(app.radio.running)
        app._settings, app._setting_row = True, 5
        app._setting_key('RIGHT')
        clock.now = 3200
        app.update(0)
        self.assertFalse(app.config['swarm_enabled'])
        self.assertFalse(app.radio.running)
        self.assertEqual(app._swarm_view['count'], 0)

    def test_busy_or_unavailable_bluetooth_never_invents_a_peer(self):
        module, app, hardware, clock = self.app()
        app.radio.set_enabled = lambda enabled: False
        app.radio.status_code = 'busy'
        for now in (0, 500, 2500):
            clock.now = now
            app.update(0)
        self.assertEqual(app._swarm_view['count'], 0)
        self.assertFalse(app.radio.sent)

    def test_simultaneous_peer_batch_does_not_starve_later_badges(self):
        module, app, hardware, clock = self.app()
        for index in range(12):
            peer = module.Swarm(node_id=bytes((index+1, 7, 31, 83)))
            app.radio.queue.append((peer.packet({'time_ms': 500}, 500), -40))
        clock.now = 500
        app.update(0)
        self.assertEqual(app._swarm_view['count'], 12)

    def test_shared_lights_remain_within_saved_brightness(self):
        module, app, hardware, clock = self.app()
        peer = module.Swarm(node_id=b'\0\0\0\1', hue=255)
        clock.now = 500
        app.radio.queue.append((peer.packet({'time_ms': 250}, 500), -40))
        app.update(0)
        app._burst()
        for value in (0, .01, .15, 1):
            app.config['ring_brightness'] = value
            app._write_lights()
            self.assertTrue(all(0 <= channel <= int(value*255) for colour in hardware.leds[1:13] for channel in colour))


if __name__ == '__main__':
    unittest.main()
