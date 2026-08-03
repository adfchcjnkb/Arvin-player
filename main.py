
import sys
import os
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon, QFontDatabase
from PyQt6.QtCore import Qt

from app.player import ParchPlayer
from app.utils import resource_path, find_font_file, APP_TITLE, APP_VERSION

logging.basicConfig(
    level=os.environ.get("PARCHMP_LOGLEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("parch_mp.main")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if "--selftest" in sys.argv:
        from app import native
        info = native.summary()
        print(f"{APP_TITLE} {APP_VERSION}")
        print(f"engine   : {info['backend']}")
        print(f"parch_dsp: {info['dsp'] or 'unavailable'}")
        print(f"parch_core: {info['core'] or 'unavailable'}")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font_path = find_font_file("Vazir.ttf")
    default_font = QFont("Noto Sans", 10)
    if font_path:
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                default_font = QFont(families[0], 10)
    default_font.setFamilies([default_font.family(), "Noto Sans", "DejaVu Sans", "sans-serif"])
    app.setFont(default_font)
    
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    try:
        player = ParchPlayer()
        sys.exit(app.exec())
    except Exception:
        log.exception("Fatal error while starting Parch MP")
        sys.exit(1)
