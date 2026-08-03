
import os
import sys
import json
import logging
import tempfile
from pathlib import Path

log = logging.getLogger("parch_mp.utils")

APP_TITLE = "Parch MP"
APP_VERSION = "9.0.0"
APP_AUTHOR = "Arvin"
APP_TAGLINE = "Parch Music Player"

DEFAULT_LANGUAGE = "en_US"
SETTINGS_PATH = Path.home() / ".parchmp_settings.json"
SESSION_PATH = Path.home() / ".parchmp_playlist.json"

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".wave", ".ogg", ".oga", ".opus", ".m4a", ".m4b",
    ".aac", ".wma", ".aif", ".aiff", ".aifc", ".alac", ".wv", ".ape", ".tta",
    ".mpc", ".mp+", ".shn", ".vqf", ".amr", ".ac3", ".eac3", ".dts", ".mka",
    ".dsf", ".dff", ".weba", ".mid", ".midi",
}
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".pls", ".xspf", ".wpl", ".asx", ".cue"}


def audio_name_filter(music_label="Music Files", all_label="All Files"):
    exts = sorted(AUDIO_EXTENSIONS | PLAYLIST_EXTENSIONS)
    pattern = " ".join("*" + e for e in exts)
    return f"{music_label} ({pattern});;{all_label} (*)"


def safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def find_font_file(expected_filename: str):
    fonts_dir = resource_path(os.path.join("assets", "fonts"))
    if not expected_filename or not os.path.isdir(fonts_dir):
        return None

    exact = os.path.join(fonts_dir, expected_filename)
    if os.path.exists(exact):
        return exact

    stem = os.path.splitext(expected_filename)[0].lower()
    try:
        best = None
        for entry in os.listdir(fonts_dir):
            name = entry.lower()
            if not name.endswith((".ttf", ".otf", ".ttc")):
                continue
            if name == expected_filename.lower() or name.startswith(stem):
                if best is None or len(entry) < len(best):
                    best = entry
        if best:
            return os.path.join(fonts_dir, best)
    except OSError:
        pass
    return None


def format_time(sec):
    if sec < 0:
        return "00:00"
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def write_json_atomic(path, data) -> bool:
    path = Path(path)
    tmp_name = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_name, str(path))
        return True
    except Exception:
        log.warning("Could not write %s atomically", path, exc_info=True)
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        return False


_SETTINGS_DEFAULTS = {
    "language": DEFAULT_LANGUAGE,
    "theme": "dark",
    "volume": 70,
}


def _validate_settings(s: dict) -> dict:
    if s.get("theme") not in ("dark", "light"):
        s["theme"] = "dark"
    if not isinstance(s.get("language"), str) or not s["language"]:
        s["language"] = DEFAULT_LANGUAGE
    try:
        s["volume"] = max(0, min(100, int(s.get("volume", 70))))
    except (TypeError, ValueError):
        s["volume"] = 70
    if "eq_preamp" in s:
        try:
            s["eq_preamp"] = max(-24.0, min(24.0, float(s["eq_preamp"])))
        except (TypeError, ValueError):
            s["eq_preamp"] = 0.0
    gains = s.get("eq_gains")
    if gains is not None:
        if isinstance(gains, list) and gains and all(isinstance(x, (int, float)) for x in gains):
            s["eq_gains"] = [max(-24.0, min(24.0, float(x))) for x in gains]
        else:
            s.pop("eq_gains", None)
    return s


def load_settings():
    if not SETTINGS_PATH.exists():
        return dict(_SETTINGS_DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        log.warning("Settings file unreadable/corrupt; using defaults", exc_info=True)
        return dict(_SETTINGS_DEFAULTS)
    if not isinstance(data, dict):
        return dict(_SETTINGS_DEFAULTS)
    settings = dict(_SETTINGS_DEFAULTS)
    settings.update(data)
    return _validate_settings(settings)


def save_settings(settings: dict):
    write_json_atomic(SETTINGS_PATH, settings)
