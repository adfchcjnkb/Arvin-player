import os
import re

_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_META = re.compile(r"^\[(ti|ar|al|by|offset|length|re|ve):(.*)\]$", re.I)

SIDECARS = (".lrc", ".txt")


def _parse_lrc(text):
    lines = []
    offset = 0.0
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        meta = _META.match(raw)
        if meta:
            if meta.group(1).lower() == "offset":
                try:
                    offset = float(meta.group(2).strip()) / 1000.0
                except ValueError:
                    offset = 0.0
            continue
        stamps = list(_TIMESTAMP.finditer(raw))
        if not stamps:
            continue
        content = _TIMESTAMP.sub("", raw).strip()
        for m in stamps:
            minutes = int(m.group(1))
            seconds = int(m.group(2))
            frac = m.group(3) or "0"
            frac_val = int(frac) / (10 ** len(frac))
            lines.append((minutes * 60 + seconds + frac_val, content))
    lines.sort(key=lambda item: item[0])
    if offset:
        lines = [(max(0.0, t + offset), c) for t, c in lines]
    return lines


def _plain(text):
    return [(None, line.strip()) for line in text.splitlines() if line.strip()]


def _read(path):
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def _embedded(path):
    try:
        import mutagen
    except ImportError:
        return ""
    try:
        audio = mutagen.File(path)
    except Exception:
        return ""
    if audio is None:
        return ""
    tags = getattr(audio, "tags", None)
    if tags is None:
        return ""
    try:
        for key in tags.keys():
            if str(key).upper().startswith("USLT"):
                return str(tags[key].text)
    except Exception:
        pass
    for key in ("LYRICS", "lyrics", "\xa9lyr", "UNSYNCEDLYRICS"):
        try:
            value = tags.get(key)
        except Exception:
            value = None
        if value:
            if isinstance(value, list):
                value = value[0]
            return str(value)
    return ""


def load(path):
    if not path:
        return [], False
    stem = os.path.splitext(path)[0]
    for ext in SIDECARS:
        candidate = stem + ext
        if os.path.exists(candidate):
            text = _read(candidate)
            if text:
                parsed = _parse_lrc(text)
                if parsed:
                    return parsed, True
                return _plain(text), False

    text = _embedded(path)
    if text:
        parsed = _parse_lrc(text)
        if parsed:
            return parsed, True
        return _plain(text), False
    return [], False


def active_index(lines, position):
    if not lines or lines[0][0] is None:
        return -1
    lo, hi, best = 0, len(lines) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if lines[mid][0] <= position:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best
