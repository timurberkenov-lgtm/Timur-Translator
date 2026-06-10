#!/usr/bin/env python3
"""
Timur Translator Realtime - Windows Interview Audio v12 build.

Windows microphone OR system-audio loopback -> OpenAI Realtime Translation -> live subtitles.

Key reliability changes:
- validates the selected Windows input device before leaving the setup screen;
- opens the mic at a device-supported native sample rate;
- downmixes and resamples locally to 24 kHz mono PCM16 for the translation socket;
- routes worker-thread events through a UI queue instead of touching Tk directly;
- writes a local debug log for startup, microphone and WebSocket failures;
- labels Windows host APIs and automatically skips fragile Realtek/WDM-KS duplicates;
- prefers an available headset microphone over the laptop mic in AUTO mode;
- switches to a newly connected headset mic while translation is running;
- reconnects to another usable microphone if the current input disappears;
- checks the OpenAI Realtime socket before replacing the setup screen;
- configures source-language transcription;
- keeps the v5 realtime streaming path that already worked on Windows;
- renders source and translated transcripts independently in equal-width columns.
- adds Windows WASAPI loopback capture for YouTube, Zoom, Meet and interview audio.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import queue
import sys
import threading
import time
import traceback
from array import array
from dataclasses import dataclass
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from typing import Callable, Optional
import tkinter as tk

APP_NAME = "Timur Translator Realtime"
APP_DIR = Path.home() / ".timur_translator_realtime"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "translator_debug.log"
REALTIME_URL = "wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate"
TARGET_SAMPLE_RATE = 24_000
TARGET_CHANNELS = 1
FRAME_MS = 200
TARGET_FRAMES_PER_BUFFER = TARGET_SAMPLE_RATE * FRAME_MS // 1000
MAX_SEGMENTS = 100
SEGMENT_IDLE_SECONDS = 1.05
RECONNECT_DELAY_SECONDS = 1.0
DEVICE_SCAN_INTERVAL_SECONDS = 3.0
UI_POLL_MS = 45
STATS_EMIT_INTERVAL_SECONDS = 1.0
API_PREFLIGHT_TIMEOUT_SECONDS = 8.0
API_PREFLIGHT_EVENT_WINDOW_SECONDS = 3.5

BG, SURFACE, SURFACE2, BORDER = "#0a0a0f", "#13131a", "#1c1c26", "#2e2e3e"
TEXT, TEXT2, TEXT3 = "#eeeef5", "#a1a1c0", "#666684"
ACCENT, GREEN, AMBER, RED = "#6c63ff", "#00d4a0", "#ffb347", "#ff5e5e"
FONT = "Helvetica"

LANGUAGES = {
    "Русский": "ru",
    "English": "en",
    "Deutsch": "de",
    "Français": "fr",
    "Español": "es",
    "Português": "pt",
    "Italiano": "it",
    "日本語": "ja",
    "中文": "zh",
    "한국어": "ko",
    "हिन्दी": "hi",
    "Bahasa Indonesia": "id",
    "Tiếng Việt": "vi",
    "Türkçe": "tr",
}

AUDIO_SOURCE_OPTIONS = {
    "System audio · YouTube / Zoom / Meet / interview (recommended)": "system",
    "Microphone · translate my own voice": "microphone",
}
SYSTEM_AUDIO_SAMPLE_RATE = 48_000
SYSTEM_AUDIO_LABEL = "System audio loopback · default Windows playback device"


THEME_PRESETS = {
    "Midnight Violet": {"background": "#090a10", "accent": "#7367ff"},
    "Graphite Mint": {"background": "#101216", "accent": "#00c995"},
    "Ocean Glass": {"background": "#07131e", "accent": "#3da7ff"},
    "Crimson Night": {"background": "#16090f", "accent": "#ff5e7d"},
    "Soft Light": {"background": "#f2f4fa", "accent": "#5b5ce2"},
    "Custom": {"background": "#090a10", "accent": "#7367ff"},
}

APPEARANCE_DEFAULTS = {
    "theme": "Midnight Violet",
    "background": THEME_PRESETS["Midnight Violet"]["background"],
    "accent": THEME_PRESETS["Midnight Violet"]["accent"],
    "opacity": 0.96,
    "always_on_top": True,
    "show_original": True,
    "show_diagnostics": False,
    "compact_overlay": False,
    "transparent_canvas": False,
    "original_font_size": 14,
    "translation_font_size": 18,
    "text_padding": 16,
    "full_geometry": "1180x730",
    "overlay_geometry": "900x260",
}


def _clamp_float(value: object, minimum: float, maximum: float, fallback: float) -> float:
    try:
        return min(max(float(value), minimum), maximum)
    except (TypeError, ValueError):
        return fallback


def _clamp_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    try:
        return min(max(int(float(value)), minimum), maximum)
    except (TypeError, ValueError):
        return fallback


def _safe_hex(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.lower()
        except ValueError:
            pass
    return fallback.lower()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = _safe_hex(value, "#000000")
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _blend_hex(first: str, second: str, amount: float) -> str:
    amount = _clamp_float(amount, 0.0, 1.0, 0.0)
    a = _hex_to_rgb(first)
    b = _hex_to_rgb(second)
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def _is_light(value: str) -> bool:
    red, green, blue = _hex_to_rgb(value)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) > 168


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    text2: str
    text3: str
    accent: str
    green: str = GREEN
    amber: str = AMBER
    red: str = RED


def load_appearance(config: Optional[dict] = None) -> dict:
    source = (config or load_config()).get("appearance", {})
    source = source if isinstance(source, dict) else {}
    # v11 moves raw STREAM counters into an opt-in diagnostic mode. Existing
    # v10 configs are migrated once so the main window opens cleanly.
    ui_schema_version = _clamp_int(source.get("_ui_schema_version", 0), 0, 999, 0)
    prefs = dict(APPEARANCE_DEFAULTS)
    prefs.update(source)
    if ui_schema_version < 11:
        prefs["show_diagnostics"] = False
    prefs["_ui_schema_version"] = 11
    theme = str(prefs.get("theme", "Midnight Violet"))
    if theme not in THEME_PRESETS:
        theme = "Custom"
    preset = THEME_PRESETS[theme]
    prefs["theme"] = theme
    prefs["background"] = _safe_hex(prefs.get("background"), preset["background"])
    prefs["accent"] = _safe_hex(prefs.get("accent"), preset["accent"])
    prefs["opacity"] = _clamp_float(prefs.get("opacity"), 0.45, 1.0, 0.96)
    prefs["always_on_top"] = bool(prefs.get("always_on_top", True))
    prefs["show_original"] = bool(prefs.get("show_original", True))
    prefs["show_diagnostics"] = bool(prefs.get("show_diagnostics", True))
    prefs["compact_overlay"] = bool(prefs.get("compact_overlay", False))
    prefs["transparent_canvas"] = bool(prefs.get("transparent_canvas", False))
    prefs["original_font_size"] = _clamp_int(prefs.get("original_font_size"), 10, 28, 14)
    prefs["translation_font_size"] = _clamp_int(prefs.get("translation_font_size"), 12, 38, 18)
    prefs["text_padding"] = _clamp_int(prefs.get("text_padding"), 6, 36, 16)
    for key, fallback in (("full_geometry", "1180x730"), ("overlay_geometry", "900x260")):
        geometry = str(prefs.get(key, fallback))
        prefs[key] = geometry if "x" in geometry else fallback
    return prefs


def build_palette(prefs: dict) -> Palette:
    bg = _safe_hex(prefs.get("background"), BG)
    accent = _safe_hex(prefs.get("accent"), ACCENT)
    if _is_light(bg):
        text = "#161722"
        text2 = "#4e5264"
        text3 = "#7d849c"
        surface = _blend_hex(bg, "#000000", 0.045)
        surface2 = _blend_hex(bg, "#000000", 0.085)
        border = _blend_hex(bg, "#000000", 0.18)
    else:
        text = "#f4f5fb"
        text2 = "#b8bdd1"
        text3 = "#737b98"
        surface = _blend_hex(bg, "#ffffff", 0.055)
        surface2 = _blend_hex(bg, "#ffffff", 0.10)
        border = _blend_hex(bg, "#ffffff", 0.20)
    return Palette(bg, surface, surface2, border, text, text2, text3, accent)


def save_appearance(prefs: dict) -> None:
    config = load_config()
    config["appearance"] = dict(prefs)
    save_config(config)


def _ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    _ensure_app_dir()
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
        encoding="utf-8",
    )
    logging.info("=" * 72)
    logging.info("Starting %s", APP_NAME)
    logging.info("Python: %s", sys.version.replace("\n", " "))
    logging.info("Platform: %s", sys.platform)


def load_config() -> dict:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config: dict) -> None:
    _ensure_app_dir()
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def check_deps() -> list[str]:
    missing: list[str] = []
    try:
        import websocket  # noqa: F401
    except ImportError:
        missing.append("websocket-client")
    try:
        import pyaudio  # noqa: F401
    except ImportError:
        missing.append("PyAudio")
    try:
        import soundcard  # noqa: F401
    except ImportError:
        missing.append("SoundCard")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    return missing


def stable_safety_id() -> str:
    raw = f"timur-translator:{os.path.expanduser('~')}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()


def _mojibake_score(value: str) -> int:
    suspicious = ("Р", "С", "Ð", "Ñ", "�")
    return sum(value.count(marker) for marker in suspicious)


def _repair_device_name_encoding(value: str) -> str:
    if _mojibake_score(value) < 2:
        return value

    best = value
    best_score = _mojibake_score(value)
    for encoding in ("cp1251", "latin-1"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        candidate_score = _mojibake_score(candidate)
        if candidate_score < best_score:
            best = candidate
            best_score = candidate_score
    return best


def safe_device_name(name: object) -> str:
    value = _repair_device_name_encoding(str(name))
    return " ".join(value.split())


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    max_input_channels: int
    default_sample_rate: int
    host_api: str
    is_default: bool = False

    @property
    def display_name(self) -> str:
        suffix = " · DEFAULT" if self.is_default else ""
        return f"[{self.index}] {self.name} · {self.host_api}{suffix}"


@dataclass(frozen=True)
class AudioInputConfig:
    device_index: int
    device_name: str
    sample_rate: int
    channels: int
    frames_per_buffer: int

    @property
    def description(self) -> str:
        return f"{self.device_name} · {self.sample_rate} Hz · {self.channels} ch"


def _host_api_name(pa, info: dict) -> str:
    try:
        host_index = int(info.get("hostApi", -1))
        if host_index >= 0:
            host = pa.get_host_api_info_by_index(host_index)
            return safe_device_name(host.get("name", f"Host API {host_index}"))
    except Exception:
        logging.exception("Could not read host API metadata")
    return "Unknown host API"


def list_input_devices(verbose: bool = True) -> list[DeviceInfo]:
    import pyaudio

    pa = pyaudio.PyAudio()
    devices: list[DeviceInfo] = []
    try:
        try:
            default_index = int(pa.get_default_input_device_info().get("index", -1))
        except Exception:
            default_index = -1
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            channels = int(info.get("maxInputChannels", 0) or 0)
            if channels <= 0:
                continue
            default_rate = int(round(float(info.get("defaultSampleRate", 0) or 0)))
            devices.append(
                DeviceInfo(
                    index=index,
                    name=safe_device_name(info.get("name", f"Device {index}")),
                    max_input_channels=channels,
                    default_sample_rate=default_rate,
                    host_api=_host_api_name(pa, info),
                    is_default=index == default_index,
                )
            )
    finally:
        pa.terminate()
    if verbose:
        logging.info("Detected %d input devices", len(devices))
        for device in devices:
            logging.info(
                "Input device [%d] %s | host=%s | default=%s | max_channels=%d | default_rate=%d",
                device.index,
                device.name,
                device.host_api,
                device.is_default,
                device.max_input_channels,
                device.default_sample_rate,
            )
    return devices


def _device_text(device: DeviceInfo) -> str:
    return f"{device.name} {device.host_api}".lower()


MIC_WORDS = (
    "microphone", "mic array", "микрофон", "микрофоны", "набор микрофонов",
    "mic", "input", "вход",
)
HEADSET_WORDS = (
    "headset", "hands-free", "hands free", "headphone", "earphone", "earbuds",
    "гарнитура", "наушник", "airpods", "buds", "bluetooth", "bt ", "wireless",
    "jabra", "logitech", "hyperx", "razer", "steelseries", "sony", "jbl",
)
OUTPUT_WORDS = ("output", "speaker", "динамик", "speakers")
LOOPBACK_WORDS = ("stereo", "mix", "loopback", "blackhole", "soundflower", "aggregate")


def _contains_any(value: str, words: tuple[str, ...]) -> bool:
    return any(word in value for word in words)


def _looks_like_microphone(device: DeviceInfo) -> bool:
    lowered = _device_text(device)
    return _contains_any(lowered, MIC_WORDS)


def _is_headset_microphone(device: DeviceInfo) -> bool:
    lowered = _device_text(device)
    # list_input_devices() already filters out devices with zero input channels.
    # Some Bluetooth drivers expose names such as "AirPods Hands-Free" without
    # the literal word "microphone", so the headset marker itself is enough.
    return _contains_any(lowered, HEADSET_WORDS) and not _contains_any(lowered, LOOPBACK_WORDS)


def _device_penalty(device: DeviceInfo) -> int:
    lowered = _device_text(device)
    penalty = 0
    if _contains_any(lowered, LOOPBACK_WORDS):
        penalty += 500
    # Do not reject a headset microphone just because its Windows name also
    # contains the word "headphones" / "наушники". Reject output-only devices.
    if _contains_any(lowered, OUTPUT_WORDS) and not _looks_like_microphone(device):
        penalty += 250
    # WDM-KS entries are low-level kernel-streaming duplicates. They often appear
    # in the list but reject shared desktop capture. Keep them as last-resort only.
    if "wdm-ks" in lowered or "wdm ks" in lowered:
        penalty += 180
    return penalty


def _device_score(device: DeviceInfo, prefer_headset: bool = True) -> int:
    lowered = _device_text(device)
    score = 0
    if device.is_default:
        score += 120
    if "wasapi" in lowered:
        score += 65
    elif "mme" in lowered:
        score += 45
    elif "directsound" in lowered:
        score += 30
    if _looks_like_microphone(device):
        score += 75
    if "mic array" in lowered or "набор микрофонов" in lowered:
        score += 20
    if prefer_headset and _is_headset_microphone(device):
        score += 260
    return score - _device_penalty(device)


def ordered_input_devices(
    devices: list[DeviceInfo], preferred: Optional[DeviceInfo] = None, prefer_headset: bool = True
) -> list[DeviceInfo]:
    result: list[DeviceInfo] = []
    if preferred is not None:
        result.append(preferred)
    for device in sorted(devices, key=lambda item: _device_score(item, prefer_headset), reverse=True):
        if device not in result:
            result.append(device)
    return result


def choose_default_position(devices: list[DeviceInfo], saved_index: Optional[int]) -> int:
    # Index 0 in the UI is AUTO. Only preserve a saved device when it is not one
    # of the fragile low-level WDM-KS duplicates.
    for position, device in enumerate(devices, start=1):
        if saved_index == device.index and _device_penalty(device) < 180:
            return position
    return 0

def _rate_candidates(default_rate: int) -> list[int]:
    candidates = [TARGET_SAMPLE_RATE, default_rate, 48_000, 44_100, 32_000, 16_000]
    result: list[int] = []
    for rate in candidates:
        if rate and rate not in result:
            result.append(int(rate))
    return result


def find_supported_input_config(device: DeviceInfo) -> AudioInputConfig:
    """Return an input format PortAudio can actually open on this Windows device."""
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        channel_candidates = [1]
        if device.max_input_channels >= 2:
            channel_candidates.append(2)
        for channels in channel_candidates:
            for rate in _rate_candidates(device.default_sample_rate):
                try:
                    pa.is_format_supported(
                        rate,
                        input_device=device.index,
                        input_channels=channels,
                        input_format=pyaudio.paInt16,
                    )
                except (ValueError, OSError):
                    continue

                frames = max(1, rate * FRAME_MS // 1000)
                stream = None
                try:
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=device.index,
                        frames_per_buffer=frames,
                    )
                    stream.read(frames, exception_on_overflow=False)
                except Exception as exc:
                    logging.warning(
                        "Probe rejected [%d] %s at %d Hz %d ch: %s",
                        device.index,
                        device.name,
                        rate,
                        channels,
                        exc,
                    )
                    continue
                finally:
                    if stream is not None:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except Exception:
                            pass

                config = AudioInputConfig(
                    device_index=device.index,
                    device_name=device.name,
                    sample_rate=rate,
                    channels=channels,
                    frames_per_buffer=frames,
                )
                logging.info("Selected input config: %s", config.description)
                return config
    finally:
        pa.terminate()

    raise RuntimeError(
        "Windows не смогла открыть выбранный вход. Выбери другой микрофон, например "
        "Realtek HD Audio Mic Array input, и проверь доступ к микрофону в настройках Windows."
    )


def find_best_supported_input_config(
    devices: list[DeviceInfo], preferred: Optional[DeviceInfo] = None, prefer_headset: bool = True
) -> tuple[AudioInputConfig, DeviceInfo, bool]:
    """Probe safe Windows inputs and return the first microphone PortAudio can open.

    The preferred device is tested first. When it is a dead driver duplicate, the
    function transparently falls back to a healthier MME/WASAPI/DirectSound entry.
    """
    failures: list[str] = []
    for device in ordered_input_devices(devices, preferred, prefer_headset=prefer_headset):
        # Never auto-select obvious speaker/stereo-loopback entries. If the user
        # manually picked one, still allow one explicit probe.
        if device is not preferred and _device_penalty(device) >= 250:
            logging.info("Auto-skip unsuitable input [%d] %s", device.index, device.display_name)
            continue
        try:
            config = find_supported_input_config(device)
            used_fallback = preferred is not None and device.index != preferred.index
            return config, device, used_fallback
        except Exception as exc:
            failures.append(f"[{device.index}] {device.name} ({device.host_api}): {exc}")
            logging.warning("Input candidate failed: %s", failures[-1])

    detail = "\n".join(failures[-8:]) if failures else "No input devices were detected."
    raise RuntimeError(
        "Windows не смогла открыть ни один подходящий микрофон. Проверь доступ к микрофону "
        "в настройках Windows и закрой программы, которые могли забрать его в монопольный режим.\n\n"
        f"Проверенные входы:\n{detail}"
    )



def find_available_headset_input_config(current_device_index: int) -> Optional[AudioInputConfig]:
    """Return a newly available, usable headset microphone for runtime switching."""
    try:
        devices = list_input_devices()
    except Exception:
        logging.exception("Could not enumerate devices during headset scan")
        return None

    candidates = [
        device for device in devices
        if device.index != current_device_index
        and _is_headset_microphone(device)
        and _device_penalty(device) < 250
    ]
    for device in sorted(candidates, key=lambda item: _device_score(item, True), reverse=True):
        try:
            return find_supported_input_config(device)
        except Exception:
            logging.warning("Runtime headset candidate failed: %s", device.display_name)
    return None


def _config_is_headset_microphone(config: AudioInputConfig) -> bool:
    lowered = config.device_name.lower()
    return _contains_any(lowered, HEADSET_WORDS) and not _contains_any(lowered, LOOPBACK_WORDS)

def _samples_from_pcm16(raw: bytes) -> array:
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _samples_to_pcm16(samples: array) -> bytes:
    if sys.byteorder != "little":
        samples = array("h", samples)
        samples.byteswap()
    return samples.tobytes()


def downmix_to_mono(samples: array, channels: int) -> array:
    if channels == 1:
        return samples
    if channels <= 0:
        raise ValueError("channels must be positive")

    usable = len(samples) - (len(samples) % channels)
    mono = array("h")
    append = mono.append
    for offset in range(0, usable, channels):
        total = 0
        for channel in range(channels):
            total += samples[offset + channel]
        append(int(total / channels))
    return mono


def resample_mono_pcm16(samples: array, source_rate: int, target_rate: int = TARGET_SAMPLE_RATE) -> array:
    """Small pure-Python linear resampler, fast enough for short speech frames."""
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample rates must be positive")
    if source_rate == target_rate or len(samples) < 2:
        return samples

    output_length = max(1, round(len(samples) * target_rate / source_rate))
    ratio = source_rate / target_rate
    result = array("h")
    append = result.append
    last_index = len(samples) - 1

    for out_index in range(output_length):
        position = out_index * ratio
        left = int(position)
        if left >= last_index:
            append(samples[last_index])
            continue
        fraction = position - left
        value = int(samples[left] + (samples[left + 1] - samples[left]) * fraction)
        append(max(-32768, min(32767, value)))
    return result


def normalize_input_pcm16(raw: bytes, config: AudioInputConfig) -> bytes:
    samples = _samples_from_pcm16(raw)
    mono = downmix_to_mono(samples, config.channels)
    normalized = resample_mono_pcm16(mono, config.sample_rate, TARGET_SAMPLE_RATE)
    return _samples_to_pcm16(normalized)


def _system_audio_config(device_name: str = SYSTEM_AUDIO_LABEL) -> AudioInputConfig:
    return AudioInputConfig(
        device_index=-1,
        device_name=device_name,
        sample_rate=SYSTEM_AUDIO_SAMPLE_RATE,
        channels=2,
        frames_per_buffer=max(1, SYSTEM_AUDIO_SAMPLE_RATE * FRAME_MS // 1000),
    )


def _find_default_loopback_microphone():
    """Return SoundCard's WASAPI loopback microphone for the active playback endpoint."""
    import soundcard as sc

    speaker = sc.default_speaker()
    if speaker is None:
        raise RuntimeError("Windows default playback device was not found")
    # SoundCard accepts a backend id or a name substring. Prefer the backend id,
    # then fall back to the visible name for older Windows backends.
    speaker_id = getattr(speaker, "id", None)
    try:
        loopback = sc.get_microphone(id=speaker_id, include_loopback=True) if speaker_id else None
    except Exception:
        loopback = None
    if loopback is None:
        loopback = sc.get_microphone(id=str(getattr(speaker, "name", speaker)), include_loopback=True)
    if loopback is None:
        raise RuntimeError("WASAPI loopback endpoint was not found for the default playback device")
    speaker_name = safe_device_name(getattr(speaker, "name", str(speaker)))
    return speaker, loopback, speaker_name


