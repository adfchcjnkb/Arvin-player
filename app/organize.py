import os
import re
import shutil

TOKENS = ("albumartist", "artist", "album", "title", "genre", "year",
          "track", "track2", "disc", "ext")

DEFAULT_PATTERN = "%albumartist%/%album%/%track2% - %title%"

_TOKEN_RE = re.compile(r"%([a-z0-9_]+)%", re.I)
_ILLEGAL = '<>:"/\\|?*'
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | \
            {f"LPT{i}" for i in range(1, 10)}


def sanitise_component(text, replacement="_"):
    text = "".join(replacement if c in _ILLEGAL or ord(c) < 32 else c for c in str(text or ""))
    text = text.strip().rstrip(".")
    if not text:
        return "Unknown"
    if text.upper().split(".")[0] in _RESERVED:
        text = "_" + text
    return text[:120]


def values_for(track):
    def clean(value, fallback=""):
        value = str(value or "").strip()
        return value or fallback

    try:
        track_no = int(track.get("track_number") or track.get("track_no") or 0)
    except (TypeError, ValueError):
        track_no = 0
    artist = clean(track.get("artist"), "Unknown Artist")
    album_artist = clean(track.get("albumartist"), artist)
    ext = os.path.splitext(track.get("path", ""))[1].lstrip(".").lower()

    return {
        "artist": artist,
        "albumartist": album_artist,
        "album": clean(track.get("album"), "Unknown Album"),
        "title": clean(track.get("title"),
                       os.path.splitext(os.path.basename(track.get("path", "")))[0]),
        "genre": clean(track.get("genre")),
        "year": clean(track.get("year")),
        "track": str(track_no) if track_no else "",
        "track2": f"{track_no:02d}" if track_no else "",
        "disc": clean(track.get("disc")),
        "ext": ext,
    }


def build_path(track, pattern, root):
    values = values_for(track)
    pattern = (pattern or DEFAULT_PATTERN).replace("\\", "/")

    def replace(match):
        return values.get(match.group(1).lower(), "")

    filled = _TOKEN_RE.sub(replace, pattern)
    parts = [sanitise_component(p) for p in filled.split("/") if p.strip()]
    if not parts:
        return None
    ext = values["ext"]
    if ext and not parts[-1].lower().endswith("." + ext):
        parts[-1] = parts[-1] + "." + ext
    return os.path.normpath(os.path.join(root, *parts))


def plan(tracks, pattern, root):
    entries = []
    seen = set()
    for track in tracks:
        source = track.get("path")
        if not source or not os.path.exists(source):
            continue
        target = build_path(track, pattern, root)
        if not target:
            continue
        base, ext = os.path.splitext(target)
        counter = 2
        while target.lower() in seen or (
                os.path.exists(target) and os.path.abspath(target) != os.path.abspath(source)):
            target = f"{base} ({counter}){ext}"
            counter += 1
            if counter > 999:
                break
        seen.add(target.lower())
        entries.append({"source": source, "target": target,
                        "same": os.path.abspath(source) == os.path.abspath(target)})
    return entries


def apply(entries, move=True, progress=None):
    done, errors = 0, []
    for i, entry in enumerate(entries):
        source, target = entry["source"], entry["target"]
        if entry.get("same"):
            continue
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if move:
                shutil.move(source, target)
            else:
                shutil.copy2(source, target)
            entry["done"] = True
            done += 1
        except Exception as exc:
            entry["done"] = False
            errors.append((source, str(exc)))
        if progress is not None:
            progress(i + 1, len(entries))
    return done, errors


def preview_line(entry, root):
    try:
        rel = os.path.relpath(entry["target"], root)
    except ValueError:
        rel = entry["target"]
    return f"{os.path.basename(entry['source'])}   ->   {rel}"
