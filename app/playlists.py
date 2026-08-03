import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

CUE_EXTENSIONS = {".cue"}
CONTAINER_EXTENSIONS = {".m3u", ".m3u8", ".pls", ".xspf", ".wpl", ".asx", ".cue"}

_CUE_LINE = re.compile(r'^\s*(\S+)\s*(.*)$')
_QUOTED = re.compile(r'"([^"]*)"')
_INDEX = re.compile(r"(\d+):(\d+):(\d+)")


def _read_text(path):
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def _resolve(base_dir, reference):
    if not reference:
        return None
    reference = reference.strip()
    if reference.startswith("file://"):
        reference = unquote(urlparse(reference).path)
    elif "://" in reference:
        return None
    reference = reference.replace("\\", os.sep)
    if not os.path.isabs(reference):
        reference = os.path.join(base_dir, reference)
    reference = os.path.normpath(reference)
    return reference if os.path.exists(reference) else None


def _unquote_value(rest):
    match = _QUOTED.search(rest)
    if match:
        return match.group(1)
    return rest.strip()


def _index_seconds(text):
    match = _INDEX.search(text)
    if not match:
        return None
    minutes, seconds, frames = (int(g) for g in match.groups())
    return minutes * 60 + seconds + frames / 75.0


def parse_cue(path):
    text = _read_text(path)
    if not text:
        return []
    base_dir = os.path.dirname(os.path.abspath(path))

    album = ""
    album_artist = ""
    genre = ""
    year = 0
    current_file = None
    tracks = []
    pending = None

    for raw in text.splitlines():
        match = _CUE_LINE.match(raw)
        if not match:
            continue
        keyword = match.group(1).upper()
        rest = match.group(2)

        if keyword == "FILE":
            resolved = _resolve(base_dir, _unquote_value(rest))
            if resolved is None:
                stem = os.path.splitext(os.path.basename(path))[0]
                for candidate in os.listdir(base_dir) if os.path.isdir(base_dir) else []:
                    if os.path.splitext(candidate)[0] == stem and \
                            not candidate.lower().endswith(".cue"):
                        resolved = os.path.join(base_dir, candidate)
                        break
            current_file = resolved
        elif keyword == "TRACK":
            if pending is not None:
                tracks.append(pending)
            pending = {"path": current_file, "title": "", "artist": "",
                       "album": album, "cue_start": 0.0, "cue_end": None,
                       "track_no": len(tracks) + 1, "genre": genre, "year": year}
        elif keyword == "TITLE":
            value = _unquote_value(rest)
            if pending is None:
                album = value
            else:
                pending["title"] = value
                pending["album"] = album
        elif keyword == "PERFORMER":
            value = _unquote_value(rest)
            if pending is None:
                album_artist = value
            else:
                pending["artist"] = value
        elif keyword == "REM":
            parts = rest.split(None, 1)
            if len(parts) == 2:
                tag = parts[0].upper()
                if tag == "GENRE":
                    genre = _unquote_value(parts[1])
                elif tag == "DATE":
                    digits = re.search(r"\d{4}", parts[1])
                    if digits:
                        year = int(digits.group(0))
        elif keyword == "INDEX" and pending is not None:
            number = rest.split(None, 1)[0] if rest.split() else "01"
            if number.strip() in ("01", "1"):
                seconds = _index_seconds(rest)
                if seconds is not None:
                    pending["cue_start"] = seconds
        elif keyword == "FILE" and pending is not None:
            pending["path"] = current_file

    if pending is not None:
        tracks.append(pending)

    result = []
    for i, entry in enumerate(tracks):
        if not entry.get("path"):
            continue
        entry["artist"] = entry["artist"] or album_artist
        entry["album"] = entry["album"] or album
        entry["albumartist"] = album_artist
        entry["genre"] = entry.get("genre") or genre
        entry["year"] = entry.get("year") or year
        entry["track_no"] = i + 1
        entry["title"] = entry["title"] or f"Track {i + 1}"
        nxt = tracks[i + 1] if i + 1 < len(tracks) else None
        if nxt is not None and nxt.get("path") == entry["path"]:
            entry["cue_end"] = nxt.get("cue_start")
        entry["cue_source"] = os.path.abspath(path)
        result.append(entry)
    return result