def find_system_audio_input_config() -> AudioInputConfig:
    """Open a short WASAPI loopback probe so setup fails visibly instead of silently."""
    speaker, loopback, speaker_name = _find_default_loopback_microphone()
    frames = max(512, SYSTEM_AUDIO_SAMPLE_RATE * FRAME_MS // 1000)
    blocksize = max(frames * 2, 2048)
    try:
        with loopback.recorder(samplerate=SYSTEM_AUDIO_SAMPLE_RATE, blocksize=blocksize) as recorder:
            recorder.record(numframes=min(frames, 2048))
    except Exception as exc:
        raise RuntimeError(
            "Windows не смогла открыть системный звук через WASAPI loopback. "
            "Проверь, что в Windows выбраны рабочие динамики или наушники, затем включи видео ещё раз. "
            f"Техническая причина: {exc}"
        ) from exc
    config = _system_audio_config(f"System audio loopback · {speaker_name}")
    logging.info("Selected system audio loopback: %s", config.description)
    return config


def _float_audio_to_target_pcm16(data) -> bytes:
    """Convert SoundCard frames×channels floats to OpenAI 24 kHz mono PCM16."""
    import numpy as np

    samples = np.asarray(data, dtype=np.float32)
    if samples.size == 0:
        return b""
    if samples.ndim == 1:
        mono = samples
    else:
        mono = samples.mean(axis=1)
    mono = np.clip(mono, -1.0, 1.0)
    raw = (mono * 32767.0).astype("<i2", copy=False).tobytes()
    source = AudioInputConfig(-1, "System audio", SYSTEM_AUDIO_SAMPLE_RATE, 1, len(mono))
    return normalize_input_pcm16(raw, source)


def build_session_update_event(
    target_language: str, noise_reduction_type: Optional[str] = None
) -> dict:
    """Create the documented translation-session configuration payload."""
    noise_reduction = (
        {"type": noise_reduction_type}
        if noise_reduction_type in {"near_field", "far_field"}
        else None
    )
    return {
        "type": "session.update",
        "session": {
            "audio": {
                "input": {
                    "transcription": {"model": "gpt-realtime-whisper"},
                    "noise_reduction": noise_reduction,
                },
                "output": {"language": target_language},
            }
        },
    }


def _websocket_error_text(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    response_body = getattr(exc, "resp_body", None) or getattr(exc, "response_body", None)
    parts = [str(exc) or exc.__class__.__name__]
    if status_code is not None:
        parts.append(f"HTTP {status_code}")
    if response_body:
        if isinstance(response_body, bytes):
            response_body = response_body.decode("utf-8", "replace")
        parts.append(str(response_body)[:600])
    return " | ".join(parts)


def probe_openai_realtime(api_key: str, target_language: str) -> None:
    """Fail early with a visible message when the Realtime socket cannot open.

    This deliberately runs before the setup form is replaced. It prevents an
    invalid key, missing API billing, or a blocked WebSocket from looking like
    a microphone crash. No API key is written to the debug log.
    """
    import websocket

    ws = websocket.WebSocket()
    try:
        logging.info("API preflight: connecting to %s", REALTIME_URL)
        ws.settimeout(API_PREFLIGHT_TIMEOUT_SECONDS)
        ws.connect(
            REALTIME_URL,
            header=[
                f"Authorization: Bearer {api_key}",
                f"OpenAI-Safety-Identifier: {stable_safety_id()}",
            ],
            timeout=API_PREFLIGHT_TIMEOUT_SECONDS,
        )
        logging.info("API preflight: WebSocket handshake completed")
        ws.send(json.dumps(build_session_update_event(target_language)))

        deadline = time.time() + API_PREFLIGHT_EVENT_WINDOW_SECONDS
        session_updated = False
        ws.settimeout(0.7)
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                break
            event = json.loads(raw)
            event_type = str(event.get("type", "unknown"))
            logging.info("API preflight event: %s", event_type)
            if event_type == "error":
                detail = event.get("error", {})
                if isinstance(detail, dict):
                    message = detail.get("message", str(detail))
                else:
                    message = str(detail)
                raise RuntimeError(f"OpenAI Realtime error: {message}")
            if event_type == "session.updated":
                session_updated = True
                break

        if not session_updated:
            raise TimeoutError("OpenAI did not confirm session.update during API preflight")

        try:
            ws.send(json.dumps({"type": "session.close"}))
        except Exception:
            pass
        logging.info("API preflight: passed")
    except Exception as exc:
        logging.exception("API preflight failed")
        raise RuntimeError(
            "Не удалось подключиться к OpenAI Realtime API. Проверь API-ключ, "
            "наличие API-баланса и не блокирует ли сеть WebSocket.\n\n"
            f"Техническая причина: {_websocket_error_text(exc)}"
        ) from exc
    finally:
        try:
            ws.close()
        except Exception:
            pass


@dataclass
class Callbacks:
    on_status: Callable[[str, str], None]
    on_source_delta: Callable[[str], None]
    on_translation_delta: Callable[[str], None]
    on_error: Callable[[str], None]
    on_input_changed: Callable[[AudioInputConfig], None]
    on_stats: Callable[[str], None]


class RealtimeTranslationClient:
    def __init__(
        self,
        api_key: str,
        target_language: str,
        audio_input: AudioInputConfig,
        play_audio: bool,
        auto_switch_headset: bool,
        audio_source_mode: str,
        callbacks: Callbacks,
    ) -> None:
        self.api_key = api_key
        self.target_language = target_language
        self.audio_input = audio_input
        self.play_audio = play_audio
        self.auto_switch_headset = auto_switch_headset
        self.audio_source_mode = audio_source_mode if audio_source_mode in {"microphone", "system"} else "microphone"
        self.callbacks = callbacks

        self.running = threading.Event()
        self.running.set()
        self.paused = threading.Event()
        self.ws = None
        self.ws_lock = threading.Lock()
        # Keep the audio backlog intentionally short. Fresh audio is more useful
        # than stale audio in a live interview translation window.
        self.audio_q: queue.Queue[bytes] = queue.Queue(maxsize=4)
        self.output_q: queue.Queue[bytes] = queue.Queue(maxsize=40)
        self.switch_q: queue.Queue[AudioInputConfig] = queue.Queue(maxsize=1)
        self.last_default_input_index: Optional[int] = None
        self.last_device_fingerprint: Optional[tuple] = None
        self.threads: list[threading.Thread] = []

        self.stats_lock = threading.Lock()
        self.mic_frames = 0
        self.mic_peak = 0
        self.audio_chunks_sent = 0
        self.audio_bytes_sent = 0
        self.source_chars = 0
        self.translation_chars = 0
        self.output_audio_frames = 0
        self.last_stats_emit = 0.0
        self.seen_stream_types: set[str] = set()

    def _noise_reduction_for_config(self, config: AudioInputConfig) -> Optional[str]:
        # Desktop loopback already contains the clean rendered output. Microphone
        # noise reduction is only useful for physical microphone capture.
        if self.audio_source_mode == "system":
            return None
        return "near_field" if _config_is_headset_microphone(config) else "far_field"

    def _record_mic_frame(self, payload: bytes) -> None:
        peak = 0
        try:
            samples = _samples_from_pcm16(payload)
            if samples:
                peak = max(abs(sample) for sample in samples)
        except Exception:
            logging.exception("Could not calculate microphone level")
        with self.stats_lock:
            self.mic_frames += 1
            if peak > self.mic_peak:
                self.mic_peak = peak
        self._emit_stats()

    def _record_sent_audio(self, payload: bytes) -> None:
        with self.stats_lock:
            self.audio_chunks_sent += 1
            self.audio_bytes_sent += len(payload)
        self._emit_stats()

    def _record_stream_event(self, event_type: str, delta_length: int = 0) -> None:
        first_seen = False
        with self.stats_lock:
            if event_type == "session.input_transcript.delta":
                self.source_chars += delta_length
            elif event_type == "session.output_transcript.delta":
                self.translation_chars += delta_length
            elif event_type == "session.output_audio.delta":
                self.output_audio_frames += 1
            if event_type not in self.seen_stream_types:
                self.seen_stream_types.add(event_type)
                first_seen = True
        if first_seen:
            logging.info("First realtime stream event: %s", event_type)
        self._emit_stats()

    def _emit_stats(self, force: bool = False) -> None:
        now = time.time()
        with self.stats_lock:
            if not force and now - self.last_stats_emit < STATS_EMIT_INTERVAL_SECONDS:
                return
            self.last_stats_emit = now
            peak_percent = round(self.mic_peak * 100 / 32767) if self.mic_peak else 0
            self.mic_peak = 0
            text = (
                f"mic {self.mic_frames} frames · peak {peak_percent}% · "
                f"sent {self.audio_chunks_sent} chunks · "
                f"source {self.source_chars} chars · translation {self.translation_chars} chars"
            )
        logging.info("Stream stats | %s", text)
        self.callbacks.on_stats(text)

    def start(self) -> None:
        logging.info(
            "Client start | source=%s | input=%s | target=%s | auto_switch_headset=%s | frame_ms=%d",
            self.audio_source_mode, self.audio_input.description, self.target_language, self.auto_switch_headset, FRAME_MS,
        )
        capture_target = self._system_audio_capture_loop if self.audio_source_mode == "system" else self._capture_loop
        capture_name = "system-loopback" if self.audio_source_mode == "system" else "mic-capture"
        self.threads = [
            threading.Thread(target=capture_target, daemon=True, name=capture_name),
            threading.Thread(target=self._network_loop, daemon=True, name="realtime-network"),
        ]
        if self.play_audio:
            self.threads.append(threading.Thread(target=self._playback_loop, daemon=True, name="translation-playback"))
        if self.audio_source_mode == "microphone" and self.auto_switch_headset:
            self.threads.append(threading.Thread(target=self._headset_monitor_loop, daemon=True, name="headset-monitor"))
        for thread in self.threads:
            thread.start()
        self._emit_stats(force=True)

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.paused.set()
            self.callbacks.on_status("Paused", AMBER)
        else:
            self.paused.clear()
            self.callbacks.on_status("Active", GREEN)

    def close(self) -> None:
        logging.info("Client close requested")
        self.running.clear()
        self._send_json({"type": "session.close"}, ignore_errors=True)
        time.sleep(0.08)
        self._close_socket()

    def _enqueue_audio(self, payload: bytes) -> None:
        try:
            self.audio_q.put_nowait(payload)
            return
        except queue.Full:
            pass

        # Throw away the oldest frame instead of accumulating latency.
        try:
            self.audio_q.get_nowait()
        except queue.Empty:
            return
        try:
            self.audio_q.put_nowait(payload)
        except queue.Full:
            pass

    @staticmethod
    def _close_input_stream(stream) -> None:
        if stream is None:
            return
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass

    @staticmethod
    def _open_input_stream(pa, cfg: AudioInputConfig):
        import pyaudio

        return pa.open(
            format=pyaudio.paInt16,
            channels=cfg.channels,
            rate=cfg.sample_rate,
            input=True,
            input_device_index=cfg.device_index,
            frames_per_buffer=cfg.frames_per_buffer,
        )

    def _capture_loop(self) -> None:
        import pyaudio

        pa = pyaudio.PyAudio()
        cfg = self.audio_input
        silence = b"\x00" * (TARGET_FRAMES_PER_BUFFER * 2)
        stream = None

        try:
            while self.running.is_set():
                try:
                    stream = self._open_input_stream(pa, cfg)
                    self.audio_input = cfg
                    self.callbacks.on_input_changed(cfg)
                    self.callbacks.on_status(f"Active · {cfg.device_name}", GREEN)
                    logging.info("Microphone stream opened: %s", cfg.description)
                    with self.ws_lock:
                        has_socket = self.ws is not None
                    if has_socket:
                        noise_reduction = self._noise_reduction_for_config(cfg)
                        self._send_json(
                            build_session_update_event(self.target_language, noise_reduction),
                            ignore_errors=True,
                        )
                        logging.info("Updated realtime input profile after microphone open: %s", noise_reduction)
                    while self.running.is_set():
                        raw = stream.read(cfg.frames_per_buffer, exception_on_overflow=False)
                        payload = silence if self.paused.is_set() else normalize_input_pcm16(raw, cfg)
                        self._enqueue_audio(payload)
                        self._record_mic_frame(payload)

                        try:
                            headset_cfg = self.switch_q.get_nowait()
                        except queue.Empty:
                            headset_cfg = None
                        if headset_cfg is not None and headset_cfg.device_index != cfg.device_index:
                            logging.info("Auto-switching to headset microphone: %s", headset_cfg.description)
                            self.callbacks.on_status("Switching to headset microphone…", AMBER)
                            cfg = headset_cfg
                            break

                except Exception as exc:
                    logging.exception("Microphone capture interrupted")
                    self.callbacks.on_error(f"Microphone reconnecting: {exc}")
                    self.callbacks.on_status("Searching for a usable microphone…", AMBER)
                    time.sleep(0.45)
                    try:
                        devices = list_input_devices()
                        cfg, actual_device, _ = find_best_supported_input_config(
                            devices, preferred=None, prefer_headset=self.auto_switch_headset
                        )
                        logging.info("Recovered microphone with [%d] %s", actual_device.index, actual_device.display_name)
                    except Exception as fallback_exc:
                        logging.exception("Microphone recovery failed")
                        self.callbacks.on_error(f"No usable microphone yet: {fallback_exc}")
                        time.sleep(1.1)
                finally:
                    self._close_input_stream(stream)
                    stream = None
        finally:
            self._close_input_stream(stream)
            pa.terminate()

    def _system_audio_capture_loop(self) -> None:
        """Capture what Windows plays through speakers/headphones via WASAPI loopback."""
        import soundcard as sc

        silence = b"\x00" * (TARGET_FRAMES_PER_BUFFER * 2)
        last_speaker_id: object = None
        try:
            while self.running.is_set():
                try:
                    speaker, loopback, speaker_name = _find_default_loopback_microphone()
                    current_id = getattr(speaker, "id", speaker_name)
                    cfg = _system_audio_config(f"System audio loopback · {speaker_name}")
                    self.audio_input = cfg
                    self.callbacks.on_input_changed(cfg)
                    self.callbacks.on_status("Listening · system audio loopback", GREEN)
                    logging.info("System loopback opened: %s", cfg.description)
                    last_speaker_id = current_id
                    frames = cfg.frames_per_buffer
                    blocksize = max(frames * 2, 2048)
                    with loopback.recorder(samplerate=SYSTEM_AUDIO_SAMPLE_RATE, blocksize=blocksize) as recorder:
                        while self.running.is_set():
                            data = recorder.record(numframes=frames)
                            payload = silence if self.paused.is_set() else _float_audio_to_target_pcm16(data)
                            if not payload:
                                continue
                            self._enqueue_audio(payload)
                            self._record_mic_frame(payload)
                            # Follow the active Windows output. This matters when
                            # headphones are plugged in after the interview starts.
                            try:
                                active = sc.default_speaker()
                                active_id = getattr(active, "id", getattr(active, "name", None)) if active is not None else None
                            except Exception:
                                active_id = last_speaker_id
                            if active_id != last_speaker_id:
                                logging.info("Default Windows playback device changed; reopening loopback")
                                self.callbacks.on_status("Switching system audio to new headphones…", AMBER)
                                break
                except Exception as exc:
                    if not self.running.is_set():
                        return
                    logging.exception("System audio loopback interrupted")
                    self.callbacks.on_error(f"System audio reconnecting: {exc}")
                    self.callbacks.on_status("Searching for Windows system audio…", AMBER)
                    time.sleep(0.9)
        finally:
            logging.info("System audio capture stopped")

    def _queue_input_switch(self, config: AudioInputConfig) -> None:
        try:
            self.switch_q.put_nowait(config)
        except queue.Full:
            pass

    def _headset_monitor_loop(self) -> None:
        """Watch for headset hot-plug and Windows default-input changes off-thread."""
        while self.running.is_set():
            time.sleep(DEVICE_SCAN_INTERVAL_SECONDS)
            if not self.running.is_set():
                return

            current = self.audio_input
            try:
                devices = list_input_devices(verbose=False)
            except Exception:
                logging.exception("Could not enumerate devices during runtime monitor")
                continue

            fingerprint = tuple(
                (device.index, device.name, device.host_api, device.is_default)
                for device in devices
            )
            if fingerprint != self.last_device_fingerprint:
                self.last_device_fingerprint = fingerprint
                logging.info(
                    "Runtime audio inventory changed: %s",
                    " | ".join(device.display_name for device in devices),
                )

            default_device = next((device for device in devices if device.is_default), None)
            current_default_index = default_device.index if default_device is not None else None

            # Bluetooth and USB headsets normally include a recognizable marker.
            # Prefer them over the laptop array when they appear.
            if not _config_is_headset_microphone(current):
                headset_candidates = [
                    device for device in devices
                    if device.index != current.device_index
                    and _is_headset_microphone(device)
                    and _device_penalty(device) < 250
                ]
                for device in sorted(headset_candidates, key=lambda item: _device_score(item, True), reverse=True):
                    try:
                        self._queue_input_switch(find_supported_input_config(device))
                        logging.info("Runtime monitor found headset microphone: %s", device.display_name)
                        break
                    except Exception:
                        logging.warning("Runtime headset candidate failed: %s", device.display_name)
                else:
                    # Some wired Realtek jacks keep generic names. In that case
                    # Windows often changes its default input endpoint on plug-in.
                    if (
                        default_device is not None
                        and default_device.index != current.device_index
                        and self.last_default_input_index is not None
                        and default_device.index != self.last_default_input_index
                        and _device_penalty(default_device) < 250
                    ):
                        try:
                            self._queue_input_switch(find_supported_input_config(default_device))
                            logging.info("Runtime monitor followed changed Windows default input: %s", default_device.display_name)
                        except Exception:
                            logging.warning("Changed Windows default input could not open: %s", default_device.display_name)

            self.last_default_input_index = current_default_index

    def _connect(self):
        import websocket

        logging.info("Connecting to %s", REALTIME_URL)
        ws = websocket.WebSocket()
        ws.settimeout(1.0)
        ws.connect(
            REALTIME_URL,
            header=[
                f"Authorization: Bearer {self.api_key}",
                f"OpenAI-Safety-Identifier: {stable_safety_id()}",
            ],
            timeout=10,
        )
        with self.ws_lock:
            self.ws = ws

        noise_reduction = self._noise_reduction_for_config(self.audio_input)
        self._send_json(build_session_update_event(self.target_language, noise_reduction))
        logging.info(
            "Realtime socket handshake completed; waiting for session.updated | target=%s | noise=%s",
            self.target_language,
            noise_reduction,
        )

        deadline = time.time() + 4.0
        session_updated = False
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise ConnectionError("OpenAI closed the socket during setup")
            event = json.loads(raw)
            event_type = str(event.get("type", "unknown"))
            logging.info("Realtime handshake event: %s", event_type)
            if event_type == "error":
                detail = event.get("error", {})
                message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
                raise RuntimeError(f"OpenAI error during realtime setup: {message}")
            if event_type == "session.updated":
                session_updated = True
                break

        if not session_updated:
            raise TimeoutError("OpenAI did not confirm session.update within 4 seconds")

        ws.settimeout(1.0)
        logging.info("Realtime socket connected and configured")
        self.callbacks.on_status("Listening · microphone ready", GREEN)
        return ws

    def _network_loop(self) -> None:
        while self.running.is_set():
            try:
                self.callbacks.on_status("Connecting to OpenAI…", AMBER)
                ws = self._connect()
                receiver = threading.Thread(target=self._receive_loop, args=(ws,), daemon=True, name="realtime-receiver")
                receiver.start()

                while self.running.is_set() and receiver.is_alive():
                    try:
                        audio = self.audio_q.get(timeout=0.35)
                    except queue.Empty:
                        continue
                    if not self.running.is_set():
                        break
                    self._send_json(
                        {
                            "type": "session.input_audio_buffer.append",
                            "audio": base64.b64encode(audio).decode("ascii"),
                        }
                    )
                    self._record_sent_audio(audio)
                if self.running.is_set():
                    raise ConnectionError("Realtime socket disconnected")
            except Exception as exc:
                if self.running.is_set():
                    logging.exception("Connection loop issue")
                    self.callbacks.on_status("Reconnecting…", AMBER)
                    self.callbacks.on_error(f"Connection issue: {exc}")
                    time.sleep(RECONNECT_DELAY_SECONDS)
                else:
                    logging.info("Network loop stopped cleanly during shutdown")
            finally:
                self._close_socket()

    def _receive_loop(self, ws) -> None:
        import websocket

        while self.running.is_set():
            try:
                raw = ws.recv()
                if not raw:
                    raise ConnectionError("OpenAI closed the socket")
                event = json.loads(raw)
                event_type = str(event.get("type", ""))
                if event_type in {"session.created", "session.updated", "session.closed", "error"}:
                    logging.info("Realtime event: %s", event_type)

                if event_type == "session.input_transcript.delta":
                    delta = str(event.get("delta", ""))
                    self._record_stream_event(event_type, len(delta))
                    self.callbacks.on_source_delta(delta)
                    self.callbacks.on_status("Listening · original transcript may appear with delay", GREEN)
                elif event_type == "session.output_transcript.delta":
                    delta = str(event.get("delta", ""))
                    self._record_stream_event(event_type, len(delta))
                    self.callbacks.on_translation_delta(delta)
                    self.callbacks.on_status("Translating live", GREEN)
                elif event_type == "session.output_audio.delta":
                    encoded = str(event.get("delta", ""))
                    self._record_stream_event(event_type, len(encoded))
                    if self.play_audio:
                        try:
                            self.output_q.put_nowait(base64.b64decode(encoded))
                        except queue.Full:
                            try:
                                self.output_q.get_nowait()
                                self.output_q.put_nowait(base64.b64decode(encoded))
                            except queue.Empty:
                                pass
                elif event_type == "session.closed":
                    logging.info("Realtime session closed by server")
                    return
                elif event_type == "error":
                    detail = event.get("error", {})
                    message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
                    logging.error("OpenAI event error: %s", message)
                    self.callbacks.on_error(f"OpenAI error: {message}")
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                logging.exception("Receiver loop stopped")
                return

    def _playback_loop(self) -> None:
        import pyaudio

        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=TARGET_CHANNELS,
                rate=TARGET_SAMPLE_RATE,
                output=True,
                frames_per_buffer=TARGET_FRAMES_PER_BUFFER,
            )
            while self.running.is_set():
                try:
                    pcm = self.output_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                stream.write(pcm)
        except Exception as exc:
            logging.exception("Audio playback disabled")
            self.callbacks.on_error(f"Audio playback disabled: {exc}")
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            pa.terminate()

    def _send_json(self, event: dict, ignore_errors: bool = False) -> None:
        payload = json.dumps(event)
        with self.ws_lock:
            ws = self.ws
        if ws is None:
            if ignore_errors:
                return
            raise ConnectionError("Realtime socket is not ready")
        try:
            ws.send(payload)
        except Exception:
            if ignore_errors:
                return
            raise

    def _close_socket(self) -> None:
        with self.ws_lock:
            ws, self.ws = self.ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


class SetupWindow:
    def __init__(self, root: tk.Tk, on_start: Callable[..., None]) -> None:
        self.root = root
        self.on_start = on_start
        self.cfg = load_config()
        self.devices: list[DeviceInfo] = []
        self.root.title("Timur Translator · Realtime setup")
        self.root.geometry("620x860")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        try:
            self.root.attributes("-alpha", 1.0)
            self.root.attributes("-topmost", False)
            if sys.platform == "win32":
                self.root.attributes("-transparentcolor", "")
        except tk.TclError:
            logging.warning("Could not reset setup-window attributes")
        self._build()

    def _build(self) -> None:
        tk.Frame(self.root, bg=ACCENT, height=3).pack(fill="x")
        tk.Label(self.root, text="Timur Translator", font=(FONT, 22, "bold"), bg=BG, fg=TEXT).pack(pady=(30, 3))
        tk.Label(self.root, text="OpenAI Realtime", font=(FONT, 12), bg=BG, fg=TEXT2).pack(pady=(0, 18))
        form = tk.Frame(self.root, bg=BG, padx=42)
        form.pack(fill="both", expand=True)

        tk.Label(form, text="OPENAI API KEY", font=(FONT, 10, "bold"), bg=BG, fg=TEXT2, anchor="w").pack(fill="x", pady=(8, 4))
        self.key = tk.Entry(form, font=(FONT, 12), bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", bd=10, show="•")
        self.key.insert(0, os.getenv("OPENAI_API_KEY", self.cfg.get("openai_key", "")))
        self.key.pack(fill="x", ipady=4)

        self.remember = tk.BooleanVar(value=bool(self.cfg.get("remember_key", False)))
        tk.Checkbutton(
            form,
            text="Remember key on this computer (stored locally)",
            variable=self.remember,
            font=(FONT, 10),
            bg=BG,
            fg=TEXT2,
            activebackground=BG,
            activeforeground=TEXT,
            selectcolor=SURFACE2,
        ).pack(anchor="w", pady=(7, 8))

        tk.Label(form, text="TARGET LANGUAGE", font=(FONT, 10, "bold"), bg=BG, fg=TEXT2, anchor="w").pack(fill="x", pady=(8, 4))
        self.lang = tk.StringVar(value=self.cfg.get("language_label", "Русский"))
        ttk.Combobox(form, textvariable=self.lang, values=list(LANGUAGES), state="readonly", font=(FONT, 12)).pack(fill="x", ipady=5)

        tk.Label(form, text="AUDIO SOURCE", font=(FONT, 10, "bold"), bg=BG, fg=TEXT2, anchor="w").pack(fill="x", pady=(14, 4))
        default_source_label = self.cfg.get("audio_source_label", next(iter(AUDIO_SOURCE_OPTIONS)))
        if default_source_label not in AUDIO_SOURCE_OPTIONS:
            default_source_label = next(iter(AUDIO_SOURCE_OPTIONS))
        self.audio_source = tk.StringVar(value=default_source_label)
        ttk.Combobox(form, textvariable=self.audio_source, values=list(AUDIO_SOURCE_OPTIONS), state="readonly", font=(FONT, 11)).pack(fill="x", ipady=5)
        tk.Label(
            form,
            text="For YouTube or an online interview choose System audio. It captures what you hear in speakers or headphones. Choose Microphone only when you want to translate your own voice.",
            font=(FONT, 9), bg=BG, fg=TEXT3, justify="left", wraplength=520,
        ).pack(fill="x", pady=(6, 2))

        top = tk.Frame(form, bg=BG)
        top.pack(fill="x", pady=(14, 4))
        tk.Label(top, text="MICROPHONE (USED ONLY IN MICROPHONE MODE)", font=(FONT, 10, "bold"), bg=BG, fg=TEXT2, anchor="w").pack(side="left")
        tk.Button(top, text="REFRESH", font=(FONT, 8, "bold"), bg=SURFACE2, fg=TEXT2, relief="flat", command=self._refresh_devices).pack(side="right")

        self.device = tk.StringVar()
        self.device_box = ttk.Combobox(form, textvariable=self.device, state="readonly", font=(FONT, 11))
        self.device_box.pack(fill="x", ipady=5)

        # Create the status label before enumerating microphones. Device enumeration
        # can update the status immediately, including during the first window build.
        self.status = tk.Label(form, text="", font=(FONT, 10), bg=BG, fg=RED, wraplength=480, justify="left")
        self._refresh_devices()

        tk.Label(
            form,
            text="Leave AUTO selected. The app tests Windows driver duplicates, picks a headset microphone first when one is connected, and falls back to the laptop microphone when needed.",
            font=(FONT, 9), bg=BG, fg=TEXT3, justify="left", wraplength=520,
        ).pack(fill="x", pady=(7, 2))

        self.auto_switch_headset = tk.BooleanVar(value=bool(self.cfg.get("auto_switch_headset", True)))
        tk.Checkbutton(
            form,
            text="AUTO: switch to headset microphone when headphones are connected",
            variable=self.auto_switch_headset,
            font=(FONT, 10), bg=BG, fg=TEXT2, activebackground=BG,
            activeforeground=TEXT, selectcolor=SURFACE2,
        ).pack(anchor="w", pady=(14, 2))

        self.play_audio = tk.BooleanVar(value=bool(self.cfg.get("play_audio", False)))
        tk.Checkbutton(
            form,
            text="Play translated voice through speakers (can create feedback)",
            variable=self.play_audio,
            font=(FONT, 10), bg=BG, fg=TEXT2, activebackground=BG,
            activeforeground=TEXT, selectcolor=SURFACE2,
        ).pack(anchor="w", pady=(18, 8))

        tk.Button(
            form,
            text="START LIVE TRANSLATION",
            font=(FONT, 12, "bold"),
            bg=ACCENT,
            fg="white",
            relief="flat",
            pady=14,
            command=self._start,
        ).pack(fill="x", pady=(16, 0))
        self.status.pack(pady=9)
        tk.Label(form, text=f"Debug log: {LOG_PATH}", font=(FONT, 8), bg=BG, fg=TEXT3, wraplength=480).pack(pady=(6, 0))

    def _refresh_devices(self) -> None:
        try:
            self.devices = list_input_devices()
        except Exception as exc:
            logging.exception("Could not enumerate input devices")
            self.devices = []
            self.status.config(text=f"Could not read microphones: {exc}")
        names = ["[AUTO] Headset microphone first, then Windows default"] + [device.display_name for device in self.devices]
        self.device_box.configure(values=names)
        if self.devices:
            position = 0
            if self.cfg.get("device_mode") == "manual":
                position = choose_default_position(self.devices, self.cfg.get("device_index"))
            self.device_box.current(position)
            self.status.config(text="")
        else:
            self.device.set("")
            self.status.config(text="No microphone inputs found")

    def _selected_device(self) -> Optional[DeviceInfo]:
        selection = self.device.get().strip()
        if not selection:
            raise RuntimeError("Select a microphone")
        if selection.startswith("[AUTO]"):
            return None
        index = int(selection.split("]", 1)[0].replace("[", ""))
        for device in self.devices:
            if device.index == index:
                return device
        raise RuntimeError("Selected microphone disappeared. Press REFRESH and select it again.")

    def _start(self) -> None:
        key = self.key.get().strip()
        if not key:
            self.status.config(text="Enter your OpenAI API key")
            return

        source_mode = AUDIO_SOURCE_OPTIONS.get(self.audio_source.get(), "system")
        auto_mode = True
        actual_device: Optional[DeviceInfo] = None
        try:
            if source_mode == "system":
                self.status.config(text="Checking Windows system audio loopback…", fg=AMBER)
                self.root.update_idletasks()
                audio_input = find_system_audio_input_config()
                self.status.config(text=f"Using: {audio_input.device_name}", fg=GREEN)
                if self.play_audio.get():
                    self.play_audio.set(False)
                    logging.info("Disabled translated voice playback in system-audio mode to avoid loopback feedback")
            else:
                selected = self._selected_device()
                auto_mode = selected is None
                prefer_headset = auto_mode and self.auto_switch_headset.get()
                self.status.config(text="Checking Windows microphone inputs…", fg=AMBER)
                self.root.update_idletasks()
                audio_input, actual_device, used_fallback = find_best_supported_input_config(
                    self.devices, selected, prefer_headset=prefer_headset
                )
                if used_fallback:
                    self.status.config(
                        text=f"Selected driver duplicate could not open. Using: {actual_device.display_name}",
                        fg=GREEN,
                    )
                else:
                    self.status.config(text=f"Using: {actual_device.display_name}", fg=GREEN)
            self.root.update_idletasks()
        except Exception as exc:
            logging.exception("Audio source preflight failed")
            self.status.config(text=str(exc), fg=RED)
            messagebox.showerror("Audio source could not start", f"{exc}\n\nDebug log:\n{LOG_PATH}")
            return

        try:
            self.status.config(text="Checking OpenAI Realtime API…", fg=AMBER)
            self.root.update_idletasks()
            probe_openai_realtime(key, LANGUAGES[self.lang.get()])
            self.status.config(text=f"Ready · using: {audio_input.device_name}", fg=GREEN)
            self.root.update_idletasks()
        except Exception as exc:
            logging.exception("OpenAI preflight rejected start")
            self.status.config(text=str(exc), fg=RED)
            messagebox.showerror("OpenAI connection could not start", f"{exc}\n\nDebug log:\n{LOG_PATH}")
            return

        config = dict(self.cfg)
        config.update({
            "remember_key": self.remember.get(),
            "language_label": self.lang.get(),
            "audio_source_label": self.audio_source.get(),
            "device_index": actual_device.index if actual_device is not None else self.cfg.get("device_index"),
            "device_mode": "auto" if auto_mode else "manual",
            "auto_switch_headset": self.auto_switch_headset.get(),
            "play_audio": self.play_audio.get(),
        })
        if self.remember.get():
            config["openai_key"] = key
        else:
            config.pop("openai_key", None)
        try:
            save_config(config)
        except Exception:
            logging.exception("Could not save config")

        self.on_start(
            key,
            LANGUAGES[self.lang.get()],
            audio_input,
            self.play_audio.get(),
            source_mode == "microphone" and auto_mode and self.auto_switch_headset.get(),
            source_mode,
        )


class AppearanceWindow:
    """Small live UI studio for the subtitle overlay."""

    def __init__(self, parent: tk.Tk, current: dict, on_apply: Callable[[dict, bool], None]) -> None:
        self.parent = parent
        self.on_apply = on_apply
        self.current = dict(current)
        self.top = tk.Toplevel(parent)
        self.top.title("Timur Translator · Appearance")
        self.top.geometry("540x720")
        self.top.minsize(500, 650)
        self.top.configure(bg=BG)
        self.top.transient(parent)
        self.top.protocol("WM_DELETE_WINDOW", self.top.destroy)
        self._build()
        self.top.lift()
        self.top.focus_force()

    def _build(self) -> None:
        tk.Frame(self.top, bg=ACCENT, height=3).pack(fill="x")
        outer = tk.Frame(self.top, bg=BG, padx=24, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="APPEARANCE STUDIO", font=(FONT, 16, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(
            outer, text="Tune the translator into a desktop overlay. Changes can be previewed live.",
            font=(FONT, 10), bg=BG, fg=TEXT2, justify="left", wraplength=470,
        ).pack(anchor="w", pady=(3, 15))

        self.theme = tk.StringVar(value=str(self.current.get("theme", "Midnight Violet")))
        self.opacity = tk.DoubleVar(value=float(self.current.get("opacity", 0.96)) * 100)
        self.original_font = tk.IntVar(value=int(self.current.get("original_font_size", 14)))
        self.translation_font = tk.IntVar(value=int(self.current.get("translation_font_size", 18)))
        self.padding = tk.IntVar(value=int(self.current.get("text_padding", 16)))
        self.always_top = tk.BooleanVar(value=bool(self.current.get("always_on_top", True)))
        self.show_original = tk.BooleanVar(value=bool(self.current.get("show_original", True)))
        self.show_diagnostics = tk.BooleanVar(value=bool(self.current.get("show_diagnostics", False)))
        self.compact = tk.BooleanVar(value=bool(self.current.get("compact_overlay", False)))
        self.transparent_canvas = tk.BooleanVar(value=bool(self.current.get("transparent_canvas", False)))
        self.background = tk.StringVar(value=str(self.current.get("background", BG)))
        self.accent = tk.StringVar(value=str(self.current.get("accent", ACCENT)))

        self._section(outer, "PRESET")
        combo = ttk.Combobox(outer, textvariable=self.theme, values=list(THEME_PRESETS), state="readonly", font=(FONT, 11))
        combo.pack(fill="x", ipady=4)
        combo.bind("<<ComboboxSelected>>", self._preset_selected)

        self._section(outer, "WINDOW OPACITY")
        self.opacity_value = tk.Label(outer, text="", font=(FONT, 10, "bold"), bg=BG, fg=TEXT2)
        self.opacity_value.pack(anchor="e")
        tk.Scale(
            outer, from_=45, to=100, orient="horizontal", variable=self.opacity, resolution=1,
            showvalue=False, bg=BG, fg=TEXT2, troughcolor=SURFACE2, highlightthickness=0,
            activebackground=ACCENT, command=lambda _value: self._update_labels(),
        ).pack(fill="x")

        self._section(outer, "SUBTITLE TYPOGRAPHY")
        grid = tk.Frame(outer, bg=BG)
        grid.pack(fill="x")
        self._scale_row(grid, 0, "Translation size", self.translation_font, 12, 38)
        self._scale_row(grid, 1, "Original size", self.original_font, 10, 28)
        self._scale_row(grid, 2, "Text padding", self.padding, 6, 36)

        self._section(outer, "COLORS")
        color_grid = tk.Frame(outer, bg=BG)
        color_grid.pack(fill="x")
        self._color_row(color_grid, 0, "Background", self.background)
        self._color_row(color_grid, 1, "Accent", self.accent)

        self._section(outer, "OVERLAY BEHAVIOR")
        self._check(outer, "Always keep translator above other windows", self.always_top)
        self._check(outer, "Compact overlay: translation only", self.compact)
        self._check(outer, "Transparent subtitle canvas, keep text opaque", self.transparent_canvas)
        self._check(outer, "Show original microphone transcript", self.show_original)
        self._check(outer, "Diagnostic mode: show technical STREAM counters", self.show_diagnostics)

        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill="x", side="bottom", pady=(18, 0))
        self._button(actions, "RESET", self._reset, bg=SURFACE2, fg=TEXT2).pack(side="left")
        self._button(actions, "PREVIEW", lambda: self._submit(False), bg=SURFACE2, fg=TEXT).pack(side="right", padx=(8, 0))
        self._button(actions, "SAVE & APPLY", lambda: self._submit(True), bg=ACCENT, fg="white").pack(side="right")
        self._update_labels()

    def _section(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, font=(FONT, 9, "bold"), bg=BG, fg=TEXT3, anchor="w").pack(fill="x", pady=(13, 5))

    def _scale_row(self, parent: tk.Frame, row: int, label: str, variable: tk.IntVar, start: int, end: int) -> None:
        tk.Label(parent, text=label, font=(FONT, 10), bg=BG, fg=TEXT2, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
        tk.Scale(
            parent, from_=start, to=end, orient="horizontal", variable=variable, resolution=1,
            showvalue=True, length=250, bg=BG, fg=TEXT2, troughcolor=SURFACE2,
            highlightthickness=0, activebackground=ACCENT,
        ).grid(row=row, column=1, sticky="ew")
        parent.grid_columnconfigure(1, weight=1)

    def _color_row(self, parent: tk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        tk.Label(parent, text=label, font=(FONT, 10), bg=BG, fg=TEXT2, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
        tk.Entry(parent, textvariable=variable, font=(FONT, 10), bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat").grid(row=row, column=1, sticky="ew", padx=8)
        self._button(parent, "PICK", lambda: self._pick_color(variable), bg=SURFACE2, fg=TEXT2).grid(row=row, column=2)
        parent.grid_columnconfigure(1, weight=1)

    def _check(self, parent: tk.Widget, text: str, variable: tk.BooleanVar) -> None:
        tk.Checkbutton(
            parent, text=text, variable=variable, font=(FONT, 10), bg=BG, fg=TEXT2,
            activebackground=BG, activeforeground=TEXT, selectcolor=SURFACE2,
        ).pack(anchor="w", pady=2)

    @staticmethod
    def _button(parent: tk.Widget, text: str, command: Callable[[], None], bg: str, fg: str) -> tk.Button:
        button = tk.Button(parent, text=text, font=(FONT, 9, "bold"), bg=bg, fg=fg, relief="flat", padx=12, pady=7, command=command)
        return button

    def _update_labels(self) -> None:
        self.opacity_value.config(text=f"{int(round(self.opacity.get()))}%")

    def _preset_selected(self, _event: object = None) -> None:
        preset = THEME_PRESETS.get(self.theme.get())
        if preset and self.theme.get() != "Custom":
            self.background.set(preset["background"])
            self.accent.set(preset["accent"])

    def _pick_color(self, variable: tk.StringVar) -> None:
        _rgb, chosen = colorchooser.askcolor(color=variable.get(), parent=self.top)
        if chosen:
            variable.set(chosen)
            self.theme.set("Custom")

    def _payload(self) -> dict:
        payload = dict(self.current)
        payload.update({
            "theme": self.theme.get(),
            "background": _safe_hex(self.background.get(), BG),
            "accent": _safe_hex(self.accent.get(), ACCENT),
            "opacity": round(self.opacity.get() / 100.0, 2),
            "always_on_top": self.always_top.get(),
            "show_original": self.show_original.get(),
            "show_diagnostics": self.show_diagnostics.get(),
            "compact_overlay": self.compact.get(),
            "transparent_canvas": self.transparent_canvas.get(),
            "original_font_size": self.original_font.get(),
            "translation_font_size": self.translation_font.get(),
            "text_padding": self.padding.get(),
        })
        return load_appearance({"appearance": payload})

    def _submit(self, persist: bool) -> None:
        payload = self._payload()
        self.current = dict(payload)
        self.on_apply(payload, persist)
        if persist:
            self.top.destroy()

    def _reset(self) -> None:
        defaults = dict(APPEARANCE_DEFAULTS)
        self.current = defaults
        self.theme.set(defaults["theme"])
        self.background.set(defaults["background"])
        self.accent.set(defaults["accent"])
        self.opacity.set(defaults["opacity"] * 100)
        self.original_font.set(defaults["original_font_size"])
        self.translation_font.set(defaults["translation_font_size"])
        self.padding.set(defaults["text_padding"])
        self.always_top.set(defaults["always_on_top"])
        self.show_original.set(defaults["show_original"])
        self.show_diagnostics.set(defaults["show_diagnostics"])
        self.compact.set(defaults["compact_overlay"])
        self.transparent_canvas.set(defaults["transparent_canvas"])
        self._update_labels()
        self.on_apply(load_appearance({"appearance": defaults}), False)


class TranslatorWindow:
    def __init__(
        self, root: tk.Tk, api_key: str, language_code: str, audio_input: AudioInputConfig,
        play_audio: bool, auto_switch_headset: bool, audio_source_mode: str
    ) -> None:
        self.root = root
        self.client: Optional[RealtimeTranslationClient] = None
        self.closed = False
        self.paused = False
        self.source_buffer = ""
        self.translation_buffer = ""
        self.last_source_delta_at = 0.0
        self.last_translation_delta_at = 0.0
        self.source_break_pending = False
        self.translation_break_pending = False
        self.ui_q: queue.Queue[tuple] = queue.Queue(maxsize=500)
        self.appearance = load_appearance()
        self.palette = build_palette(self.appearance)
        self.appearance_dialog: Optional[AppearanceWindow] = None

        self.root.title("Timur Translator · OpenAI Realtime")
        geometry_key = "overlay_geometry" if self.appearance["compact_overlay"] else "full_geometry"
        self.root.geometry(str(self.appearance[geometry_key]))
        self.root.minsize(620, 210)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._build(audio_input, audio_source_mode)
        self._apply_appearance()

        callbacks = Callbacks(
            on_status=lambda text, color: self._enqueue_ui("status", text, color),
            on_source_delta=lambda delta: self._enqueue_ui("source", delta),
            on_translation_delta=lambda delta: self._enqueue_ui("translation", delta),
            on_error=lambda text: self._enqueue_ui("error", text),
            on_input_changed=lambda config: self._enqueue_ui("input", config),
            on_stats=lambda text: self._enqueue_ui("stats", text),
        )
        self.client = RealtimeTranslationClient(
            api_key, language_code, audio_input, play_audio, auto_switch_headset, audio_source_mode, callbacks
        )
        self.client.start()
        self.root.after(UI_POLL_MS, self._poll_ui)
        self.root.after(350, self._segment_tick)

    def _build(self, audio_input: AudioInputConfig, audio_source_mode: str) -> None:
        p = self.palette
        self.accent_bar = tk.Frame(self.root, bg=p.accent, height=3)
        self.accent_bar.pack(fill="x")
        self.header = tk.Frame(self.root, bg=p.surface, padx=18, pady=10)
        self.header.pack(fill="x")
        self.brand_label = tk.Label(self.header, text="Timur Translator", font=(FONT, 14, "bold"), bg=p.surface, fg=p.text)
        self.brand_label.pack(side="left")
        self.status_label = tk.Label(self.header, text="Starting…", font=(FONT, 10), bg=p.surface, fg=p.amber)
        self.status_label.pack(side="left", padx=14)
        self.setup_button = self._button(self.header, "SETUP", self._settings)
        self.setup_button.pack(side="right")
        self.style_button = self._button(self.header, "STYLE", self._open_appearance)
        self.style_button.pack(side="right", padx=8)
        self.overlay_button = self._button(self.header, "OVERLAY", self._toggle_overlay)
        self.overlay_button.pack(side="right")
        self.pause_button = self._button(self.header, "PAUSE", self._toggle_pause, prominent=True)
        self.pause_button.pack(side="right", padx=8)

        self.input_label = tk.Label(
            self.root, text=f"INPUT: {audio_input.description} → 24000 Hz mono PCM16",
            font=(FONT, 9), bg=p.surface2, fg=p.text3, anchor="w", padx=18, pady=4
        )
        self.input_label.pack(fill="x")

        self.helper_label = tk.Label(
            self.root,
            text=(
                "Listening to Windows system audio. Play a YouTube video or keep the interview call audible in your headphones."
                if audio_source_mode == "system"
                else "Listening to your microphone. The original transcript can appear a little later than the translation."
            ),
            font=(FONT, 9), bg=p.surface, fg=p.text2, anchor="w", padx=18, pady=5
        )
        self.helper_label.pack(fill="x")

        self.diagnostics = tk.Frame(self.root, bg=p.surface, padx=18, pady=5)
        self.diagnostics.pack(fill="x")
        self.stream_title = tk.Label(self.diagnostics, text="STREAM:", font=(FONT, 9, "bold"), bg=p.surface, fg=p.text3)
        self.stream_title.pack(side="left")
        self.stats_label = tk.Label(self.diagnostics, text="mic waiting · API waiting", font=(FONT, 9), bg=p.surface, fg=p.text2, anchor="w")
        self.stats_label.pack(side="left", padx=(8, 0), fill="x", expand=True)

        self.heads = tk.Frame(self.root, bg=p.surface2, pady=7)
        self.heads.pack(fill="x")
        self.heads.grid_columnconfigure(0, weight=1, uniform="subtitle_columns")
        self.heads.grid_columnconfigure(1, weight=1, uniform="subtitle_columns")
        self.left_head = tk.Label(self.heads, text="ORIGINAL MICROPHONE SPEECH", font=(FONT, 10, "bold"), bg=p.surface2, fg=p.text3)
        self.left_head.grid(row=0, column=0, sticky="ew")
        self.right_head = tk.Label(self.heads, text="LIVE TRANSLATION", font=(FONT, 10, "bold"), bg=p.surface2, fg=p.text3)
        self.right_head.grid(row=0, column=1, sticky="ew")

        self.footer = tk.Frame(self.root, bg=p.surface, padx=18, pady=7)
        self.footer.pack(side="bottom", fill="x")
        self.count_label = tk.Label(self.footer, text="0 segments", font=(FONT, 10), bg=p.surface, fg=p.text3)
        self.count_label.pack(side="left")
        self.clear_button = self._button(self.footer, "CLEAR", self._clear)
        self.clear_button.pack(side="right")
        self.copy_button = self._button(self.footer, "COPY TRANSLATION", self._copy_translation)
        self.copy_button.pack(side="right", padx=8)
        self.error_label = tk.Label(self.footer, text="", font=(FONT, 9), bg=p.surface, fg=p.red)
        self.error_label.pack(side="right", padx=14)

        self.body = tk.Frame(self.root, bg=p.bg)
        self.body.pack(fill="both", expand=True)
        self.body.grid_rowconfigure(0, weight=1)
        self.left_text = tk.Text(self.body, width=1, bg=p.bg, fg=p.text2, insertbackground=p.text, relief="flat", wrap="word", state="disabled")
        self.separator = tk.Frame(self.body, bg=p.border, width=1)
        self.right_text = tk.Text(self.body, width=1, bg=p.bg, fg=p.text, insertbackground=p.text, relief="flat", wrap="word", state="disabled")
        self._layout_subtitles()

    def _button(self, parent: tk.Widget, text: str, command: Callable[[], None], prominent: bool = False) -> tk.Button:
        p = self.palette
        bg = p.accent if prominent else p.surface2
        fg = "white" if prominent else p.text2
        button = tk.Button(parent, text=text, font=(FONT, 9, "bold"), bg=bg, fg=fg, relief="flat", padx=11, pady=5, command=command, cursor="hand2")
        self._restyle_button(button, bg, fg)
        button.bind("<Enter>", lambda _event: button.config(bg=getattr(button, "_timur_hover_bg", bg)))
        button.bind("<Leave>", lambda _event: button.config(bg=getattr(button, "_timur_normal_bg", bg)))
        return button

    @staticmethod
    def _restyle_button(button: tk.Button, bg: str, fg: str) -> None:
        button._timur_normal_bg = bg  # type: ignore[attr-defined]
        button._timur_hover_bg = _blend_hex(bg, "#ffffff" if not _is_light(bg) else "#000000", 0.12)  # type: ignore[attr-defined]
        button.config(bg=bg, fg=fg, activebackground=button._timur_hover_bg, activeforeground=fg)  # type: ignore[attr-defined]

    def _layout_subtitles(self) -> None:
        compact = bool(self.appearance.get("compact_overlay"))
        show_original = bool(self.appearance.get("show_original")) and not compact
        for column in (0, 1, 2):
            self.body.grid_columnconfigure(column, weight=0, uniform="")
        self.left_text.grid_forget()
        self.separator.grid_forget()
        self.right_text.grid_forget()
        if show_original:
            self.body.grid_columnconfigure(0, weight=1, uniform="subtitle_columns")
            self.body.grid_columnconfigure(2, weight=1, uniform="subtitle_columns")
            self.left_text.grid(row=0, column=0, sticky="nsew")
            self.separator.grid(row=0, column=1, sticky="ns")
            self.right_text.grid(row=0, column=2, sticky="nsew")
            self.left_head.grid(row=0, column=0, sticky="ew")
            self.right_head.grid(row=0, column=1, sticky="ew")
        else:
            self.body.grid_columnconfigure(0, weight=1)
            self.right_text.grid(row=0, column=0, columnspan=3, sticky="nsew")
            self.left_head.grid_forget()
            self.right_head.grid(row=0, column=0, columnspan=2, sticky="ew")

    def _apply_appearance(self) -> None:
        self.palette = build_palette(self.appearance)
        p = self.palette
        transparent_key = "#010203"
        transparent_canvas = bool(self.appearance.get("transparent_canvas", False))
        canvas_bg = transparent_key if transparent_canvas else p.bg
        try:
            self.root.attributes("-alpha", float(self.appearance["opacity"]))
            self.root.attributes("-topmost", bool(self.appearance["always_on_top"]))
            if sys.platform == "win32":
                self.root.attributes("-transparentcolor", transparent_key if transparent_canvas else "")
        except tk.TclError:
            logging.warning("Could not apply one or more Windows overlay attributes")
        self.root.configure(bg=p.bg)
        self.accent_bar.config(bg=p.accent)
        self.header.config(bg=p.surface)
        self.brand_label.config(bg=p.surface, fg=p.text)
        self.status_label.config(bg=p.surface)
        self.input_label.config(bg=p.surface2, fg=p.text3)
        self.helper_label.config(bg=p.surface, fg=p.text2)
        self.diagnostics.config(bg=p.surface)
        self.stream_title.config(bg=p.surface, fg=p.text3)
        self.stats_label.config(bg=p.surface, fg=p.text2)
        self.heads.config(bg=p.surface2)
        self.left_head.config(bg=p.surface2, fg=p.text3)
        self.right_head.config(bg=p.surface2, fg=p.text3)
        self.footer.config(bg=p.surface)
        self.count_label.config(bg=p.surface, fg=p.text3)
        self.error_label.config(bg=p.surface, fg=p.red)
        self.body.config(bg=canvas_bg)
        padding = int(self.appearance["text_padding"])
        self.left_text.config(bg=canvas_bg, fg=p.text2, insertbackground=p.text, font=(FONT, int(self.appearance["original_font_size"])), padx=padding, pady=padding)
        self.right_text.config(bg=canvas_bg, fg=p.text, insertbackground=p.text, font=(FONT, int(self.appearance["translation_font_size"]), "bold"), padx=padding, pady=padding)
        self.separator.config(bg=p.border)
        for button in (self.setup_button, self.style_button, self.overlay_button, self.clear_button, self.copy_button):
            self._restyle_button(button, p.surface2, p.text2)
        self._restyle_button(self.pause_button, p.accent, "white")
        compact = bool(self.appearance["compact_overlay"])
        self.overlay_button.config(text="FULL VIEW" if compact else "OVERLAY")
        self._set_packed(self.input_label, not compact, fill="x", before=self.body)
        self._set_packed(self.helper_label, not compact, fill="x", before=self.body)
        self._set_packed(self.diagnostics, bool(self.appearance["show_diagnostics"]) and not compact, fill="x", before=self.body)
        self._set_packed(self.heads, not compact, fill="x", before=self.body)
        self._set_packed(self.footer, not compact, side="bottom", fill="x", before=self.body)
        self._layout_subtitles()

    @staticmethod
    def _set_packed(widget: tk.Widget, visible: bool, **kwargs: object) -> None:
        if visible:
            if not widget.winfo_manager():
                widget.pack(**kwargs)
        elif widget.winfo_manager():
            widget.pack_forget()

    def _store_geometry(self) -> None:
        key = "overlay_geometry" if self.appearance.get("compact_overlay") else "full_geometry"
        geometry = self.root.geometry()
        if geometry:
            self.appearance[key] = geometry

    def _toggle_overlay(self) -> None:
        self._store_geometry()
        self.appearance["compact_overlay"] = not bool(self.appearance.get("compact_overlay"))
        key = "overlay_geometry" if self.appearance["compact_overlay"] else "full_geometry"
        self.root.geometry(str(self.appearance[key]))
        self._apply_appearance()
        save_appearance(self.appearance)

    def _open_appearance(self) -> None:
        if self.appearance_dialog and self.appearance_dialog.top.winfo_exists():
            self.appearance_dialog.top.lift()
            return
        self._store_geometry()
        self.appearance_dialog = AppearanceWindow(self.root, self.appearance, self._apply_appearance_settings)

    def _apply_appearance_settings(self, prefs: dict, persist: bool) -> None:
        was_compact = bool(self.appearance.get("compact_overlay"))
        self._store_geometry()
        self.appearance = dict(prefs)
        is_compact = bool(self.appearance.get("compact_overlay"))
        if was_compact != is_compact:
            key = "overlay_geometry" if is_compact else "full_geometry"
            self.root.geometry(str(self.appearance[key]))
        self._apply_appearance()
        if persist:
            save_appearance(self.appearance)

    def _enqueue_ui(self, *event: object) -> None:
        try:
            self.ui_q.put_nowait(tuple(event))
        except queue.Full:
            logging.warning("UI queue full; dropped event %s", event[0] if event else "unknown")

    def _poll_ui(self) -> None:
        if self.closed:
            return
        try:
            while True:
                event = self.ui_q.get_nowait()
                kind = event[0]
                if kind == "status":
                    color = str(event[2])
                    mapped = self.palette.green if color == GREEN else self.palette.amber if color == AMBER else self.palette.red if color == RED else color
                    self.status_label.config(text=str(event[1]), fg=mapped)
                elif kind == "error":
                    text = str(event[1])
                    self.error_label.config(text=text[:150])
                    self.root.after(7000, lambda: self.error_label.config(text=""))
                elif kind == "input":
                    config = event[1]
                    if isinstance(config, AudioInputConfig):
                        self.input_label.config(text=f"INPUT: {config.description} → 24000 Hz mono PCM16")
                elif kind == "stats":
                    self.stats_label.config(text=str(event[1]))
                elif kind == "source":
                    self._append_delta("source", str(event[1]))
                elif kind == "translation":
                    self._append_delta("translation", str(event[1]))
        except queue.Empty:
            pass
        if not self.closed and self.root.winfo_exists():
            self.root.after(UI_POLL_MS, self._poll_ui)

    def _append_delta(self, side: str, delta: str) -> None:
        if not delta:
            return
        now = time.time()
        if side == "source":
            if self.source_break_pending and self.source_buffer and not self.source_buffer.endswith("\n"):
                self.source_buffer += "\n\n"
            self.source_break_pending = False
            self.source_buffer += delta
            self.last_source_delta_at = now
        else:
            if self.translation_break_pending and self.translation_buffer and not self.translation_buffer.endswith("\n"):
                self.translation_buffer += "\n\n"
            self.translation_break_pending = False
            self.translation_buffer += delta
            self.last_translation_delta_at = now
        self._render()

    def _segment_tick(self) -> None:
        if self.closed:
            return
        now = time.time()
        if self.last_source_delta_at and now - self.last_source_delta_at > SEGMENT_IDLE_SECONDS:
            self.source_break_pending = True
        if self.last_translation_delta_at and now - self.last_translation_delta_at > SEGMENT_IDLE_SECONDS:
            self.translation_break_pending = True
        if not self.closed and self.root.winfo_exists():
            self.root.after(350, self._segment_tick)

    def _render(self) -> None:
        self._replace_text(self.left_text, self.source_buffer)
        self._replace_text(self.right_text, self.translation_buffer)
        translation_parts = self.translation_buffer.count("\n\n") + (1 if self.translation_buffer.strip() else 0)
        if translation_parts:
            self.count_label.config(text=f"{translation_parts} translated segment{'s' if translation_parts != 1 else ''}")
        else:
            self.count_label.config(text="Waiting for speech")

    @staticmethod
    def _replace_text(widget: tk.Text, value: str) -> None:
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.see("end")
        widget.config(state="disabled")

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.client:
            self.client.set_paused(self.paused)
        self.pause_button.config(text="RESUME" if self.paused else "PAUSE")

    def _clear(self) -> None:
        self.source_buffer = ""
        self.translation_buffer = ""
        self.last_source_delta_at = 0.0
        self.last_translation_delta_at = 0.0
        self.source_break_pending = False
        self.translation_break_pending = False
        self._render()

    def _copy_translation(self) -> None:
        if not self.translation_buffer.strip():
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.translation_buffer)
        self.error_label.config(text="Translation copied", fg=self.palette.green)
        self.root.after(1700, lambda: self.error_label.config(text="", fg=self.palette.red))

    def _settings(self) -> None:
        self._store_geometry()
        save_appearance(self.appearance)
        self.closed = True
        if self.client:
            self.client.close()
        for widget in self.root.winfo_children():
            widget.destroy()
        self.root._timur_screen = SetupWindow(self.root, self._restart)  # type: ignore[attr-defined]

    def _restart(
        self, api_key: str, language_code: str, audio_input: AudioInputConfig,
        play_audio: bool, auto_switch_headset: bool, audio_source_mode: str
    ) -> None:
        for widget in self.root.winfo_children():
            widget.destroy()
        self.__init__(self.root, api_key, language_code, audio_input, play_audio, auto_switch_headset, audio_source_mode)

    def _close(self) -> None:
        self._store_geometry()
        try:
            save_appearance(self.appearance)
        except Exception:
            logging.exception("Could not save appearance on close")
        self.closed = True
        if self.client:
            self.client.close()
        self.root.destroy()

def _install_tk_exception_hook(root: tk.Tk) -> None:
    def report_callback_exception(exc_type, exc_value, exc_tb):
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.error("Unhandled Tk callback exception:\n%s", formatted)
        messagebox.showerror("Application error", f"{exc_value}\n\nDebug log:\n{LOG_PATH}")

    root.report_callback_exception = report_callback_exception  # type: ignore[method-assign]


def _launch(
    root: tk.Tk, api_key: str, language_code: str, audio_input: AudioInputConfig,
    play_audio: bool, auto_switch_headset: bool, audio_source_mode: str
) -> None:
    try:
        for widget in root.winfo_children():
            widget.destroy()
        root._timur_screen = TranslatorWindow(  # type: ignore[attr-defined]
            root, api_key, language_code, audio_input, play_audio, auto_switch_headset, audio_source_mode
        )
        root.deiconify()
        root.lift()
    except Exception as exc:
        logging.exception("Translator window launch failed")
        for widget in root.winfo_children():
            widget.destroy()
        root._timur_screen = SetupWindow(  # type: ignore[attr-defined]
            root, lambda key, lang, audio, play, auto, source: _launch(root, key, lang, audio, play, auto, source)
        )
        messagebox.showerror("Translator could not start", f"{exc}\n\nDebug log:\n{LOG_PATH}")


def main() -> None:
    configure_logging()
    missing = check_deps()
    if missing:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing dependencies",
            "Run install_windows.bat first.\n\nMissing: " + ", ".join(missing),
        )
        return

    root = tk.Tk()
    _install_tk_exception_hook(root)
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TCombobox", fieldbackground=SURFACE2, background=SURFACE2, foreground=TEXT)
    root._timur_screen = SetupWindow(  # type: ignore[attr-defined]
        root, lambda key, lang, audio, play, auto, source: _launch(root, key, lang, audio, play, auto, source)
    )
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            configure_logging()
            logging.exception("Fatal top-level crash")
        except Exception:
            pass
        raise
