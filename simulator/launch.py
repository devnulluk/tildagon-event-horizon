"""Run Event Horizon through the official SDL/ctx simulator, never real USB."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time as host_time
import types

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("TILDAGON_HORIZON_SIM_ROOT", ROOT / ".simulator")).expanduser().resolve()
RUN, SIM = CACHE / "run", CACHE / "firmware/sim"
SCENES = ("intro", "starflight", "tunnel", "terrain", "planet", "kaleidoscope", "blackhole", "finale")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scene", choices=SCENES, help="Start one scene, with a stable mid-scene screenshot position")
parser.add_argument("--showcase", choices=("tour", "idle"), default="tour")
parser.add_argument("--seconds", type=float, default=48, help="Recording duration1..180;120 preserves the full native score")
parser.add_argument("--record", type=Path)
parser.add_argument("--soundtrack", type=Path, help="Explicit original WAV input, muxed after capture without changing video pixels")
parser.add_argument("--video-fps", type=int, default=15)
parser.add_argument("--record-view", choices=("lcd", "window"), default="lcd")
parser.add_argument("--screenshot", action="store_true")
parser.add_argument("--output", type=Path)
parser.add_argument("--gallery", type=Path, help="Capture all8 actual scenes and a contact sheet in one run")
parser.add_argument("--expansions", action="store_true", help="Simulate documented EEH14 +Liteloop adapters; no physical hardware")
parser.add_argument("--quality", type=float, default=.9)
parser.add_argument("--action", choices=["joy" + key for key in ("up", "down", "left", "right", "fire")]
                    + ["touch%02d" % pad for pad in range(1, 13)], help="One virtual Spaceagon press, for repeatable input checks")
parser.add_argument("--capture-frames", type=int, default=10)
options = parser.parse_args()
if not (SIM / "run.py").is_file():
    parser.error("Run Python3.10 tools/prepare_simulator.py first; see simulator/README.md")
if sum(bool(value) for value in (options.record, options.screenshot, options.gallery)) > 1:
    parser.error("Choose one recording, screenshot or gallery capture")
if not 0 <= options.quality <= 1 or not 5 <= options.video_fps <= 30 or not 1 <= options.seconds <= 180:
    parser.error("Quality0..1, sampling5..30FPS, duration1..180 seconds required")
if options.record and options.record.suffix.lower() != ".mp4":
    parser.error("--record requires an MP4 filename")
if options.soundtrack and (not options.record or not options.soundtrack.is_file()):
    parser.error("--soundtrack requires --record and an existing audio file")
soundtrack = options.soundtrack.resolve() if options.soundtrack else None
RUN.mkdir(parents=True, exist_ok=True)
capture_output = (options.output or ROOT / "docs" / ("simulator-" + (options.scene or "intro") + ".png")).resolve()
if options.screenshot:
    capture_output.parent.mkdir(parents=True, exist_ok=True)
gallery = options.gallery.resolve() if options.gallery else None
if gallery:
    gallery.mkdir(parents=True, exist_ok=True)
if not options.record and not options.screenshot and not gallery:
    sys.stdout = open(RUN / "live-stdout.log", "w", encoding="utf-8", buffering=1)
    sys.stderr = open(RUN / "live-stderr.log", "w", encoding="utf-8", buffering=1)

# Only runtime source/manifests are staged. Private local config never travels.
target = SIM / "apps/event_horizon"
target.mkdir(parents=True, exist_ok=True)
for source in ROOT.glob("*.py"):
    shutil.copyfile(source, target / source.name)
shutil.copyfile(ROOT / "tildagon.toml", target / "tildagon.toml")
(target / "config.json").write_text(json.dumps({
    "ring_brightness": .15, "eeh_brightness": .03, "matrix_brightness": .12,
    "quality": options.quality, "adaptive_quality": False,
    "space_tilt": True, "space_joystick": True, "space_touch": True, "space_proximity": False,
    "eeh": {"slot": 6, "type": "EEH Logo"} if options.expansions else None,
}), encoding="utf-8")
source_hashes = {source.name: hashlib.sha256(source.read_bytes()).hexdigest() for source in target.glob("*.py")}

recorder = None
if options.record:
    from film_capture import FrameRecorder
    recorder = FrameRecorder(CACHE, options.record, options.seconds, options.video_fps, options.record_view, options.showcase)
    recorder.source_hashes = source_hashes
    recorder.sequence_mode = "manual-scene-cuts" if options.showcase == "tour" and not options.scene and options.seconds < 110 else "native-score"
    recorder.soundtrack = str(soundtrack) if soundtrack else None
    recorder.soundtrack_sha256 = hashlib.sha256(soundtrack.read_bytes()).hexdigest() if soundtrack else None

os.chdir(SIM)
sys.path.insert(0, str(SIM))
import run
import system.scheduler  # Preserve the firmware's normal circular-import order.
import settings
# Suppress the firmware's optional boot overlay in this simulator process.
# It otherwise covers the first scene captures; no badge setting is touched.
settings.set("enable_boot_animation", False)
import pygame
import _sim
from system.eventbus import eventbus
from events.input import Button, ButtonDownEvent, ButtonUpEvent
from events.keyboard import KEYBOARD_BUTTONS
import event_horizon.app as app_module
from event_horizon import expansions, space_inputs
from event_horizon.matrix import GRID

pygame.display.set_caption("Event Horizon - Official Spaceagon Simulator (DEMO)")
_sim.screen = pygame.display.set_mode((1040, 733))
_sim._sim.grav.KEYS = []
eeh = [(0, 0, 0)] * 14
eeh_writes = 0
matrix_registers = bytearray(256)


class Pixels:
    def __init__(self):
        self.n = 14
        self.values = [(0, 0, 0)] * 14
    def __setitem__(self, key, value):
        self.values[key] = tuple(value)
    def fill(self, value):
        self.values[:] = [tuple(value)] * 14
    def write(self):
        global eeh_writes
        eeh[:] = self.values
        eeh_writes += 1


class MatrixSink:
    def writeto_mem(self, address, register, data):
        if address != 0x20 or not 0x50 <= register <= 0xEC or len(data) != 1:
            raise ValueError("Unexpected virtual matrix transaction")
        matrix_registers[register:register + len(data)] = data
        return len(data)


matrix_sink = MatrixSink()
matrix_header = types.SimpleNamespace(vid=0xCAFE, pid=0x54E1, friendly_name="Liteloop")
keyboard_driver = types.SimpleNamespace(hexpansion_config=types.SimpleNamespace(port=4), ADDR=0x34,
                                        handle_keyboard_key=lambda key, down: None)
expansions.FirmwareBackend.snapshot = lambda self: ({4: keyboard_driver}, {2, 4, 6} if options.expansions else {4}, [])
expansions.FirmwareBackend.saved_eeh = lambda self: {"slot": 6, "type": "EEH Logo"} if options.expansions else None
expansions.FirmwareBackend.pixels = lambda self, slot, count: Pixels()
expansions.FirmwareBackend.headers = lambda self: {2: matrix_header} if options.expansions else {}
expansions.FirmwareBackend.matrix_i2c = lambda self, slot: matrix_sink

VirtualBoard = type("TwentyTwentySix", (), {"__module__": "frontboards.twentysix", "year": 2026})
front = VirtualBoard()
front.joystick_states = {key: [False, 0] for key in ("UP", "DOWN", "LEFT", "RIGHT", "FIRE")}
front.touch_states = {"TOUCH%02d" % pad: [False, 0] for pad in range(1, 13)}
tilt_acceleration = [0.0, 0.0, 9.81]
space_inputs.FirmwareBackend.frontboards = lambda self: [front]
space_inputs.FirmwareBackend.acceleration = lambda self: tuple(tilt_acceleration)

native_buttons = {name: Button(name, "TwentyTwentySix") for name in
                  ["JOY" + name for name in front.joystick_states] + list(front.touch_states)}


def emit(name, down):
    if name.startswith("JOY"):
        front.joystick_states[name[3:]][0] = down
    else:
        front.touch_states[name][0] = down
    eventbus.emit((ButtonDownEvent if down else ButtonUpEvent)(native_buttons[name]))


touch_positions = [(880 + math.cos(index * math.pi / 6 - .42 * math.pi) * 70,
                    202 + math.sin(index * math.pi / 6 - .42 * math.pi) * 70) for index in range(12)]
mouse_touch = None
mouse_joy = None
tilt_drag = False
original_events = _sim._sim.process_events
JOY_KEYS = {pygame.K_UP: "JOYUP", pygame.K_DOWN: "JOYDOWN", pygame.K_LEFT: "JOYLEFT",
            pygame.K_RIGHT: "JOYRIGHT", pygame.K_RETURN: "JOYFIRE"}
TOUCH_KEYS = {getattr(pygame, "K_" + key): "TOUCH%02d" % (index + 1) for index, key in enumerate("1234567890")}
TOUCH_KEYS[pygame.K_MINUS], TOUCH_KEYS[pygame.K_EQUALS] = "TOUCH11", "TOUCH12"
JOY_BOXES = {"JOYUP": (868, 164, 24, 23), "JOYLEFT": (841, 191, 24, 23),
             "JOYFIRE": (868, 191, 24, 23), "JOYRIGHT": (895, 191, 24, 23), "JOYDOWN": (868, 218, 24, 23)}


def process_events():
    global mouse_touch, mouse_joy, tilt_drag
    for event in pygame.event.get():
        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
            down = event.type == pygame.KEYDOWN
            if event.key in JOY_KEYS:
                emit(JOY_KEYS[event.key], down)
                continue
            if event.key in TOUCH_KEYS:
                emit(TOUCH_KEYS[event.key], down)
                continue
            if event.key not in [getattr(pygame, "K_" + key) for key in "abcdef"]:
                name = {pygame.K_SPACE: "SPACE", pygame.K_ESCAPE: "ESCAPE"}.get(event.key)
                if name is None and 32 <= event.key < 127:
                    name = chr(event.key).upper()
                if name in KEYBOARD_BUTTONS:
                    eventbus.emit((ButtonDownEvent if down else ButtonUpEvent)(KEYBOARD_BUTTONS[name]))
                    continue
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION) and event.pos[0] >= 733:
            x, y = event.pos
            if event.type == pygame.MOUSEBUTTONDOWN:
                for index, (tx, ty) in enumerate(touch_positions):
                    if (x - tx) ** 2 + (y - ty) ** 2 < 14 ** 2:
                        mouse_touch = "TOUCH%02d" % (index + 1)
                        emit(mouse_touch, True)
                        break
                for name, rectangle in JOY_BOXES.items():
                    if pygame.Rect(rectangle).collidepoint(x, y):
                        mouse_joy = name
                        emit(name, True)
                        break
                tilt_drag = (x - 880) ** 2 + (y - 393) ** 2 <= 40 ** 2
            if event.type == pygame.MOUSEBUTTONUP:
                if mouse_touch:
                    emit(mouse_touch, False)
                if mouse_joy:
                    emit(mouse_joy, False)
                mouse_joy = None
                mouse_touch, tilt_drag = None, False
                tilt_acceleration[:] = [0, 0, 9.81]
            if event.type == pygame.MOUSEMOTION and tilt_drag:
                ax, ay = max(-4.8, min(4.8, (x - 880) / 7)), max(-4.8, min(4.8, (y - 393) / 7))
                tilt_acceleration[:] = [ax, ay, math.sqrt(9.81 ** 2 - ax * ax - ay * ay)]
            if event.type == pygame.MOUSEMOTION and mouse_touch:
                for index, (tx, ty) in enumerate(touch_positions):
                    name = "TOUCH%02d" % (index + 1)
                    if name != mouse_touch and (x - tx) ** 2 + (y - ty) ** 2 < 14 ** 2:
                        emit(mouse_touch, False)
                        mouse_touch = name
                        emit(mouse_touch, True)
                        break
            continue
        pygame.event.post(event)
    original_events()


_sim._sim.process_events = process_events
preview = None


class PreviewHorizon(app_module.EventHorizon):
    def __init__(self):
        global preview
        super().__init__()
        preview = self
        if options.scene:
            self.show.select(SCENES.index(options.scene))
            if options.screenshot:
                self.show.position += int(self.show.frame()["duration_ms"] * .45)

    def _now(self):
        value = super()._now()
        if recorder is not None and recorder.start is None:
            # Warm-up frames stay at score zero; the first recorded frame is
            # the real initial chapter, not a late sample of the boot period.
            self.show.select(SCENES.index(options.scene) if options.scene else 0)
            self.show.elapsed = 0
        return value


preview_module = types.ModuleType("horizon_preview")
preview_module.PreviewHorizon = PreviewHorizon
sys.modules["horizon_preview"] = preview_module
original_render = _sim._sim.render_gui_now
frames, gallery_index, gallery_since = 0, -1, 0
gallery_images, gallery_proof = [], []
last_status = None
native_surface = None
last_tour_index = -1


def side_text(value, y, size=18, colour=(175, 198, 220)):
    image = pygame.font.Font(None, size).render(value, True, colour)
    _sim.screen.blit(image, (750, y))


def native_frame():
    surface = pygame.Surface((240, 240))
    surface.fill((0, 0, 0))
    surface.blit(_sim._sim._oled_surface, (0, 0))
    return surface


def save_gallery():
    sheet = pygame.Surface((960, 624))
    sheet.fill((5, 9, 20))
    heading = pygame.font.Font(None, 23).render("EVENT HORIZON / OFFICIAL SIMULATOR / PROCEDURAL DEMO", True, (230, 238, 250))
    sheet.blit(heading, ((960 - heading.get_width()) // 2, 17))
    for index, image in enumerate(gallery_images):
        x, y = index % 4 * 240, 56 + index // 4 * 282
        sheet.blit(image, (x, y))
        label = pygame.font.Font(None, 23).render(SCENES[index].upper(), True, (110, 212, 244))
        sheet.blit(label, (x + (240 - label.get_width()) // 2, y + 247))
    pygame.image.save(sheet, str(gallery / "contact-sheet.png"))
    with open(str(gallery / "gallery-proof.json"), "w") as handle:
        json.dump({"official_simulator": True, "physical_camera_footage": False,
                   "source_hashes": source_hashes, "frames": gallery_proof}, handle, indent=2)


def render_gui():
    global frames, gallery_index, gallery_since, last_status, native_surface, last_tour_index
    original_render()
    frames += 1
    pygame.draw.rect(_sim.screen, (10, 17, 29), (733, 0, 307, 733))
    side_text("EVENT HORIZON", 20, 31, (210, 240, 255))
    side_text("OFFICIAL SDL/ctx SIMULATOR", 56, 17)
    side_text("PROCEDURAL DEMO / NO USB", 79, 17, (255, 201, 95))
    side_text("Touch ring / keys1..0,-,=", 105, 19)
    for index, (x, y) in enumerate(touch_positions):
        down = front.touch_states["TOUCH%02d" % (index + 1)][0]
        pygame.draw.circle(_sim.screen, (55, 206, 245) if down else (25, 51, 75), (int(x), int(y)), 12)
        label = pygame.font.Font(None, 17).render(str(index + 1), True, (220, 240, 250))
        _sim.screen.blit(label, (x - label.get_width() / 2, y - 7))
    for name, rectangle in JOY_BOXES.items():
        down = front.joystick_states[name[3:]][0]
        pygame.draw.rect(_sim.screen, (45, 170, 214) if down else (18, 43, 65), rectangle, border_radius=4)
        glyph = {"JOYUP": "^", "JOYLEFT": "<", "JOYRIGHT": ">", "JOYDOWN": "v", "JOYFIRE": "O"}[name]
        label = pygame.font.Font(None, 22).render(glyph, True, (215, 235, 250))
        _sim.screen.blit(label, (rectangle[0] + (24 - label.get_width()) / 2, rectangle[1] + 3))
    side_text("Arrows: joystick / Enter: pause", 287, 19)
    side_text("A: boost  B/E: scenes  D: HUD", 312, 19)
    side_text("C/Space: pause  F/Esc: exit", 336, 19)
    pygame.draw.circle(_sim.screen, (20, 42, 65), (880, 393), 38)
    pygame.draw.circle(_sim.screen, (66, 216, 247),
                       (int(880 + tilt_acceleration[0] * 5), int(393 + tilt_acceleration[1] * 5)), 6)
    side_text("Drag disc: tilt / S: settings", 440, 19)
    side_text("SIMULATED EEH + LITELOOP" if options.expansions else "Optional expansions disabled", 468, 18)
    if options.expansions:
        for index, colour in enumerate(eeh):
            pygame.draw.circle(_sim.screen, (35, 48, 64), (768 + index % 7 * 36, 504 + index // 7 * 24), 11)
            pygame.draw.circle(_sim.screen, tuple(colour), (768 + index % 7 * 36, 504 + index // 7 * 24), 8)
        side_text("Matrix PWM diagram / normalized", 552, 17)
        for y in range(9):
            for x in range(18):
                physical = GRID[y * 18 + x]
                if physical >= 0:
                    value = matrix_registers[0x51 + physical]
                    shade = 30 + min(225, value * 7) if value else 14
                    pygame.draw.rect(_sim.screen, (shade, shade, shade), (749 + x * 16, 577 + y * 9, 12, 6))
    if preview is not None:
        frame = preview.show.frame()
        side_text(frame["title"], 674, 19, (93, 220, 248))
        side_text("120BPM / live-rendered pixels", 702, 17)
        native_surface = native_frame()
        last_status = {"official_simulator": True, "physical_camera_footage": False,
                       "scene": frame["scene"], "frames": frames, "pid": os.getpid(),
                       "time_ms": frame["time_ms"], "spaceagon_inputs_simulated": True,
                       "expansions_simulated": options.expansions, "eeh_writes": eeh_writes,
                       "matrix_mode": preview.matrix.displayed_mode, "matrix_frames": preview.matrix.frames_written,
                       "quality_requested": options.quality, "quality_rendered": preview._quality,
                       "adaptive_quality": False, "draw_ms": preview.metrics["draw_ms"], "heartbeat": host_time.time()}
        if frames % 15 == 0 or frames == 5:
            with open(str(RUN / "status.json"), "w") as handle:
                json.dump(last_status, handle)
        if gallery:
            if gallery_index < 0:
                gallery_index, gallery_since = 0, frames
                preview.show.select(0)
                preview.show.position += 3000
            elif frames - gallery_since >= 6:
                image = native_surface.copy()
                gallery_images.append(image)
                gallery_proof.append(dict(last_status))
                pygame.image.save(image, str(gallery / (SCENES[gallery_index] + "-lcd.png")))
                pygame.image.save(_sim.screen, str(gallery / (SCENES[gallery_index] + ".png")))
                gallery_index += 1
                if gallery_index == len(SCENES):
                    save_gallery()
                    raise SystemExit(0)
                preview.show.select(gallery_index)
                preview.show.position += int(preview.show.frame()["duration_ms"] * .45)
                gallery_since = frames
        if recorder and frames >= 5:
            if options.showcase == "tour" and not options.scene and options.seconds < 110:
                index = min(7, int(recorder.elapsed() * 8 / options.seconds))
                if index != last_tour_index:
                    preview.show.select(index)
                    recorder.events.append({"at": recorder.elapsed(), "label": SCENES[index].upper()})
                    last_tour_index = index
            elif frame["index"] != last_tour_index:
                recorder.events.append({"at": recorder.elapsed(), "label": frame["title"]})
                last_tour_index = frame["index"]
            recorded = native_surface if options.record_view == "lcd" else _sim.screen.copy()
            first_capture = recorder.start is None
            finished = recorder.capture(pygame, recorded, {"label": frame["title"], "scene": frame["scene"],
                                                  "time_ms": frame["time_ms"], "quality": preview._quality,
                                                  "ring_rgb": list(_sim._sim.led_state[1:13])})
            if first_capture:
                preview._ticks = app_module.time.ticks_ms()
            if finished:
                raise SystemExit(0)
    pygame.display.flip()
    if options.action and frames in (8, 11):
        name = options.action.upper()
        keymap = {value: key for key, value in {**JOY_KEYS, **TOUCH_KEYS}.items()}
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN if frames == 8 else pygame.KEYUP, key=keymap[name]))


_sim._sim.render_gui_now = render_gui
_sim.SCREENSHOT_DELAY = max(36 if options.action else 5, options.capture_frames)
sys.argv = [str(SIM / "run.py")] + (["--screenshot"] if options.screenshot else []) + ["horizon_preview.PreviewHorizon"]
try:
    run.sim_main()
except SystemExit as stopped:
    if options.screenshot and stopped.code in (None, 0) and native_surface is not None:
        pygame.image.save(native_surface, str(capture_output.with_name(capture_output.stem + "-lcd.png")))
        with open(str(SIM / "flow3r.png"), "rb") as source, open(str(capture_output), "wb") as destination:
            shutil.copyfileobj(source, destination)
        with open(str(capture_output.with_suffix(".json")), "w") as handle:
            json.dump(dict(last_status, source_hashes=source_hashes), handle, indent=2)
        print("Official Event Horizon screenshot:", capture_output)
    if recorder and recorder.finished and stopped.code in (None, 0):
        logfile = str(recorder.directory / "encode.log")
        with open(logfile, "w", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, str(HERE / "film_encode.py"), str(recorder.directory)],
                                    stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise SystemExit("Encoding failed; see " + logfile)
        print("Official Event Horizon recording:", recorder.output)
    raise
