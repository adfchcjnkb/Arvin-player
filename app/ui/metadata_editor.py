
import os

from PyQt6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QWidget,
)

from app.i18n import tr, LANGUAGES

_COVER_PX = 150
_COVER_MAX = 1000


class MetadataEditorDialog(QDialog):

    def __init__(self, track, theme, language, parent=None):
        super().__init__(parent)
        self._track = track
        self._lang = language
        self.result_fields = None
        self.cover_action = "keep"
        self.cover_bytes = None
        self.cover_mime = None

        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if LANGUAGES[language]["rtl"]
            else Qt.LayoutDirection.LeftToRight)
        self.setWindowTitle(tr(language, "edit_metadata"))
        self.setMinimumWidth(460)
        self.setStyleSheet(
            f"QDialog{{background:{theme['bg_secondary']};color:{theme['text_primary']};}}"
            f"QLineEdit{{background:{theme['input_bg']};color:{theme['text_primary']};"
            f"border:1px solid {theme['input_border']};border-radius:6px;padding:6px;}}")

        self._build()

    def _build(self):
        lang = self._lang
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(16)

        cover_col = QVBoxLayout()
        cover_col.setSpacing(8)
        self._cover_label = QLabel()
        self._cover_label.setFixedSize(_COVER_PX, _COVER_PX)
        self._cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_label.setStyleSheet("border-radius:10px;background:rgba(128,128,128,40);")
        self._has_cover = False
        self._set_cover_from_track()
        cover_col.addWidget(self._cover_label)

        self._hint_label = QLabel(tr(lang, "md_cover_hint"))
        self._hint_label.setWordWrap(True)
        self._hint_label.setFixedWidth(_COVER_PX)
        self._hint_label.setStyleSheet("font-size:10px;opacity:0.8;")
        cover_col.addWidget(self._hint_label)

        self._warn_label = QLabel("")
        self._warn_label.setWordWrap(True)
        self._warn_label.setFixedWidth(_COVER_PX)
        self._warn_label.setStyleSheet("font-size:10px;color:#E5A50A;")
        self._warn_label.setVisible(False)
        cover_col.addWidget(self._warn_label)

        self._change_btn = QPushButton()
        self._change_btn.setObjectName("smallBtn")
        self._change_btn.clicked.connect(self._pick_cover)
        cover_col.addWidget(self._change_btn)
        self._remove_btn = QPushButton(tr(lang, "md_remove_cover"))
        self._remove_btn.setObjectName("smallBtn")
        self._remove_btn.clicked.connect(self._remove_cover)
        cover_col.addWidget(self._remove_btn)
        cover_col.addStretch()
        body.addLayout(cover_col)
        self._update_cover_buttons()

        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(10)
        self._edits = {}
        rows = [
            ("title", "md_title"), ("artist", "md_artist"), ("album", "md_album"),
            ("genre", "md_genre"), ("year", "md_year"), ("track_number", "md_track"),
        ]
        for r, (fkey, label_key) in enumerate(rows):
            lbl = QLabel(tr(lang, label_key))
            edit = QLineEdit(self._field_text(fkey))
            grid.addWidget(lbl, r, 0)
            grid.addWidget(edit, r, 1)
            self._edits[fkey] = edit
        fields_wrap = QWidget()
        fields_wrap.setLayout(grid)
        body.addWidget(fields_wrap, 1)
        root.addLayout(body)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton(tr(lang, "md_cancel"))
        cancel_btn.setObjectName("smallBtn")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = QPushButton(tr(lang, "md_save"))
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._on_save)
        buttons.addWidget(save_btn)
        root.addLayout(buttons)

    def _field_text(self, fkey):
        val = self._track.get(fkey, "")
        if fkey == "track_number" and not val:
            return ""
        return str(val) if val not in (None, 0) else ""

    def _update_cover_buttons(self):
        self._change_btn.setText(
            tr(self._lang, "md_change_cover" if self._has_cover else "md_add_cover"))
        self._remove_btn.setVisible(self._has_cover)

    def _set_cover_from_track(self):
        data = self._track.get("cover_data")
        path = self._track.get("cover_path")
        if data:
            self._has_cover = True
            self._show_cover_bytes(bytes(data))
        elif path and os.path.exists(path):
            self._has_cover = True
            self._show_cover_pixmap(QPixmap(path))
        else:
            self._has_cover = False
            self._show_no_cover()

    def _show_cover_bytes(self, data):
        img = QImage.fromData(QByteArray(data))
        if img.isNull():
            self._show_no_cover()
        else:
            self._show_cover_pixmap(QPixmap.fromImage(img))

    def _show_cover_pixmap(self, pixmap):
        if pixmap.isNull():
            self._show_no_cover()
            return
        self._cover_label.setPixmap(pixmap.scaled(
            _COVER_PX, _COVER_PX, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _show_no_cover(self):
        self._cover_label.setPixmap(QPixmap())
        self._cover_label.setText(tr(self._lang, "md_no_cover"))

    def _pick_cover(self):
        exts = "*.jpg *.jpeg *.jfif *.png *.webp *.bmp *.gif *.tif *.tiff *.ico *.avif *.heic"
        img_filter = (f"{tr(self._lang, 'md_images')} ({exts});;"
                      f"{tr(self._lang, 'all_files')} (*)")
        path, _ = QFileDialog.getOpenFileName(
            self, tr(self._lang, "md_add_cover"), "", img_filter)
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self._warn_label.setText(tr(self._lang, "md_bad_image"))
            self._warn_label.setVisible(True)
            return
        data, mime = self._encode_cover(img)
        if not data:
            return
        self.cover_bytes = data
        self.cover_mime = mime
        self.cover_action = "replace"
        self._has_cover = True
        self._show_cover_pixmap(QPixmap.fromImage(img))
        self._update_cover_buttons()
        self._check_cover_quality(img)

    def _check_cover_quality(self, img):
        w, h = img.width(), img.height()
        msgs = []
        if w and h and abs(w - h) > max(w, h) * 0.05:
            msgs.append(tr(self._lang, "md_warn_square"))
        if min(w, h) < 300:
            msgs.append(tr(self._lang, "md_warn_small"))
        self._warn_label.setText("  ".join(msgs))
        self._warn_label.setVisible(bool(msgs))

    @staticmethod
    def _encode_cover(img):
        if img.width() > _COVER_MAX or img.height() > _COVER_MAX:
            img = img.scaled(_COVER_MAX, _COVER_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        flat = QImage(img.size(), QImage.Format.Format_RGB888)
        flat.fill(QColor("white"))
        painter = QPainter(flat)
        painter.drawImage(0, 0, img)
        painter.end()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        ok = flat.save(buf, "JPEG", 90)
        data = bytes(buf.data())
        buf.close()
        if not ok or not data:
            return None, None
        return data, "image/jpeg"

    def _remove_cover(self):
        self.cover_action = "remove"
        self.cover_bytes = None
        self._has_cover = False
        self._warn_label.setVisible(False)
        self._show_no_cover()
        self._update_cover_buttons()

    def _on_save(self):
        self.result_fields = {fkey: edit.text().strip() for fkey, edit in self._edits.items()}
        self.accept()