def parse_m3u(path):
    text = _read_text(path)
    base_dir = os.path.dirname(os.path.abspath(path))
    out = []
    title = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            _, _, meta = line.partition(":")
            if "," in meta:
                title = meta.split(",", 1)[1].strip()
            continue
        if line.startswith("#"):
            continue
        resolved = _resolve(base_dir, line)
        if resolved:
            out.append({"path": resolved, "title": title or ""})
        title = None
    return out


def parse_pls(path):
    text = _read_text(path)
    base_dir = os.path.dirname(os.path.abspath(path))
    files, titles = {}, {}
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        if key.startswith("file"):
            files[key[4:]] = value.strip()
        elif key.startswith("title"):
            titles[key[5:]] = value.strip()
    out = []
    for index in sorted(files, key=lambda k: int(k) if k.isdigit() else 0):
        resolved = _resolve(base_dir, files[index])
        if resolved:
            out.append({"path": resolved, "title": titles.get(index, "")})
    return out


def _xml_root(path):
    try:
        return ET.parse(path).getroot()
    except Exception:
        return None


def _localname(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_xspf(path):
    root = _xml_root(path)
    if root is None:
        return []
    base_dir = os.path.dirname(os.path.abspath(path))
    out = []
    for node in root.iter():
        if _localname(node.tag) != "track":
            continue
        entry = {"path": None, "title": "", "artist": "", "album": ""}
        for child in node:
            name = _localname(child.tag)
            value = (child.text or "").strip()
            if name == "location":
                entry["path"] = _resolve(base_dir, value)
            elif name == "title":
                entry["title"] = value
            elif name == "creator":
                entry["artist"] = value
            elif name == "album":
                entry["album"] = value
        if entry["path"]:
            out.append(entry)
    return out


def parse_wpl(path):
    root = _xml_root(path)
    if root is None:
        return []
    base_dir = os.path.dirname(os.path.abspath(path))
    out = []
    for node in root.iter():
        if _localname(node.tag) != "media":
            continue
        resolved = _resolve(base_dir, node.attrib.get("src", ""))
        if resolved:
            out.append({"path": resolved, "title": ""})
    return out


def parse_asx(path):
    root = _xml_root(path)
    base_dir = os.path.dirname(os.path.abspath(path))
    out = []
    if root is not None:
        for node in root.iter():
            if _localname(node.tag) != "ref":
                continue
            href = node.attrib.get("href") or node.attrib.get("HREF") or ""
            resolved = _resolve(base_dir, href)
            if resolved:
                out.append({"path": resolved, "title": ""})
        if out:
            return out
    for line in _read_text(path).splitlines():
        if "=" in line and line.strip().lower().startswith("ref"):
            resolved = _resolve(base_dir, line.split("=", 1)[1])
            if resolved:
                out.append({"path": resolved, "title": ""})
    return out


_PARSERS = {
    ".m3u": parse_m3u,
    ".m3u8": parse_m3u,
    ".pls": parse_pls,
    ".xspf": parse_xspf,
    ".wpl": parse_wpl,
    ".asx": parse_asx,
    ".cue": parse_cue,
}


def is_container(path):
    return os.path.splitext(path)[1].lower() in CONTAINER_EXTENSIONS


def parse(path):
    parser = _PARSERS.get(os.path.splitext(path)[1].lower())
    if parser is None:
        return []
    try:
        return parser(path)
    except Exception:
        return []


def sidecar_cue(audio_path):
    stem = os.path.splitext(audio_path)[0]
    for candidate in (stem + ".cue", stem + ".CUE"):
        if os.path.exists(candidate):
            return candidate
    return None


def write_m3u(path, tracks):
    lines = ["#EXTM3U"]
    for track in tracks:
        duration = int(track.get("duration") or 0)
        title = track.get("title") or os.path.basename(track.get("path", ""))
        artist = track.get("artist") or ""
        label = f"{artist} - {title}" if artist else title
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(track.get("path", ""))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def write_xspf(path, tracks):
    root = ET.Element("playlist", {"version": "1", "xmlns": "http://xspf.org/ns/0/"})
    track_list = ET.SubElement(root, "trackList")
    for track in tracks:
        node = ET.SubElement(track_list, "track")
        location = ET.SubElement(node, "location")
        location.text = "file://" + track.get("path", "")
        for tag, key in (("title", "title"), ("creator", "artist"), ("album", "album")):
            value = track.get(key)
            if value:
                ET.SubElement(node, tag).text = str(value)
        duration = int(track.get("duration") or 0)
        if duration:
            ET.SubElement(node, "duration").text = str(duration * 1000)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
