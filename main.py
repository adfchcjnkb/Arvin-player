"""
Arvin Player - Professional Music Player
Ultimate Edition | Real-Time Audio Visualizer | Vinyl Animation | Full Metadata
Developed for Arvin | Version 7.5 Final - Perfect Design
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon, QFontDatabase
from PyQt6.QtCore import Qt

from player import ArvinPlayer
from utils import resource_path, APP_TITLE, APP_VERSION

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Load Vazir font
    font_path = resource_path("Vazir.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            app.setFont(QFont(font_family, 10))
    else:
        app.setFont(QFont("Segoe UI", 10))
    
    # Set app icon
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    try:
        player = ArvinPlayer()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)