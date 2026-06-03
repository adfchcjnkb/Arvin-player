"""
Arvin Player - Custom Widgets (VinylDisc, EqualizerVisualizer, TreeItemDelegate)
"""

import math
import random
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF,
    pyqtSignal, QPointF, QByteArray, QObject
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPixmap, QImage,
    QLinearGradient, QPainterPath, QRadialGradient
)
from PyQt6.QtWidgets import QWidget, QStyle, QSizePolicy, QStyledItemDelegate, QStyleOptionViewItem


# ========== Animated Object for Vinyl ==========
class AnimatedVinylObject(QObject):
    angleChanged = pyqtSignal(float)
    
    def __init__(self):
        super().__init__()
        self._angle = 0
    
    def getAngle(self):
        return self._angle
    
    def setAngle(self, angle):
        self._angle = angle
        self.angleChanged.emit(angle)


class VinylDisc(QWidget):
    """Rotating vinyl record disc - responsive with large cover art"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._anim_obj = AnimatedVinylObject()
        self.animation = QPropertyAnimation(self._anim_obj, b"angle")
        self.animation.setDuration(2000)
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim_obj.angleChanged.connect(self._on_angle_changed)
        self._playing = False
        self.setMinimumSize(80, 80)
        self.setMaximumSize(300, 300)
        self.cover_pixmap = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
    def _on_angle_changed(self, angle):
        self._angle = angle
        self.update()
    
    def set_playing(self, playing: bool):
        if playing and not self._playing:
            self._playing = True
            self.animation.start()
        elif not playing and self._playing:
            self._playing = False
            self.animation.stop()
    
    def set_cover(self, pixmap: QPixmap):
        self.cover_pixmap = pixmap
        self.update()
    
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
        
        # Shadow effect
        shadow_path = QPainterPath()
        shadow_path.addEllipse(rect.adjusted(2, 4, 2, 4))
        painter.fillPath(shadow_path, QColor(0, 0, 0, 60))
        
        # Draw rotating vinyl
        painter.save()
        painter.translate(center)
        painter.rotate(self._angle)
        
        # Disc gradient
        disc = QRadialGradient(0, 0, radius)
        disc.setColorAt(0, QColor('#111111'))
        disc.setColorAt(0.7, QColor('#2a2a2a'))
        disc.setColorAt(1, QColor('#0f0f0f'))
        painter.setBrush(disc)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        
        # Vinyl grooves - outer ring
        pen_width = max(0.3, radius / 200)
        painter.setPen(QPen(QColor(255, 255, 255, 15), pen_width))
        groove_start = int(radius * 0.72)
        groove_end = int(radius * 0.92)
        step = max(3, int(radius / 30))
        for i in range(groove_start, groove_end, step):
            painter.drawEllipse(QPointF(0, 0), i, i)
        
        painter.restore()
        
        # Draw cover art on top (not rotating) - LARGE, 70% of vinyl
        if self.cover_pixmap and not self.cover_pixmap.isNull():
            art_size = int(radius * 1.4)
            art_rect = QRectF(-art_size/2, -art_size/2, art_size, art_size)
            painter.save()
            painter.translate(center)
            path = QPainterPath()
            path.addEllipse(art_rect)
            painter.setClipPath(path)
            scaled_pixmap = self.cover_pixmap.scaled(
                art_size, art_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(art_rect.toRect(), scaled_pixmap)
            painter.setClipping(False)
            
            # Border around cover
            painter.setPen(QPen(QColor(255, 255, 255, 50), max(1, radius / 80)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(art_rect)
            painter.restore()
        else:
            painter.save()
            painter.translate(center)
            font_size = max(12, int(radius * 0.5))
            font = QFont("Vazir", font_size, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor('#666666'))
            text_rect = QRectF(-radius*0.5, -radius*0.5, radius, radius)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "♪")
            painter.restore()


# ========== Equalizer Visualizer ==========
class EqualizerVisualizer(QWidget):
    """Professional audio visualizer with responsive bar count"""
    
    def __init__(self, num_bars=100, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.levels = [0.02] * num_bars
        self.targets = [0.02] * num_bars
        self.is_playing = False
        self.theme = 'dark'
        self.time_counter = 0
        self.beat_counter = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(30)
        
        self.bar_colors = []
        self._calculate_colors()
        
        self.setMinimumHeight(50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
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
    
    def set_playing(self, playing: bool):
        self.is_playing = playing
        if not playing:
            self.time_counter = 0
            self.beat_counter = 0
    
    def set_theme(self, theme: str):
        self.theme = theme
    
    def _update(self):
        if not self.is_playing:
            for i in range(self.num_bars):
                self.levels[i] *= 0.9
            self.update()
            return
        
        self.time_counter += 0.04
        self.beat_counter += 0.04
        
        beat_length = 0.45
        beat_progress = (self.beat_counter % beat_length) / beat_length
        
        for i in range(self.num_bars):
            freq = i / self.num_bars
            
            if freq < 0.08:
                base_amp = 0.85
                rhythm = 1.0 if beat_progress < 0.2 else 0.3
                wave = abs(math.sin(self.time_counter * 8.0))
            elif freq < 0.2:
                base_amp = 0.75
                rhythm = 0.9 if beat_progress < 0.15 else 0.4
                wave = abs(math.sin(self.time_counter * 6.0 + i * 0.3))
            elif freq < 0.4:
                base_amp = 0.6
                snare_beat = (self.beat_counter % (beat_length * 2)) / (beat_length * 2)
                rhythm = 0.8 if (0.4 < snare_beat < 0.6) or (0.9 < snare_beat < 1.0) else 0.3
                wave = abs(math.cos(self.time_counter * 5.0 + i * 0.5))
            elif freq < 0.6:
                base_amp = 0.5
                eighth = (self.beat_counter % (beat_length / 2)) / (beat_length / 2)
                rhythm = 0.7 if eighth < 0.3 else 0.2
                wave = abs(math.sin(self.time_counter * 10.0 + i * 0.7))
            elif freq < 0.8:
                base_amp = 0.4
                rhythm = 0.6 + 0.4 * abs(math.sin(self.time_counter * 12.0))
                wave = abs(math.cos(self.time_counter * 7.0 + i * 0.4))
            else:
                base_amp = 0.3
                rhythm = 0.5 + 0.5 * abs(math.sin(self.time_counter * 15.0 + i * 0.6))
                wave = abs(math.cos(self.time_counter * 9.0 + i * 0.3))
            
            target = base_amp * (rhythm * 0.6 + wave * 0.4)
            
            if random.random() > 0.95:
                target = min(1.0, target * 1.5)
            if random.random() > 0.97:
                target = 0.8 + 0.2 * random.random()
            
            self.targets[i] = max(0.02, min(1.0, target))
            
            if self.targets[i] > self.levels[i]:
                self.levels[i] += (self.targets[i] - self.levels[i]) * 0.35
            else:
                self.levels[i] += (self.targets[i] - self.levels[i]) * 0.2
        
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        if h <= 0 or w <= 0:
            return
        
        # Responsive bar count
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
            
            x = int(i * (bar_width + spacing))
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
    """Custom delegate to draw three-dot menu button in actions column"""
    
    def paint(self, painter, option, index):
        if index.column() == 3:
            painter.save()
            
            rect = option.rect
            btn_size = min(22, rect.height() - 12)
            btn_rect = QRectF(
                rect.x() + (rect.width() - btn_size) / 2,
                rect.y() + (rect.height() - btn_size) / 2,
                btn_size,
                btn_size
            )
            
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.setBrush(QColor("#FF6B6B"))
            else:
                painter.setBrush(QColor(80, 80, 80, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawRoundedRect(btn_rect, btn_size / 2, btn_size / 2)
            
            dot_color = QColor("#FFFFFF") if option.state & QStyle.StateFlag.State_MouseOver else QColor("#BBBBBB")
            dot_size = 1.2
            dot_spacing = 3.5
            center_x = btn_rect.center().x()
            center_y = btn_rect.center().y()
            
            painter.setBrush(dot_color)
            painter.setPen(Qt.PenStyle.NoPen)
            for dy in [-dot_spacing, 0, dot_spacing]:
                painter.drawEllipse(QPointF(center_x, center_y + dy), dot_size, dot_size)
            
            painter.restore()
            return
        
        super().paint(painter, option, index)
    
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        from PyQt6.QtCore import QSize
        return QSize(size.width(), 45)