import os

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPixmap

from .ui import icons

BACKGROUND = QColor("#12141A")
TEXT = QColor("#F2F4F8")
SUBTEXT = QColor("#9AA3B2")


def _cover_pixmap(metadata_manager, path, size):
    if not path:
        return None
    try:
        meta = metadata_manager.get_metadata(path)
        data = meta.get("cover_art") or meta.get("cover")
        if not data:
            return None
        pix = QPixmap()
        if not pix.loadFromData(data):
            return None
        return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


def _placeholder(size, label):
    pix = QPixmap(size, size)
    pix.fill(QColor("#242833"))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    icons.paint(painter, "disc", QRectF(size * 0.32, size * 0.28, size * 0.36, size * 0.36),
                QColor("#5C6577"), 2.0)
    font = QFont()
    font.setPointSize(max(7, size // 16))
    painter.setFont(font)
    painter.setPen(SUBTEXT)
    painter.drawText(QRectF(6, size * 0.7, size - 12, size * 0.26),
                     int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop |
                         Qt.TextFlag.TextWordWrap), label or "")
    painter.end()
    return pix


def collect_albums(library, limit):
    rows = library.top_albums(limit) if hasattr(library, "top_albums") else []
    if rows:
        return rows
    counts = {}
    for track in library.top_tracks(600):
        artist = track.get("albumartist") or track.get("artist") or "?"
        album = track.get("album") or ""
        if not album:
            continue
        key = (artist.lower(), album.lower())
        entry = counts.setdefault(key, {"aartist": artist, "album": album,
                                        "plays": 0, "sample": track.get("path")})
        entry["plays"] += int(track.get("play_count") or 0)
        if not entry.get("sample"):
            entry["sample"] = track.get("path")
    ordered = sorted(counts.values(), key=lambda e: e["plays"], reverse=True)
    return ordered[:limit]


def render(library, metadata_manager, rows=3, columns=3, tile=300, title="",
           show_labels=True):
    rows = max(1, min(int(rows), 10))
    columns = max(1, min(int(columns), 10))
    tile = max(120, min(int(tile), 600))

    albums = collect_albums(library, rows * columns)
    border = max(18, tile // 12)
    spacing = max(8, tile // 30)
    label_h = int(tile * 0.22) if show_labels else 0
    header = int(tile * 0.28) if title else 0

    width = border * 2 + tile * columns + spacing * (columns - 1)
    height = (border * 2 + header + (tile + label_h) * rows +
              spacing * (rows - 1))

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(BACKGROUND)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    if title:
        font = QFont()
        font.setPointSize(max(12, tile // 12))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(TEXT)
        painter.drawText(QRectF(border, border * 0.5, width - border * 2, header),
                         int(Qt.AlignmentFlag.AlignCenter), title)

    name_font = QFont()
    name_font.setPointSize(max(7, tile // 24))
    name_font.setBold(True)
    artist_font = QFont()
    artist_font.setPointSize(max(6, tile // 28))

    index = 0
    for r in range(rows):
        for c in range(columns):
            x = border + c * (tile + spacing)
            y = border + header + r * (tile + label_h + spacing)
            entry = albums[index] if index < len(albums) else None
            index += 1

            if entry is None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#1A1D26"))
                painter.drawRoundedRect(QRectF(x, y, tile, tile), 6, 6)
                continue

            cover = _cover_pixmap(metadata_manager, entry.get("sample"), tile)
            if cover is None:
                cover = _placeholder(tile, entry.get("album", ""))
            painter.drawPixmap(int(x), int(y), cover.copy(0, 0, tile, tile))

            if show_labels:
                painter.setFont(name_font)
                painter.setPen(TEXT)
                painter.drawText(
                    QRectF(x, y + tile + 4, tile, label_h * 0.55),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                    _elide(painter, entry.get("album", ""), tile - 6))
                painter.setFont(artist_font)
                painter.setPen(SUBTEXT)
                painter.drawText(
                    QRectF(x, y + tile + 4 + label_h * 0.52, tile, label_h * 0.45),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                    _elide(painter, entry.get("aartist", ""), tile - 6))

    painter.end()
    return image


def _elide(painter, text, width):
    metrics = painter.fontMetrics()
    return metrics.elidedText(text or "", Qt.TextElideMode.ElideRight, int(width))


def save(library, metadata_manager, path, rows=3, columns=3, tile=300, title="",
         show_labels=True):
    image = render(library, metadata_manager, rows, columns, tile, title, show_labels)
    if not os.path.splitext(path)[1]:
        path += ".png"
    return path if image.save(path) else None
