"""Compose original Event Horizon trailer music; standard library, no samples.

120 BPM, D minor, stereo PCM. This is a video soundtrack, not badge runtime
audio. Synthesis and arrangement are deterministic and covered by LICENSE.
"""
import argparse
from array import array
import json
import math
from pathlib import Path
import sys
import wave

BPM = 120
_SINE = tuple(math.sin(index * 2 * math.pi / 4096) for index in range(4096))
_CHORDS = ((50, 53, 57, 64), (46, 50, 53, 57), (48, 53, 57, 67), (48, 52, 55, 62))
_ARP = (0, 2, 3, 1, 2, 3, 2, 1, 0, 3, 2, 1, 3, 2, 1, 2)
_MELODY = (74, 77, 81, 76, 74, 72, 69, 72, 74, 81, 79, 77, 76, 72, 69, 74)
_NAMES = ("Intro", "Starflight", "Tunnel", "Terrain", "Planet", "Kaleidoscope", "Black hole", "Finale")
# Pad, arp, bass, drums, lead. A quieter middle act gives the climax contrast.
_LEVELS = ((.045, .025, 0, 0, 0), (.045, .043, .12, .74, .018),
           (.042, .052, .14, .87, .025), (.052, .038, .12, .75, .030),
           (.065, .027, .08, .46, .040), (.047, .056, .14, .92, .038),
           (.047, .062, .17, 1.0, .044), (.068, .035, .085, .48, .040))


def _sin(cycles):
    return _SINE[int(cycles * 4096) & 4095]


