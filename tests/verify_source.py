#!/usr/bin/env python3
"""Hardware-free verification for Timur Translator desktop sources.

Run before packaging:
    python tests/verify_source.py windows
    python tests/verify_source.py macos
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from array import array
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
platform_folder = sys.argv[1] if len(sys.argv) > 1 else "windows"
if platform_folder not in {"windows", "macos"}:
    raise SystemExit("Usage: verify_source.py [windows|macos]")
source_path = ROOT / platform_folder / "timur_translator.py"
source_text = source_path.read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise AssertionError(message)


# Catch the exact class of Tkinter crash fixed in v16.2: tuple spacing passed
# into a widget constructor instead of into pack()/grid().
tree = ast.parse(source_text, filename=str(source_path))
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func_name = ast.unparse(node.func)
    if func_name.endswith((".pack", ".grid", ".place")):
        continue
    for keyword in node.keywords:
        if keyword.arg in {"padx", "pady", "ipadx", "ipady", "bd", "borderwidth", "width", "height"} and isinstance(keyword.value, (ast.Tuple, ast.List)):
            fail(f"Invalid Tk widget spacing at {source_path}:{node.lineno}: {keyword.arg}={ast.unparse(keyword.value)}")

# Reject accidentally bundled API secrets.
if re.search(r"\bsk-[A-Za-z0-9_-]{20,}", source_text):
    fail(f"Possible embedded API key in {source_path}")

module_name = f"timur_verify_{platform_folder}"
spec = importlib.util.spec_from_file_location(module_name, source_path)
if spec is None or spec.loader is None:
    fail(f"Could not import {source_path}")
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)

assert module.LANGUAGES["Türkçe"] == "tr"

# Stereo downmix and sample-rate conversion.
stereo = array("h", [1000, -1000, 3000, 1000, -2000, -4000])
assert list(module.downmix_to_mono(stereo, 2)) == [0, 2000, -3000]
resampled = module.resample_mono_pcm16(array("h", range(480)), 48_000, 24_000)
assert len(resampled) == 240
config = module.AudioInputConfig(1, "synthetic mic", 48_000, 2, 9600)
normalized = module.normalize_input_pcm16(array("h", [1000, 3000] * 480).tobytes(), config)
assert len(normalized) == 480

# Float loopback frames are clipped, downmixed and resampled to PCM16.
loopback = np.array([[1.0, -1.0], [0.5, 0.5], [-2.0, -2.0], [0.0, 0.0]], dtype=np.float32)
pcm = module._float_audio_to_target_pcm16(loopback)
pcm_values = array("h")
pcm_values.frombytes(pcm)
assert len(pcm_values) == 2
assert all(-32768 <= sample <= 32767 for sample in pcm_values)

# Realtime session payload and headset priority.
event = module.build_session_update_event("tr", "near_field")
assert event["type"] == "session.update"
assert event["session"]["audio"]["output"]["language"] == "tr"
assert event["session"]["audio"]["input"]["transcription"]["model"] == "gpt-realtime-whisper"
assert event["session"]["audio"]["input"]["noise_reduction"] == {"type": "near_field"}

devices = [
    module.DeviceInfo(1, "Laptop Mic Array", 2, 44_100, "MME", True),
    module.DeviceInfo(2, "USB Headset Microphone", 1, 48_000, "Windows WASAPI", False),
    module.DeviceInfo(3, "Speaker output", 2, 48_000, "Windows WDM-KS", False),
]
ordered = module.ordered_input_devices(devices, prefer_headset=True)
assert ordered[0].index == 2
assert module.choose_default_position(devices, 3) == 0

print(f"Verified {platform_folder}: syntax, Tk spacing, secrets, PCM16 pipeline, session payload and headset priority")
