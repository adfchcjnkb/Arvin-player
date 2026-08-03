import os
import sys

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPixmap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ui import icons


def render(size):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#1DB954"))
    gradient.setColorAt(1.0, QColor("#0E7A38"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    inset = size * 0.17
    box = QRectF(inset, inset, size - inset * 2, size - inset * 2)
    icons.paint(painter, "disc", box, QColor("#FFFFFF"), 1.7)
    painter.end()
    return pix


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "packaging/parch-mp.png"
    app = QGuiApplication([])
    sizes = [16, 24, 32, 48, 64, 128, 256, 512]
    base = os.path.splitext(out)[0]
    for size in sizes:
        render(size).save(f"{base}-{size}.png", "PNG")
    render(512).save(out, "PNG")
    if out.endswith(".png"):
        render(256).save(base + ".ico", "ICO")
    print("icons written next to", out)
    del app


if __name__ == "__main__":
    main()
