import json
import logging
import os
from pathlib import Path

from .core import ThemeManager

log = logging.getLogger("parch_mp.themes")

THEMES_DIR = Path.home() / ".parchmp_themes"

BUILTIN = {
    "midnight": {
        "base": "dark", "label": "Midnight",
        "bg_primary": "#07080D", "bg_secondary": "#12141F", "bg_card": "#171A27",
        "bg_surface": "#171A27", "bg_surface_light": "#212637",
        "accent_primary": "#6C8CFF", "accent_secondary": "#FF7A8A",
        "accent_tertiary": "#5AD1E6", "playing_bg": "#1b2440",
        "playing_border": "#6C8CFF", "input_focus": "#6C8CFF",
        "tree_alt_bg": "#171A27", "button_bg": "#171A27", "input_bg": "#171A27",
    },
    "ember": {
        "base": "dark", "label": "Ember",
        "bg_primary": "#0F0A08", "bg_secondary": "#1D1512", "bg_card": "#241A16",
        "bg_surface": "#241A16", "bg_surface_light": "#31241E",
        "accent_primary": "#FF7A3C", "accent_secondary": "#FFB13C",
        "accent_tertiary": "#E0574F", "playing_bg": "#3a2118",
        "playing_border": "#FF7A3C", "input_focus": "#FF7A3C",
        "tree_alt_bg": "#241A16", "button_bg": "#241A16", "input_bg": "#241A16",
    },
    "forest": {
        "base": "dark", "label": "Forest",
        "bg_primary": "#070D0A", "bg_secondary": "#111E17", "bg_card": "#16261D",
        "bg_surface": "#16261D", "bg_surface_light": "#1E3328",
        "accent_primary": "#4CD98A", "accent_secondary": "#E6C86A",
        "accent_tertiary": "#5FBFA8", "playing_bg": "#173323",
        "playing_border": "#4CD98A", "input_focus": "#4CD98A",
        "tree_alt_bg": "#16261D", "button_bg": "#16261D", "input_bg": "#16261D",
    },
    "grape": {
        "base": "dark", "label": "Grape",
        "bg_primary": "#0B0813", "bg_secondary": "#181227", "bg_card": "#1F1733",
        "bg_surface": "#1F1733", "bg_surface_light": "#2B2145",
        "accent_primary": "#B47CFF", "accent_secondary": "#FF7AC8",
        "accent_tertiary": "#7FA6FF", "playing_bg": "#2a1d47",
        "playing_border": "#B47CFF", "input_focus": "#B47CFF",
        "tree_alt_bg": "#1F1733", "button_bg": "#1F1733", "input_bg": "#1F1733",
    },
    "paper": {
        "base": "light", "label": "Paper",
        "bg_primary": "#F3EFE7", "bg_secondary": "#FBF8F2", "bg_card": "#FFFDF8",
        "bg_surface": "#F3EFE7", "bg_surface_light": "#EAE4D8",
        "accent_primary": "#C2703D", "accent_secondary": "#8C6A4A",
        "accent_tertiary": "#5B8A72", "playing_bg": "#f2e3d4",
        "playing_border": "#C2703D", "input_focus": "#C2703D",
        "tree_alt_bg": "#FBF8F2", "button_bg": "#EAE4D8", "input_bg": "#FFFDF8",
        "text_primary": "#3A322A", "text_secondary": "#7A6E60", "border": "#DCD3C4",
    },
    "nord": {
        "base": "dark", "label": "Nord",
        "bg_primary": "#2E3440", "bg_secondary": "#3B4252", "bg_card": "#434C5E",
        "bg_surface": "#434C5E", "bg_surface_light": "#4C566A",
        "accent_primary": "#88C0D0", "accent_secondary": "#BF616A",
        "accent_tertiary": "#A3BE8C", "playing_bg": "#3f5163",
        "playing_border": "#88C0D0", "input_focus": "#88C0D0",
        "tree_alt_bg": "#434C5E", "button_bg": "#434C5E", "input_bg": "#434C5E",
        "text_primary": "#ECEFF4", "text_secondary": "#B8C0CC", "border": "#4C566A",
    },
}

_REQUIRED = ("bg_primary", "bg_secondary", "accent_primary")
_cache = {}


def _valid_colour(value):
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("rgba(") and value.endswith(")"):
        return True
    return value.startswith("#") and len(value) in (4, 7, 9)


def _sanitise(data, base_theme):
    merged = dict(base_theme)
    for key, value in data.items():
        if key in ("base", "label", "name"):
            continue
        if key in merged and _valid_colour(value):
            merged[key] = value
    return merged


def user_dir():
    try:
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return THEMES_DIR


def load_user_themes():
    out = {}
    directory = user_dir()
    if not directory.is_dir():
        return out
    for entry in sorted(directory.glob("*.json")):
        try:
            with open(entry, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            log.warning("could not read theme %s", entry, exc_info=True)
            continue
        if not isinstance(data, dict):
            continue
        if not any(_valid_colour(data.get(k, "")) for k in _REQUIRED):
            continue
        key = entry.stem.lower()
        data.setdefault("label", entry.stem)
        out[key] = data
    return out


def catalogue():
    entries = {
        "dark": {"label": "Dark", "base": "dark", "builtin": True},
        "light": {"label": "Light", "base": "light", "builtin": True},
    }
    for key, data in BUILTIN.items():
        entries[key] = {"label": data.get("label", key.title()),
                        "base": data.get("base", "dark"), "builtin": True}
    for key, data in load_user_themes().items():
        if key in entries:
            key = f"user_{key}"
        entries[key] = {"label": data.get("label", key), "base": data.get("base", "dark"),
                        "builtin": False}
    return entries


def resolve(name):
    name = (name or "dark").lower()
    if name in _cache:
        return _cache[name]

    if name == "light":
        theme = dict(ThemeManager.LIGHT)
    elif name == "dark":
        theme = dict(ThemeManager.DARK)
    else:
        data = BUILTIN.get(name)
        if data is None:
            user = load_user_themes()
            data = user.get(name) or user.get(name[5:] if name.startswith("user_") else name)
        if data is None:
            theme = dict(ThemeManager.DARK)
        else:
            base = ThemeManager.LIGHT if data.get("base") == "light" else ThemeManager.DARK
            theme = _sanitise(data, base)
    theme["name"] = name
    _cache[name] = theme
    return theme


def is_light(name):
    return resolve(name).get("name") == "light" or \
        (BUILTIN.get((name or "").lower(), {}).get("base") == "light") or \
        load_user_themes().get((name or "").lower(), {}).get("base") == "light"


def clear_cache():
    _cache.clear()


def install():
    ThemeManager.get_theme = staticmethod(resolve)


def export_template(path):
    sample = dict(BUILTIN["midnight"])
    sample["label"] = "My Theme"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(sample, handle, indent=2)
    return path