def _frequency(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def _pan(position):
    return math.sqrt((1 - position) / 2), math.sqrt((1 + position) / 2)


def _timeline(seconds):
    durations = (8, 16, 16, 16, 16, 16, 20, 12) if seconds == 120 else (6,) * 8
    start, result = 0, []
    for name, duration in zip(_NAMES, durations):
        result.append({"name": name, "start": start, "end": start + duration})
        start += duration
    return result


def _section(timeline, seconds):
    for index, entry in enumerate(timeline):
        if seconds < entry["end"]:
            return index
    return len(timeline) - 1


def _tone(mix, rate, start, duration, midi, gain, pan, voice):
    first, length = int(start * rate), int(duration * rate)
    length = min(length, len(mix) // 2 - first)
    if length <= 0 or gain == 0:
        return
    frequency = _frequency(midi)
    increment = frequency / rate
    left, right = _pan(pan)
    attack = .22 if voice == "pad" else .007 if voice == "lead" else .003
    release = .42 if voice == "pad" else .13 if voice == "lead" else .06
    position = 0.0
    # Different starting phases avoid a repeated four-voice impulse at bars.
    detune_phase = (midi % 7) / 7
    for index in range(length):
        t = index / rate
        fraction = index / max(1, length - 1)
        envelope = min(1, t / attack, (duration - t) / release)
        if voice == "pad":
            value = (_sin(position) * .64 + _sin(position * 1.002 + detune_phase) * .25
                     + _sin(position * 2 + .12) * .11)
            # Sidechain breathing leaves room for the kick without compression.
            beat_time = (start + t) % .5
            envelope *= .78 + .22 * min(1, beat_time / .14)
        elif voice == "bass":
            value = _sin(position) * .72 + _sin(position * 2) * .20 + _sin(position * 3) * .08
            envelope *= (1 - fraction) ** .7
        elif voice == "lead":
            vibrato = _sin(t * 5) * .003
            value = _sin(position + vibrato) * .72 + _sin(position * 2) * .19 + _sin(position * 3) * .09
            envelope *= 1 - fraction * .55
        else:
            # Three controlled harmonics give a soft chiptune attack, rather
            # than an unbandlimited square wave full of aliasing.
            value = _sin(position) * .78 + _sin(position * 3) * .16 + _sin(position * 5) * .06
            envelope *= (1 - fraction) * (1 - fraction)
        value *= gain * max(0, envelope)
        offset = (first + index) * 2
        mix[offset] += value * left
        mix[offset + 1] += value * right
        position += increment


def _percussion(rate, seed):
    state = seed & 0x7fffffff
    noise = []
    for index in range(rate):
        state = (state * 1103515245 + 12345) & 0x7fffffff
        noise.append(state / 1073741824 - 1)
    kick, snare, hat = array("f"), array("f"), array("f")
    for index in range(int(rate * .26)):
        t = index / rate
        cycles = 43 * t + 97 * .025 * (1 - math.exp(-t / .025))
        body = _sin(cycles) * math.exp(-t / .071)
        click = (noise[index] - noise[index - 1]) * math.exp(-t / .004) * .07
        kick.append(body + click)
    for index in range(int(rate * .19)):
        t = index / rate
        high = (noise[(index + 3001) % rate] - noise[(index + 3000) % rate]) * .30
        body = _sin(181 * t) * .22
        snare.append((high + body) * math.exp(-t / .046) * min(1, t / .0018))
    for index in range(int(rate * .065)):
        t = index / rate
        high = noise[(index + 7019) % rate] - noise[(index + 7018) % rate]
        hat.append(high * math.exp(-t / .013) * .25)
    return kick, snare, hat, noise


def _sample(mix, rate, when, source, gain, pan=0):
    first = int(when * rate)
    length = min(len(source), len(mix) // 2 - first)
    left, right = _pan(pan)
    for index in range(max(0, length)):
        value, offset = source[index] * gain, (first + index) * 2
        mix[offset] += value * left
        mix[offset + 1] += value * right


def _riser(mix, rate, end, noise, gain):
    duration = 1.75
    first = max(0, int((end - duration) * rate))
    last = min(int(end * rate), len(mix) // 2)
    previous = 0
    for frame in range(first, last):
        t = (frame - first) / rate
        progress = min(1, t / duration)
        raw = noise[frame % len(noise)]
        # Low-pass noise opens over the riser; no external sweep sample.
        previous += (raw - previous) * (.025 + progress * .21)
        shimmer = _sin(300 * t + 350 * t * t) * .14
        value = (previous + shimmer) * gain * progress * progress
        pan = _sin(t * .55) * .55
        mix[frame * 2] += value * (.65 - pan * .25)
        mix[frame * 2 + 1] += value * (.65 + pan * .25)


def _master(mix, rate, seconds):
    # Cross-channel dotted-eighth and half-note echoes form an original,
    # deterministic space around the notes. Feedback stays well below unity.
    short, long = int(rate * .375), int(rate * .75)
    low_left = low_right = 0.0
    previous_left = previous_right = dc_left = dc_right = 0.0
    dc_coefficient = math.exp(-2 * math.pi * 12 / rate)
    frames = len(mix) // 2
    fade_out = 3.5 if seconds == 120 else 2.5
    for frame in range(frames):
        offset = frame * 2
        left, right = mix[offset], mix[offset + 1]
        if frame >= short:
            left += mix[(frame - short) * 2 + 1] * .18
            right += mix[(frame - short) * 2] * .18
        if frame >= long:
            left += mix[(frame - long) * 2] * .075
            right += mix[(frame - long) * 2 + 1] * .075
        # Gentle master low-pass controls high-frequency synth/noise energy.
        low_left += (left - low_left) * .70
        low_right += (right - low_right) * .70
        # Remove the pitch-swept kick's tiny DC component before the fade.
        dc_left = low_left - previous_left + dc_coefficient * dc_left
        dc_right = low_right - previous_right + dc_coefficient * dc_right
        previous_left, previous_right = low_left, low_right
        fade_in = min(1, frame / (rate * 1.15))
        ending = min(1, (frames - 1 - frame) / (rate * fade_out))
        gain = fade_in * ending * ending
        mix[offset], mix[offset + 1] = dc_left * gain, dc_right * gain


def compose(seconds=120, rate=24000, seed=2026, progress=None):
    if seconds not in (48, 120) or rate not in (16000, 24000, 44100):
        raise ValueError("Choose48/120 seconds and16000/24000/44100 Hz")
    timeline = _timeline(seconds)
    mix = array("f", [0.0]) * (seconds * rate * 2)
    kick, snare, hat, noise = _percussion(rate, seed)
    last_section = None
    for step in range(seconds * 8):
        when = step * .125
        section = _section(timeline, when)
        if section != last_section:
            if progress:
                progress("Composing " + timeline[section]["name"])
            last_section = section
        pad, arp, bass, drums, lead = _LEVELS[section]
        # Hold the tonic for the closing two bars instead of ending on a loop.
        chord = _CHORDS[0] if when >= seconds - 4 else _CHORDS[(step // 16) % 4]
        if step % 16 == 0:
            for voice, note in enumerate(chord):
                _tone(mix, rate, when, 2.65, note, pad, (-.72, -.24, .24, .72)[voice], "pad")
        note = chord[_ARP[step % len(_ARP)]] + 24
        if section == 0 and step % 2:
            continue
        if section == 4 and step % 2:
            arp *= .45
        if when >= seconds - 2:
            arp *= .45
        accent = 1 if step % 4 == 0 else .73 if step % 2 == 0 else .53
        _tone(mix, rate, when, .205, note, arp * accent, (-.48, .12, .48, -.12)[step % 4], "arp")
        if step % 4 == 0:
            _tone(mix, rate, when, .39, min(chord) - 12, bass, 0, "bass")
            if drums and when < seconds - 2:
                _sample(mix, rate, when, kick, drums * .34)
        if step % 16 in (4, 12) and drums and when < seconds - 3:
            _sample(mix, rate, when, snare, drums * .34, .06)
        if step % 2 == 0 and drums and when < seconds - 2:
            _sample(mix, rate, when, hat, drums * (.24 if step % 4 == 2 else .13), -.30 if step % 4 else .3)
        if section in (5, 6) and step % 8 in (5, 7):
            _sample(mix, rate, when, hat, .07, .45)
        if lead and step % 8 == 0:
            _tone(mix, rate, when + .02, .67, _MELODY[(step // 8) % len(_MELODY)],
                  lead, .20 * (-1 if step % 16 else 1), "lead")
    for section in timeline[1:]:
        _riser(mix, rate, section["start"], noise, .075 if section["name"] == "Black hole" else .045)
    if progress:
        progress("Mastering stereo echoes and fade")
    _master(mix, rate, seconds)
    peak = max(abs(value) for value in mix)
    rms = math.sqrt(sum(value * value for value in mix) / len(mix))
    normalization = min(.92 / peak, .17 / rms) if peak and rms else 1
    pcm = array("h")
    peak_integer, energy, dc = 0, 0, 0
    stereo_difference = 0
    previous = 0
    for index, value in enumerate(mix):
        sample = int(round(value * normalization * 32767))
        if not -32768 <= sample <= 32767:
            raise ArithmeticError("Synthesis clipping detected")
        pcm.append(sample)
        peak_integer = max(peak_integer, abs(sample))
        energy += sample * sample
        dc += sample
        if index % 2:
            stereo_difference += (sample - previous) ** 2
        previous = sample
    stats = {"title": "Event Horizon / Signal Beyond", "composition": "Original procedural composition",
             "license": "MIT", "video_soundtrack_only": True, "tempo_bpm": BPM,
             "key": "D minor", "seconds": seconds, "sample_rate": rate, "channels": 2,
             "sample_width_bits": 16, "frames": len(pcm) // 2, "seed": seed,
             "dc_block_hz": 12,
             "peak": peak_integer / 32768, "rms": math.sqrt(energy / len(pcm)) / 32768,
             "dc_offset": dc / len(pcm) / 32768,
             "stereo_difference_rms": math.sqrt(stereo_difference / (len(pcm) // 2)) / 32768,
             "clipped_samples": 0, "normalization_gain": normalization,
             "final_samples": list(pcm[-2:]), "timeline": timeline}
    stats["rms_dbfs"] = 20 * math.log10(stats["rms"]) if stats["rms"] else None
    if stats["peak"] >= .95 or stats["final_samples"] != [0, 0]:
        raise ArithmeticError("Mastering validation failed")
    return pcm, stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, choices=(48, 120), default=120)
    parser.add_argument("--rate", type=int, choices=(16000, 24000, 44100), default=24000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or Path("work/horizon-media") / ("event-horizon-%d.wav" % args.seconds)
    output.parent.mkdir(parents=True, exist_ok=True)
    pcm, metadata = compose(args.seconds, args.rate, args.seed, progress=lambda message: print(message, flush=True))
    # wave requires little-endian PCM regardless of the host's array byte order.
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(args.rate)
        handle.writeframes(pcm.tobytes())
    metadata["file"] = output.name
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: metadata[key] for key in ("file", "seconds", "peak", "rms", "rms_dbfs", "clipped_samples")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
