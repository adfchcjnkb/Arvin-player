"""
Arvin Player - Utilities and Constants
"""

import os
import sys

# ========== Constants ==========
APP_TITLE = "Arvin Player"
APP_VERSION = "7.5.0"
APP_AUTHOR = "Arvin"

# ========== Resource Path Helper ==========
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def format_time(sec):
    """Format seconds to MM:SS or HH:MM:SS"""
    if sec < 0:
        return "00:00"
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"