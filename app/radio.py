import json
import logging
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("parch_mp.radio")

STATIONS_PATH = Path.home() / ".parchmp_radio.json"

DEFAULTS = [
    {"name": "SomaFM Groove Salad", "url": "https://ice1.somafm.com/groovesalad-128-mp3",
     "genre": "Ambient"},
    {"name": "SomaFM Drone Zone", "url": "https://ice1.somafm.com/dronezone-128-mp3",
     "genre": "Ambient"},
    {"name": "SomaFM Indie Pop Rocks", "url": "https://ice1.somafm.com/indiepop-128-mp3",
     "genre": "Indie"},
    {"name": "SomaFM Deep Space One", "url": "https://ice1.somafm.com/deepspaceone-128-mp3",
     "genre": "Ambient"},
    {"name": "SomaFM Lush", "url": "https://ice1.somafm.com/lush-128-mp3", "genre": "Vocal"},
    {"name": "SomaFM Secret Agent", "url": "https://ice1.somafm.com/secretagent-128-mp3",
     "genre": "Lounge"},
    {"name": "Radio Paradise Main", "url": "https://stream.radioparadise.com/mp3-192",
     "genre": "Eclectic"},
    {"name": "Radio Paradise Mellow", "url": "https://stream.radioparadise.com/mellow-192",
     "genre": "Mellow"},
    {"name": "Radio Paradise Rock", "url": "https://stream.radioparadise.com/rock-192",
     "genre": "Rock"},
]


def is_stream(path):
    if not path:
        return False
    scheme = urlparse(str(path)).scheme.lower()
    return scheme in ("http", "https", "rtsp", "mms")


def valid_url(url):
    parsed = urlparse((url or "").strip())
    return parsed.scheme.lower() in ("http", "https", "rtsp", "mms") and bool(parsed.netloc)


def load():
    if not STATIONS_PATH.exists():
        return [dict(s) for s in DEFAULTS]
    try:
        with open(STATIONS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        log.warning("radio stations unreadable", exc_info=True)
        return [dict(s) for s in DEFAULTS]
    if not isinstance(data, list):
        return [dict(s) for s in DEFAULTS]
    out = []
    for entry in data:
        if isinstance(entry, dict) and valid_url(entry.get("url")):
            out.append({"name": str(entry.get("name") or entry["url"])[:120],
                        "url": entry["url"].strip(),
                        "genre": str(entry.get("genre") or "")[:60]})
    return out or [dict(s) for s in DEFAULTS]


def save(stations):
    from .utils import write_json_atomic
    return write_json_atomic(STATIONS_PATH, stations)


def add(stations, name, url, genre=""):
    if not valid_url(url):
        return False
    url = url.strip()
    for entry in stations:
        if entry.get("url") == url:
            return False
    stations.append({"name": (name or url).strip()[:120], "url": url,
                     "genre": (genre or "").strip()[:60]})
    return True


def remove(stations, url):
    before = len(stations)
    stations[:] = [s for s in stations if s.get("url") != url]
    return len(stations) != before


def as_track(station):
    return {
        "path": station["url"],
        "title": station.get("name") or station["url"],
        "artist": station.get("genre") or "Radio",
        "album": "Internet Radio",
        "genre": station.get("genre") or "",
        "year": "",
        "duration": 0,
        "track_number": 0,
        "cover_data": None,
        "cover_path": "",
        "bitrate": 0,
        "sample_rate": 0,
        "mtime": 0.0,
        "is_stream": True,
    }
