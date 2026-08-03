import numpy as np
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QRect,
    pyqtSignal, QPointF, QByteArray, QObject, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPixmap, QImage,
    QLinearGradient, QPainterPath, QRadialGradient
)
from PyQt6.QtWidgets import (
    QWidget, QStyle, QSizePolicy, QStyledItemDelegate, QStyleOptionViewItem, QLabel, QMenu,
    QSlider,
)

from .. import native
from . import icons


class StayOpenMenu(QMenu):

    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action is not None and action.isEnabled() and action.isCheckable():
            action.trigger()
            return
        super().mouseReleaseEvent(event)


class ElidingLabel(QLabel):

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full = text
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 24 else "")
        self._apply_elide()

    def full_text(self):
        return self._full

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, Qt.TextElideMode.ElideRight, max(0, self.width() - 2)))


class VinylDisc(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self.setMinimumSize(70, 70)
        self.setMaximumSize(420, 420)
        self.cover_pixmap = None
        self._disc_cache = None
        self._disc_cache_size = -1
        self._scaled_cover_cache = None
        self._scaled_cover_key = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_theme(self, theme_name: str):
        if theme_name != self._theme:
            self._theme = theme_name
            self._disc_cache = None
            self._disc_cache_size = -1
            self.update()

    def set_playing(self, playing: bool):
        pass

    def set_cover(self, pixmap: QPixmap):
        self.cover_pixmap = pixmap
        self._scaled_cover_cache = None
        self._scaled_cover_key = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._disc_cache = None
        self._disc_cache_size = -1
        self._scaled_cover_cache = None
        self._scaled_cover_key = None

    def _build_disc_pixmap(self, size: int) -> QPixmap:
        c_in, c_mid, c_out = '#111111', '#2a2a2a', '#0f0f0f'
        groove = QColor(255, 255, 255, 15)
        dpr = self.devicePixelRatioF() or 1.0
        pm = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = size / 2
        p.translate(radius, radius)

        disc = QRadialGradient(0, 0, radius)
        disc.setColorAt(0, QColor(c_in))
        disc.setColorAt(0.7, QColor(c_mid))
        disc.setColorAt(1, QColor(c_out))
        p.setBrush(disc)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(0, 0), radius, radius)

        p.setPen(QPen(groove, max(0.3, radius / 200)))
        step = max(3, int(radius / 30))
        for i in range(int(radius * 0.72), int(radius * 0.92), step):
            p.drawEllipse(QPointF(0, 0), i, i)
        p.end()
        return pm

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        available = min(self.width(), self.height())
        size = min(available - 10, 300)
        if size < 50:
            return

        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        center = rect.center()
        radius = size / 2

        shadow_path = QPainterPath()
        shadow_path.addEllipse(rect.adjusted(2, 4, 2, 4))
        painter.fillPath(shadow_path, QColor(0, 0, 0, 60))

        if self._disc_cache is None or self._disc_cache_size != size:
            self._disc_cache = self._build_disc_pixmap(size)
            self._disc_cache_size = size
        painter.drawPixmap(QPointF(center.x() - radius, center.y() - radius), self._disc_cache)

        if self.cover_pixmap and not self.cover_pixmap.isNull():
            art_size = int(radius * 1.4)
            art_rect = QRectF(-art_size/2, -art_size/2, art_size, art_size)
            key = (self.cover_pixmap.cacheKey(), art_size)
            if self._scaled_cover_key != key:
                self._scaled_cover_cache = self.cover_pixmap.scaled(
                    art_size, art_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._scaled_cover_key = key
            painter.save()
            painter.translate(center)
            path = QPainterPath()
            path.addEllipse(art_rect)
            painter.setClipPath(path)
            painter.drawPixmap(art_rect.toRect(), self._scaled_cover_cache)
            painter.setClipping(False)

            painter.setPen(QPen(QColor(255, 255, 255, 50), max(1, radius / 80)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(art_rect)
            painter.restore()
        else:
            painter.save()
            painter.translate(center)
            font_size = max(12, int(radius * 0.5))
            font = QFont("Noto Sans", font_size, QFont.Weight.Bold)
            font.setFamilies(["Noto Sans", "DejaVu Sans", "sans-serif"])
            painter.setFont(font)
            painter.setPen(QColor('#666666'))
            text_rect = QRectF(-radius*0.5, -radius*0.5, radius, radius)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "♪")
            painter.restore()


class EqualizerVisualizer(QWidget):

    FFT_SIZE = 2048

    def __init__(self, num_bars=100, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.levels = [0.02] * num_bars
        self.targets = [0.02] * num_bars
        self.is_playing = False
        self._settled = False
        self.theme = 'dark'

        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._rtl = False

        self._ring = np.zeros(self.FFT_SIZE, dtype=np.float32)
        self._sample_rate = 44100
        self._window = np.hanning(self.FFT_SIZE).astype(np.float32)
        self._band_edges = self._compute_band_edges(self.num_bars, self._sample_rate)
        self._band_log_centers = self._compute_band_log_centers(self._band_edges)
        self._has_fresh_data = False

        self._spectrum = None
        self._native_levels = None
        if native.HAVE_CORE:
            try:
                self._spectrum = native.core.Spectrum(
                    bars=num_bars, sample_rate=float(self._sample_rate),
                    fft_size=self.FFT_SIZE)
                self._spectrum.set_response(attack=0.62, release=0.16, tilt=0.34)
            except Exception:
                self._spectrum = None


        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(33)

        self.bar_colors = []
        self._calculate_colors()

        self.setMinimumHeight(50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _compute_band_edges(self, num_bars, sample_rate):
        nyquist = max(1000.0, sample_rate / 2.0)
        low = 30.0
        high = min(16000.0, nyquist * 0.98)
        return np.logspace(np.log10(low), np.log10(high), num_bars + 1)

    @staticmethod
    def _compute_band_log_centers(band_edges: np.ndarray) -> np.ndarray:
        centers = np.sqrt(band_edges[:-1] * band_edges[1:])
        return np.log10(np.maximum(centers, 1.0))

    def set_rtl(self, rtl: bool):
        rtl = bool(rtl)
        if rtl != self._rtl:
            self._rtl = rtl
            self.update()

    def _calculate_colors(self):
        self.bar_colors = []
        for i in range(self.num_bars):
            freq = i / self.num_bars
            if freq < 0.1:
                self.bar_colors.append(QColor("#FF1493"))
            elif freq < 0.25:
                self.bar_colors.append(QColor("#1DB954"))
            elif freq < 0.5:
                self.bar_colors.append(QColor("#4ECDC4"))
            elif freq < 0.75:
                self.bar_colors.append(QColor("#FFD93D"))
            else:
                self.bar_colors.append(QColor("#FF6B6B"))

    def feed_audio(self, samples: np.ndarray, sample_rate: int):
        if samples is None or len(samples) == 0:
            return
        if sample_rate and sample_rate != self._sample_rate:
            self._sample_rate = sample_rate
            self._band_edges = self._compute_band_edges(self.num_bars, self._sample_rate)
            self._band_log_centers = self._compute_band_log_centers(self._band_edges)
            if self._spectrum is not None:
                self._spectrum.set_sample_rate(float(sample_rate))

        if self._spectrum is not None:
            try:
                self._native_levels = self._spectrum.feed(
                    np.ascontiguousarray(samples, dtype=np.float32), 1)
                self._has_fresh_data = True
                self._settled = False
                return
            except Exception:
                self._spectrum = None

        n = len(samples)
        if n >= self.FFT_SIZE:
            self._ring = np.ascontiguousarray(samples[-self.FFT_SIZE:], dtype=np.float32)
        else:
            self._ring = np.concatenate([self._ring[n:], samples.astype(np.float32)])
        self._has_fresh_data = True
        self._settled = False

    def set_playing(self, playing: bool):
        self.is_playing = playing
        if playing:
            self._settled = False
        else:
            self._has_fresh_data = False

    def set_theme(self, theme: str):
        self.theme = theme

    def _update(self):
        if self._spectrum is not None:
            if self.is_playing and self._has_fresh_data and self._native_levels:
                self.targets = [max(0.02, v) for v in self._native_levels]
            else:
                self._native_levels = self._spectrum.decay(0.85)
                self.targets = [max(0.02, v) for v in self._native_levels]
            for i in range(self.num_bars):
                delta = self.targets[i] - self.levels[i]
                self.levels[i] += delta * (0.6 if delta > 0 else 0.32)
            if self.is_playing and self._has_fresh_data:
                self.update()
            elif not self._settled:
                self.update()
                if max(self.levels) <= 0.02 + 1e-6:
                    self._settled = True
            return

        if self.is_playing and self._has_fresh_data:
            windowed = self._ring * self._window
            spectrum = np.abs(np.fft.rfft(windowed))
            freqs = np.fft.rfftfreq(self.FFT_SIZE, d=1.0 / self._sample_rate)

            log_freqs = np.log10(np.maximum(freqs, 1.0))
            mags = np.interp(self._band_log_centers, log_freqs, spectrum)

            band_idx = np.arange(self.num_bars)
            gain = 1.0 + (band_idx / self.num_bars) * 1.6

            raw = np.log1p(mags * gain) / 5.5

            knee = 0.85
            over = raw > knee
            vals = np.where(over, knee + (1.0 - knee) * np.tanh((raw - knee) / (1.0 - knee)), raw)
            self.targets = np.clip(vals, 0.02, 1.0).tolist()
        else:
            self.targets = [t * 0.85 for t in self.targets]

        for i in range(self.num_bars):
            if self.targets[i] > self.levels[i]:
                self.levels[i] += (self.targets[i] - self.levels[i]) * 0.6
            else:
                self.levels[i] += (self.targets[i] - self.levels[i]) * 0.3

        if self.is_playing and self._has_fresh_data:
            self.update()
        elif not self._settled:
            self.update()
            if max(self.levels) <= 0.02 + 1e-6:
                self._settled = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        if h <= 0 or w <= 0:
            return
        
        bars_to_draw = min(self.num_bars, max(8, w // 4))
        
        total_spacing = 2 * bars_to_draw
        bar_width = max(1, (w - total_spacing) / bars_to_draw)
        spacing = 2
        bar_area_h = h * 0.65
        mirror_start = bar_area_h + 8
        
        step = self.num_bars / bars_to_draw if bars_to_draw > 0 else 1
        
        for i in range(bars_to_draw):
            idx = min(int(i * step), self.num_bars - 1)
            level = max(0.02, self.levels[idx])
            bar_height = level * bar_area_h
            
            slot = (bars_to_draw - 1 - i) if self._rtl else i
            x = int(slot * (bar_width + spacing))
            y = int(bar_area_h - bar_height)
            
            color = self.bar_colors[idx]
            
            gradient = QLinearGradient(0, bar_area_h, 0, y)
            gradient.setColorAt(0, color.darker(180))
            gradient.setColorAt(0.3, color)
            gradient.setColorAt(0.7, color.lighter(130))
            gradient.setColorAt(1, color.lighter(180))
            
            bar_path = QPainterPath()
            bar_rect = QRectF(x, y, bar_width, bar_height)
            radius = min(bar_width / 2, 3)
            bar_path.addRoundedRect(bar_rect, radius, radius)
            painter.fillPath(bar_path, gradient)
            
            if level > 0.3 and bar_height > 10:
                glow_alpha = int(level * 100)
                glow_color = QColor(color.red(), color.green(), color.blue(), glow_alpha)
                glow_rect = QRectF(x - 2, y - 3, bar_width + 4, 6)
                glow_gradient = QLinearGradient(0, y - 3, 0, y + 3)
                glow_gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 0))
                glow_gradient.setColorAt(0.5, glow_color)
                glow_gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
                painter.fillRect(glow_rect, glow_gradient)
            
            if level > 0.08 and mirror_start < h:
                mirror_h = min(bar_height * 0.7, h - mirror_start - 2)
                if mirror_h > 0:
                    mirror_y = mirror_start
                    
                    mirror_alpha = int(level * 70)
                    mirror_color = QColor(color.red(), color.green(), color.blue(), mirror_alpha)
                    
                    mirror_gradient = QLinearGradient(0, mirror_y, 0, mirror_y + mirror_h)
                    mirror_gradient.setColorAt(0, mirror_color)
                    mirror_gradient.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), int(mirror_alpha * 0.5)))
                    mirror_gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
                    
                    mirror_rect = QRectF(x, mirror_y, bar_width, mirror_h)
                    mirror_path = QPainterPath()
                    mirror_radius = min(bar_width / 2, 2)
                    mirror_path.addRoundedRect(mirror_rect, mirror_radius, mirror_radius)
                    painter.fillPath(mirror_path, mirror_gradient)
        
        painter.end()


class TreeItemDelegate(QStyledItemDelegate):

    FAVOURITE_ROLE = Qt.ItemDataRole.UserRole + 11
    RATING_ROLE = Qt.ItemDataRole.UserRole + 12

    def __init__(self, theme: str = 'dark', parent=None):
        super().__init__(parent)
        self.theme = theme
        self.favourite_column = 3
        self.actions_column = 4
        self._fg = QColor("#FFFFFF")
        self._muted = QColor("#7C8598")
        self._chip = QColor(80, 80, 80, 80)
        self._accent = QColor("#FF6B6B")

    def set_theme(self, theme: str):
        self.theme = theme

    def set_palette(self, text_primary, text_secondary, accent, light):
        self._fg = QColor(text_primary)
        self._muted = QColor(text_secondary)
        self._accent = QColor(accent)
        self._chip = QColor(0, 0, 0, 28) if light else QColor(255, 255, 255, 26)
        self.theme = 'light' if light else 'dark'

    def _neutral(self):
        return self._muted

    def paint(self, painter, option, index):
        column = index.column()
        if column == self.favourite_column:
            self._paint_favourite(painter, option, index)
            return
        if column == self.actions_column:
            self._paint_actions(painter, option, index)
            return
        super().paint(painter, option, index)

    def _paint_favourite(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        size = min(20, rect.height() - 14)
        box = QRectF(rect.x() + (rect.width() - size) / 2,
                     rect.y() + (rect.height() - size) / 2, size, size)
        favourite = bool(index.data(self.FAVOURITE_ROLE))
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if favourite:
            colour = QColor("#FF4D6D")
        elif hovered:
            colour = self._accent
        else:
            colour = self._neutral()
        icons.paint(painter, "heart_filled" if favourite else "heart", box, colour, 1.9)
        painter.restore()

    def _paint_actions(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        btn = min(22, rect.height() - 12)
        box = QRectF(rect.x() + (rect.width() - btn) / 2,
                     rect.y() + (rect.height() - btn) / 2, btn, btn)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setBrush(self._accent if hovered else self._chip)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(box, btn / 2, btn / 2)
        colour = QColor("#FFFFFF") if hovered else self._fg
        icons.paint(painter, "dots", box.adjusted(4, 4, -4, -4), colour, 1.6)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), 45)


class WaveformSeekBar(QWidget):
    seek_requested = pyqtSignal(float)

    MODE_WAVE = "wave"
    MODE_MOOD = "mood"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self.theme = "dark"
        self.mode = self.MODE_WAVE
        self._wave = np.zeros(0, dtype=np.float32)
        self._mood = b""
        self._position = 0.0
        self._duration = 0.0
        self._hover = -1.0
        self._dragging = False
        self._rtl = False
        self._accent = QColor("#1DB954")
        self._idle = QColor("#3a3f4b")
        self._track = QColor("#22252c")

    def set_theme(self, theme, accent=None):
        self.theme = theme
        if accent:
            self._accent = QColor(accent)
        if theme == "light":
            self._idle = QColor("#a8b0be")
            self._track = QColor("#eef0f4")
        else:
            self._idle = QColor("#484e5c")
            self._track = QColor("#1e2129")
        self.update()

    def set_rtl(self, rtl):
        rtl = bool(rtl)
        if rtl != self._rtl:
            self._rtl = rtl
            self.update()

    def set_mode(self, mode):
        if mode in (self.MODE_WAVE, self.MODE_MOOD) and mode != self.mode:
            self.mode = mode
            self.update()

    def toggle_mode(self):
        self.set_mode(self.MODE_MOOD if self.mode == self.MODE_WAVE else self.MODE_WAVE)
        return self.mode

    def has_data(self):
        return self._wave.size > 0 or len(self._mood) > 0

    def set_analysis(self, waveform, moodbar):
        self._wave = np.asarray(waveform, dtype=np.float32) if waveform is not None \
            else np.zeros(0, dtype=np.float32)
        self._mood = moodbar or b""
        self.update()

    def clear(self):
        self._wave = np.zeros(0, dtype=np.float32)
        self._mood = b""
        self._position = 0.0
        self.update()

    def set_duration(self, seconds):
        self._duration = max(0.0, float(seconds))
        self.update()

    def set_position(self, seconds):
        self._position = max(0.0, float(seconds))
        self.update()

    def progress(self):
        if self._duration <= 0:
            return 0.0
        return min(1.0, self._position / self._duration)

    def _fraction_at(self, x):
        w = max(1, self.width())
        frac = min(1.0, max(0.0, x / w))
        return 1.0 - frac if self._rtl else frac

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.seek_requested.emit(self._fraction_at(event.position().x()))

    def mouseMoveEvent(self, event):
        self._hover = self._fraction_at(event.position().x())
        if self._dragging:
            self.seek_requested.emit(self._hover)
        self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def leaveEvent(self, event):
        self._hover = -1.0
        self.update()

    def _column_rects(self, w, count):
        step = w / float(count)
        return step

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        painter.fillRect(0, 0, w, h, self._track)
        played = self.progress()

        if self.mode == self.MODE_MOOD and len(self._mood) >= 3:
            self._paint_mood(painter, w, h, played)
        elif self._wave.size:
            self._paint_wave(painter, w, h, played)
        else:
            self._paint_plain(painter, w, h, played)

        if self._hover >= 0.0:
            hx = (1.0 - self._hover) * w if self._rtl else self._hover * w
            painter.setPen(QPen(QColor(255, 255, 255, 120), 1))
            painter.drawLine(int(hx), 0, int(hx), h)

    def _paint_plain(self, painter, w, h, played):
        bar = QRect(0, h // 2 - 2, w, 4)
        painter.fillRect(bar, self._idle)
        filled = int(w * played)
        if self._rtl:
            painter.fillRect(QRect(w - filled, bar.y(), filled, bar.height()), self._accent)
        else:
            painter.fillRect(QRect(0, bar.y(), filled, bar.height()), self._accent)

    def _paint_wave(self, painter, w, h, played):
        n = self._wave.size
        mid = h / 2.0
        cut = played * w
        painter.setPen(Qt.PenStyle.NoPen)
        step = max(1.0, w / float(n))
        bar_w = max(1, int(step) - 1) if step >= 2 else 1
        for i in range(n):
            x = i * step
            if self._rtl:
                x = w - x - step
            amp = float(self._wave[i])
            hh = max(1.0, amp * (h * 0.46))
            lit = (w - x - step) < cut if self._rtl else x < cut
            painter.setBrush(self._accent if lit else self._idle)
            painter.drawRect(QRectF(x, mid - hh, bar_w, hh * 2.0))

    def _paint_mood(self, painter, w, h, played):
        cols = len(self._mood) // 3
        if cols <= 0:
            return
        step = w / float(cols)
        cut = played * w
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(cols):
            r = self._mood[i * 3]
            g = self._mood[i * 3 + 1]
            b = self._mood[i * 3 + 2]
            x = i * step
            if self._rtl:
                x = w - x - step
            colour = QColor(r, g, b)
            lit = (w - x - step) < cut if self._rtl else x < cut
            if not lit:
                colour = QColor(int(r * 0.42), int(g * 0.42), int(b * 0.42))
            painter.setBrush(colour)
            painter.drawRect(QRectF(x, 0, step + 1.0, h))

        painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
        px = (1.0 - played) * w if self._rtl else cut
        painter.drawLine(int(px), 0, int(px), h)


class SeekSlider(QSlider):

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._pressed = False

    def _value_at(self, pos):
        span = self.maximum() - self.minimum()
        if span <= 0:
            return self.minimum()
        if self.orientation() == Qt.Orientation.Horizontal:
            width = max(1, self.width())
            fraction = pos.x() / width
            if self.invertedAppearance():
                fraction = 1.0 - fraction
        else:
            height = max(1, self.height())
            fraction = 1.0 - pos.y() / height
        fraction = min(1.0, max(0.0, fraction))
        return int(self.minimum() + round(fraction * span))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.setValue(self._value_at(event.position()))
            self.sliderPressed.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed:
            self.setValue(self._value_at(event.position()))
            self.sliderMoved.emit(self.value())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.setValue(self._value_at(event.position()))
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
