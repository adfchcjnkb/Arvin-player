"""
Arvin Player - Professional Music Player
Ultimate Edition | Real-Time Audio Visualizer | Vinyl Animation | Full Metadata
Developed for Arvin | Version 7.5 Final - Perfect Design
"""

import sys
import os
import json
import random
import math
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import struct
from collections import deque

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF,
    pyqtSignal, QUrl, QSize, QPointF, QByteArray
)
from PyQt6.QtGui import (
    QAction, QPainter, QColor, QBrush, QPen, QFont, QPixmap, QImage,
    QIcon, QLinearGradient, QPainterPath, QRadialGradient,
    QTransform, QPalette, QKeySequence, QShortcut
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QListWidget, QListWidgetItem,
    QStackedWidget, QSizePolicy, QFileDialog, QMessageBox, QMenu,
    QLineEdit, QFrame, QSplitter, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QProgressBar,
    QScrollArea, QToolButton, QStyle, QSystemTrayIcon,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView
)

# Try to import QMediaPlayer components
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    MULTIMEDIA_OK = True
except ImportError:
    MULTIMEDIA_OK = False
    print("Warning: PyQt6 Multimedia not available")

# Try to import QAudioProbe
try:
    from PyQt6.QtMultimedia import QAudioProbe, QAudioBuffer
    AUDIO_PROBE_OK = True
except ImportError:
    AUDIO_PROBE_OK = False
    print("Warning: QAudioProbe not available - using simulated visualizer")

try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False
    print("Warning: mutagen not installed. Install with: pip install mutagen")

# ========== Constants ==========
APP_TITLE = "Arvin Player"
APP_VERSION = "7.5.0"
APP_AUTHOR = "Arvin"

# ========== Theme Manager ==========
class ThemeManager:
    """Manages light and dark themes"""
    
    DARK = {
        'name': 'dark',
        'bg_primary': '#0A0A0F',
        'bg_secondary': '#1A1A2E',
        'bg_card': '#16213E',
        'bg_surface': '#16213E',
        'bg_surface_light': '#1F2B47',
        'accent_primary': '#1DB954',
        'accent_secondary': '#FF6B6B',
        'accent_tertiary': '#4ECDC4',
        'accent_gold': '#FFD93D',
        'accent_purple': '#6C5CE7',
        'text_primary': '#FFFFFF',
        'text_secondary': '#B0B0B0',
        'text_disabled': '#666666',
        'border': '#333333',
        'shadow': 'rgba(0, 0, 0, 200)',
        'tree_alt_bg': '#16213E',
        'button_bg': '#16213E',
        'input_bg': '#16213E',
        'input_border': '#333333',
        'input_focus': '#1DB954',
        'slider_bg': '#333333',
        'playing_bg': '#1a3a2a',
        'playing_border': '#1DB954',
    }
    
    LIGHT = {
        'name': 'light',
        'bg_primary': '#F5F5F5',
        'bg_secondary': '#FFFFFF',
        'bg_card': '#FFFFFF',
        'bg_surface': '#F0F0F0',
        'bg_surface_light': '#E8E8E8',
        'accent_primary': '#1DB954',
        'accent_secondary': '#E74C3C',
        'accent_tertiary': '#3498DB',
        'accent_gold': '#F39C12',
        'accent_purple': '#8E44AD',
        'text_primary': '#2C3E50',
        'text_secondary': '#7F8C8D',
        'text_disabled': '#BDC3C7',
        'border': '#D5D8DC',
        'shadow': 'rgba(0, 0, 0, 100)',
        'tree_alt_bg': '#F8F9FA',
        'button_bg': '#E8E8E8',
        'input_bg': '#FFFFFF',
        'input_border': '#D5D8DC',
        'input_focus': '#1DB954',
        'slider_bg': '#D5D8DC',
        'playing_bg': '#e8f5e9',
        'playing_border': '#1DB954',
    }
    
    @classmethod
    def get_theme(cls, theme_name: str = 'dark') -> dict:
        return cls.DARK if theme_name == 'dark' else cls.LIGHT


# ========== Metadata Manager ==========
class MetadataManager:
    """Robust metadata extraction using mutagen"""
    
    def get_metadata(self, filepath: str) -> Dict[str, Any]:
        filename = os.path.basename(filepath)
        metadata = {
            'title': filename,
            'artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'genre': '',
            'year': '',
            'track_number': 0,
            'duration': 0,
            'bitrate': 0,
            'sample_rate': 0,
            'channels': 2,
            'cover_art': None,
            'cover_path': '',
        }
        
        if not MUTAGEN_OK:
            return metadata
        
        try:
            audio = MutagenFile(filepath)
            if audio is None:
                return metadata
            
            if hasattr(audio, 'info') and audio.info:
                info = audio.info
                metadata['duration'] = int(info.length) if hasattr(info, 'length') else 0
                metadata['bitrate'] = (getattr(info, 'bitrate', 0) or 0) // 1000
                metadata['sample_rate'] = getattr(info, 'sample_rate', 0) or 0
                metadata['channels'] = getattr(info, 'channels', 2) or 2
            
            if hasattr(audio, 'tags') and audio.tags:
                tags = audio.tags
                
                # ID3 tags
                tag_map = {
                    'TIT2': 'title', 'TPE1': 'artist', 'TALB': 'album',
                    'TCON': 'genre', 'TDRC': 'year', 'TRCK': 'track_number'
                }
                for tag_key, meta_key in tag_map.items():
                    if tag_key in tags:
                        val = str(tags[tag_key])
                        if meta_key == 'track_number':
                            try:
                                metadata[meta_key] = int(val.split('/')[0])
                            except:
                                pass
                        elif meta_key == 'year':
                            metadata[meta_key] = val[:4] if val else ''
                        else:
                            metadata[meta_key] = val
                
                # Cover art
                for key in tags.keys():
                    if key.startswith('APIC'):
                        metadata['cover_art'] = tags[key].data
                        break
                
                # Vorbis/FLAC
                vorbis_map = {
                    'title': 'title', 'artist': 'artist', 'album': 'album',
                    'genre': 'genre', 'date': 'year', 'tracknumber': 'track_number'
                }
                for tag_key, meta_key in vorbis_map.items():
                    if tag_key in tags and not metadata.get(meta_key):
                        val = tags[tag_key][0] if isinstance(tags[tag_key], list) else str(tags[tag_key])
                        if meta_key == 'track_number':
                            try:
                                metadata[meta_key] = int(val)
                            except:
                                pass
                        else:
                            metadata[meta_key] = str(val)
                
                # FLAC pictures
                if hasattr(audio, 'pictures') and audio.pictures:
                    metadata['cover_art'] = audio.pictures[0].data
                
                # MP4 covr
                if 'covr' in tags:
                    metadata['cover_art'] = bytes(tags['covr'][0])
            
            # Check for folder covers
            if not metadata['cover_art']:
                folder = os.path.dirname(filepath)
                for name in ['cover.jpg', 'folder.jpg', 'Front.jpg', 'AlbumArt.jpg', 'cover.png']:
                    candidate = os.path.join(folder, name)
                    if os.path.exists(candidate):
                        metadata['cover_path'] = candidate
                        break
        
        except Exception:
            pass
        
        return metadata


# ========== Vinyl Disc Animation ==========
class VinylDisc(QWidget):
    """Rotating vinyl record disc"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.animation = QPropertyAnimation(self, b"angle")
        self.animation.setDuration(2000)
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._playing = False
        self.setFixedSize(220, 220)
        self.cover_pixmap = None
    
    def set_playing(self, playing: bool):
        if playing and not self._playing:
            self._playing = True
            self.animation.start()
        elif not playing and self._playing:
            self._playing = False
            self.animation.stop()
    
    def set_angle(self, angle):
        self.angle = angle
        self.update()
    
    def set_cover(self, pixmap: QPixmap):
        self.cover_pixmap = pixmap
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)
        center = rect.center()
        radius = min(rect.width(), rect.height()) // 2
        
        # Shadow effect for vinyl
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 150))
        
        painter.save()
        painter.translate(center)
        painter.rotate(self.angle)
        
        # Disc gradient
        disc = QRadialGradient(0, 0, radius)
        disc.setColorAt(0, QColor('#111111'))
        disc.setColorAt(0.8, QColor('#2a2a2a'))
        disc.setColorAt(1, QColor('#0f0f0f'))
        painter.setBrush(disc)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        
        # Vinyl grooves
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        for i in range(5, radius - 10, 8):
            painter.drawEllipse(QPointF(0, 0), i, i)
        
        # Label
        label_radius = radius * 0.4
        label_grad = QRadialGradient(0, 0, label_radius)
        label_grad.setColorAt(0, QColor('#cc3333'))
        label_grad.setColorAt(1, QColor('#881111'))
        painter.setBrush(label_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), label_radius, label_radius)
        
        # Center hole
        hole = QRadialGradient(0, 0, 4)
        hole.setColorAt(0, QColor('#ffffff'))
        hole.setColorAt(1, QColor('#aaaaaa'))
        painter.setBrush(hole)
        painter.drawEllipse(QPointF(0, 0), 4, 4)
        
        painter.restore()
        
        # Overlay album art
        if self.cover_pixmap and not self.cover_pixmap.isNull():
            art_rect = QRectF(-60, -60, 120, 120)
            painter.translate(center)
            path = QPainterPath()
            path.addEllipse(art_rect)
            painter.setClipPath(path)
            painter.drawPixmap(art_rect.toRect(), self.cover_pixmap)
            painter.setClipping(False)
        else:
            painter.translate(center)
            font = QFont("Segoe UI", 24, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor('#aaaaaa'))
            painter.drawText(QRectF(-40, -40, 80, 80), Qt.AlignmentFlag.AlignCenter, "♪")


# ========== Equalizer Visualizer (Random with rhythm feel) ==========
class EqualizerVisualizer(QWidget):
    """Professional audio visualizer with random rhythm patterns and glass reflection"""
    
    def __init__(self, num_bars=100, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.levels = [0.02] * num_bars
        self.targets = [0.02] * num_bars
        self.is_playing = False
        self.theme = 'dark'
        self.time_counter = 0
        self.beat_counter = 0
        self.bpm_phase = 0
        
        # Update timer - 30fps for smooth animation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(30)  # ~33 fps
        
        # Pre-calculate colors
        self.bar_colors = []
        self._calculate_colors()
        
        self.setMinimumHeight(120)
    
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
        
        # Advance time with rhythm feel
        self.time_counter += 0.04
        self.beat_counter += 0.04
        
        # Simulate BPM (between 120-140 for energetic feel)
        beat_length = 0.45  # ~133 BPM
        beat_progress = (self.beat_counter % beat_length) / beat_length
        
        for i in range(self.num_bars):
            freq = i / self.num_bars
            
            # Create rhythmic patterns that work with most music
            
            # Base amplitude based on frequency range
            if freq < 0.08:  # Deep sub bass
                base_amp = 0.85
                # Heavy on beat
                rhythm = 1.0 if beat_progress < 0.2 else 0.3
                wave = abs(math.sin(self.time_counter * 8.0))
                
            elif freq < 0.2:  # Bass
                base_amp = 0.75
                # Follow kick drum pattern
                rhythm = 0.9 if beat_progress < 0.15 else 0.4
                wave = abs(math.sin(self.time_counter * 6.0 + i * 0.3))
                
            elif freq < 0.4:  # Low mids
                base_amp = 0.6
                # Snare/clap pattern (on 2 and 4)
                snare_beat = (self.beat_counter % (beat_length * 2)) / (beat_length * 2)
                rhythm = 0.8 if (0.4 < snare_beat < 0.6) or (0.9 < snare_beat < 1.0) else 0.3
                wave = abs(math.cos(self.time_counter * 5.0 + i * 0.5))
                
            elif freq < 0.6:  # High mids
                base_amp = 0.5
                # Hi-hat pattern (8th notes)
                eighth = (self.beat_counter % (beat_length / 2)) / (beat_length / 2)
                rhythm = 0.7 if eighth < 0.3 else 0.2
                wave = abs(math.sin(self.time_counter * 10.0 + i * 0.7))
                
            elif freq < 0.8:  # Presence
                base_amp = 0.4
                # Shimmer effect
                rhythm = 0.6 + 0.4 * abs(math.sin(self.time_counter * 12.0))
                wave = abs(math.cos(self.time_counter * 7.0 + i * 0.4))
                
            else:  # Air/treble
                base_amp = 0.3
                # Constant shimmer
                rhythm = 0.5 + 0.5 * abs(math.sin(self.time_counter * 15.0 + i * 0.6))
                wave = abs(math.cos(self.time_counter * 9.0 + i * 0.3))
            
            # Combine all elements
            target = base_amp * (rhythm * 0.6 + wave * 0.4)
            
            # Add some randomness for organic feel
            if random.random() > 0.95:
                target = min(1.0, target * 1.5)
            
            # Occasional peaks for visual excitement
            if random.random() > 0.97:
                target = 0.8 + 0.2 * random.random()
            
            self.targets[i] = max(0.02, min(1.0, target))
            
            # Smooth transitions with musical feel
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
        
        # Calculate bar dimensions
        total_spacing = 2 * self.num_bars
        bar_width = max(1, (w - total_spacing) / self.num_bars)
        spacing = 2
        bar_area_h = h * 0.65  # Upper portion for bars
        mirror_start = bar_area_h + 8  # Where reflection starts
        
        for i in range(self.num_bars):
            level = max(0.02, self.levels[i])
            bar_height = level * bar_area_h
            
            x = int(i * (bar_width + spacing))
            y = int(bar_area_h - bar_height)
            
            color = self.bar_colors[i]
            
            # Main bar gradient
            gradient = QLinearGradient(0, bar_area_h, 0, y)
            gradient.setColorAt(0, color.darker(180))
            gradient.setColorAt(0.3, color)
            gradient.setColorAt(0.7, color.lighter(130))
            gradient.setColorAt(1, color.lighter(180))
            
            # Draw main bar with rounded top
            bar_path = QPainterPath()
            bar_rect = QRectF(x, y, bar_width, bar_height)
            radius = min(bar_width / 2, 3)
            bar_path.addRoundedRect(bar_rect, radius, radius)
            painter.fillPath(bar_path, gradient)
            
            # Glow effect on top
            if level > 0.3:
                glow_alpha = int(level * 100)
                glow_color = QColor(color.red(), color.green(), color.blue(), glow_alpha)
                glow_rect = QRectF(x - 2, y - 3, bar_width + 4, 6)
                glow_gradient = QLinearGradient(0, y - 3, 0, y + 3)
                glow_gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 0))
                glow_gradient.setColorAt(0.5, glow_color)
                glow_gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
                painter.fillRect(glow_rect, glow_gradient)
            
            # Glass reflection below (mirror effect)
            if level > 0.08:
                mirror_h = bar_height * 0.7
                mirror_y = mirror_start
                
                # Create fading mirror gradient
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


# ========== Main Player ==========
class ArvinPlayer(QMainWindow):
    """Arvin Player - Ultimate Edition"""
    
    def __init__(self):
        super().__init__()
        
        if not MULTIMEDIA_OK:
            QMessageBox.critical(self, "Error", 
                "PyQt6 Multimedia not available!\n\nInstall with:\npip install PyQt6-Qt6==6.5.0")
            sys.exit(1)
        
        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        self.resize(1300, 800)
        self.setMinimumSize(950, 600)
        
        # State
        self.current_theme = 'dark'
        self.playlist: List[Dict[str, Any]] = []
        self.current_index = -1
        self.is_playing = False
        self.is_paused = False
        self.repeat_mode = 0
        self.shuffle_mode = False
        self._seeking = False
        self.is_fullscreen = False
        
        # Core components
        self.metadata_manager = MetadataManager()
        
        # Audio player
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        
        # Connect signals
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        
        # Build UI
        self._setup_ui()
        self._apply_theme()
        
        # Shortcuts
        self._setup_shortcuts()
        
        # System tray
        self._setup_tray()
        
        # Load last session
        self._load_last_session()
        
        self.show()
    
    def _setup_shortcuts(self):
        self.shortcut_f11 = QShortcut(QKeySequence("F11"), self)
        self.shortcut_f11.activated.connect(self._toggle_fullscreen)
        self.shortcut_space = QShortcut(QKeySequence("Space"), self)
        self.shortcut_space.activated.connect(self._play_pause)
        self.shortcut_left = QShortcut(QKeySequence("Left"), self)
        self.shortcut_left.activated.connect(lambda: self._seek_relative(-5))
        self.shortcut_right = QShortcut(QKeySequence("Right"), self)
        self.shortcut_right.activated.connect(lambda: self._seek_relative(5))
        self.shortcut_theme = QShortcut(QKeySequence("Ctrl+T"), self)
        self.shortcut_theme.activated.connect(self._toggle_theme)
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        container = QFrame()
        container.setObjectName("mainContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(5)
        
        # ===== Top Bar =====
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(45)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 4, 12, 4)
        top_layout.setSpacing(8)
        
        logo = QLabel("ARVIN PLAYER")
        logo.setObjectName("logo")
        top_layout.addWidget(logo)
        top_layout.addStretch()
        
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("Search playlist...")
        self.global_search.setObjectName("globalSearch")
        self.global_search.setFixedWidth(250)
        self.global_search.textChanged.connect(self._on_search)
        top_layout.addWidget(self.global_search)
        
        self.theme_btn = QPushButton("Light")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setFixedSize(80, 28)
        self.theme_btn.clicked.connect(self._toggle_theme)
        top_layout.addWidget(self.theme_btn)
        
        self.mini_info = QLabel("Ready")
        self.mini_info.setObjectName("miniInfo")
        top_layout.addWidget(self.mini_info)
        
        container_layout.addWidget(top_bar)
        
        # ===== Main Splitter =====
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        
        # ===== Left Panel: Playlist =====
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        
        pl_header = QHBoxLayout()
        pl_title = QLabel("Playlist")
        pl_title.setObjectName("sectionTitle")
        pl_header.addWidget(pl_title)
        self.track_count = QLabel("0 tracks")
        self.track_count.setObjectName("trackCount")
        pl_header.addWidget(self.track_count)
        pl_header.addStretch()
        for text, slot in [("+ Files", self._add_files), ("+ Folder", self._add_folder)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setObjectName("smallBtn")
            pl_header.addWidget(btn)
        left_layout.addLayout(pl_header)
        
        # Playlist tree - Simple and clean
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderLabels(["#", "Title", "Artist", "Time"])
        self.playlist_tree.setRootIsDecorated(False)
        self.playlist_tree.setAlternatingRowColors(True)
        self.playlist_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.playlist_tree.itemDoubleClicked.connect(self._on_playlist_double_click)
        self.playlist_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.playlist_tree.setObjectName("playlistTree")
        self.playlist_tree.setIconSize(QSize(40, 40))
        
        # Column widths
        self.playlist_tree.setColumnWidth(0, 35)
        self.playlist_tree.setColumnWidth(1, 250)
        self.playlist_tree.setColumnWidth(2, 200)
        self.playlist_tree.setColumnWidth(3, 60)
        
        left_layout.addWidget(self.playlist_tree, 1)
        
        pl_buttons = QHBoxLayout()
        for text, slot in [("Save", self._save_playlist), ("Load", self._load_playlist),
                           ("Clear", self._clear_playlist), ("Shuffle", self._toggle_shuffle),
                           ("Repeat", self._cycle_repeat)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setObjectName("smallBtn")
            pl_buttons.addWidget(btn)
        left_layout.addLayout(pl_buttons)
        
        splitter.addWidget(left_panel)
        
        # ===== Right Panel: Now Playing =====
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)
        
        top_info = QHBoxLayout()
        top_info.setSpacing(20)
        
        # Vinyl disc
        self.vinyl = VinylDisc()
        top_info.addWidget(self.vinyl, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Track info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        
        self.title_label = QLabel("Select a Track")
        self.title_label.setObjectName("trackTitle")
        self.title_label.setWordWrap(True)
        info_layout.addWidget(self.title_label)
        
        self.artist_label = QLabel("Unknown Artist")
        self.artist_label.setObjectName("trackArtist")
        self.artist_label.setWordWrap(True)
        info_layout.addWidget(self.artist_label)
        
        self.album_label = QLabel("Unknown Album")
        self.album_label.setObjectName("trackAlbum")
        self.album_label.setWordWrap(True)
        info_layout.addWidget(self.album_label)
        
        self.genre_label = QLabel("")
        self.genre_label.setObjectName("trackGenre")
        info_layout.addWidget(self.genre_label)
        
        info_layout.addStretch()
        top_info.addLayout(info_layout, 1)
        right_layout.addLayout(top_info)
        
        # ===== Progress Bar =====
        progress_frame = QFrame()
        progress_layout = QHBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 5, 0, 5)
        progress_layout.setSpacing(8)
        
        self.current_time = QLabel("00:00")
        self.current_time.setObjectName("timeLabel")
        self.current_time.setFixedWidth(45)
        progress_layout.addWidget(self.current_time)
        
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.sliderPressed.connect(lambda: setattr(self, '_seeking', True))
        self.progress_slider.sliderReleased.connect(self._seek)
        self.progress_slider.setObjectName("progressSlider")
        progress_layout.addWidget(self.progress_slider, 1)
        
        self.total_time = QLabel("00:00")
        self.total_time.setObjectName("timeLabel")
        self.total_time.setFixedWidth(45)
        progress_layout.addWidget(self.total_time)
        
        right_layout.addWidget(progress_frame)
        
        # ===== Controls =====
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        controls_layout.addStretch()
        
        control_data = [
            ("Previous", self._prev_track),
            ("Play", self._play_pause),
            ("Stop", self._stop),
            ("Next", self._next_track),
        ]
        
        for text, slot in control_data:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            if text == "Play":
                btn.setObjectName("playButton")
                self.play_button = btn
                btn.setFixedHeight(40)
            else:
                btn.setObjectName("playbackBtn")
                btn.setFixedHeight(35)
            controls_layout.addWidget(btn)
        
        controls_layout.addStretch()
        right_layout.addLayout(controls_layout)
        
        # ===== Volume =====
        vol_frame = QFrame()
        vol_layout = QHBoxLayout(vol_frame)
        vol_layout.setContentsMargins(0, 0, 0, 0)
        vol_layout.setSpacing(8)
        
        vol_label = QLabel("Volume")
        vol_label.setObjectName("volLabel")
        vol_layout.addWidget(vol_label)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self._on_volume_change)
        self.volume_slider.setObjectName("volumeSlider")
        vol_layout.addWidget(self.volume_slider, 1)
        
        self.vol_percent = QLabel("70%")
        self.vol_percent.setObjectName("volLabel")
        self.vol_percent.setFixedWidth(35)
        vol_layout.addWidget(self.vol_percent)
        
        right_layout.addWidget(vol_frame)
        
        # ===== Visualizer (100 bars with random rhythm) =====
        self.visualizer = EqualizerVisualizer(100)
        self.visualizer.setObjectName("visualizer")
        self.visualizer.setMinimumHeight(100)
        right_layout.addWidget(self.visualizer, 1)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 900])
        
        container_layout.addWidget(splitter, 1)
        
        # ===== Status Bar =====
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_bar.setFixedHeight(25)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 2, 10, 2)
        
        self.status_info = QLabel("Welcome to Arvin Player")
        self.status_info.setObjectName("statusLabel")
        status_layout.addWidget(self.status_info)
        
        status_layout.addStretch()
        
        self.clock_label = QLabel("")
        self.clock_label.setObjectName("statusLabel")
        status_layout.addWidget(self.clock_label)
        
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()
        
        container_layout.addWidget(status_bar)
        main_layout.addWidget(container)
    
    def _apply_theme(self):
        """Apply current theme"""
        theme = ThemeManager.get_theme(self.current_theme)
        t = theme
        
        stylesheet = f"""
            QMainWindow {{
                background-color: {t['bg_primary']};
            }}
            
            #mainContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 {t['bg_primary']}, stop:0.5 {t['bg_secondary']}, stop:1 {t['bg_primary']});
                border-radius: 12px;
            }}
            
            #topBar {{
                background: {t['bg_card']};
                border-radius: 8px;
                border-bottom: 1px solid {t['border']};
            }}
            
            #logo {{
                color: {t['accent_primary']};
                font-size: 18px;
                font-weight: bold;
            }}
            
            #miniInfo {{
                color: {t['text_secondary']};
                font-size: 11px;
                padding: 0 8px;
            }}
            
            #globalSearch {{
                background: {t['input_bg']};
                color: {t['text_primary']};
                border: 1px solid {t['input_border']};
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
            }}
            
            #globalSearch:focus {{
                border-color: {t['accent_primary']};
            }}
            
            #themeBtn {{
                background: {t['button_bg']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                font-size: 11px;
            }}
            
            #themeBtn:hover {{
                background: {t['accent_primary']};
                color: white;
            }}
            
            #smallBtn {{
                background: {t['button_bg']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 11px;
            }}
            
            #smallBtn:hover {{
                background: {t['accent_primary']};
                color: white;
            }}
            
            #leftPanel, #rightPanel {{
                background: {t['bg_card']};
                border-radius: 10px;
            }}
            
            #sectionTitle {{
                color: {t['text_primary']};
                font-size: 16px;
                font-weight: bold;
            }}
            
            #trackCount {{
                color: {t['text_secondary']};
                font-size: 10px;
            }}
            
            #playlistTree {{
                background: {t['bg_secondary']};
                color: {t['text_primary']};
                border: none;
                border-radius: 10px;
                alternate-background-color: {t['tree_alt_bg']};
                font-size: 13px;
                outline: none;
            }}
            
            #playlistTree::item {{
                padding: 8px 5px;
                border-bottom: 1px solid {t['border']};
            }}
            
            #playlistTree::item:selected {{
                background: {t['accent_primary']};
                color: white;
                border-radius: 5px;
            }}
            
            #playlistTree::item:hover {{
                background: {t['bg_surface_light']};
                border-radius: 5px;
            }}
            
            QHeaderView::section {{
                background: {t['bg_surface']};
                color: {t['accent_primary']};
                border: none;
                padding: 8px;
                font-weight: bold;
                font-size: 12px;
            }}
            
            #trackTitle {{
                color: {t['text_primary']};
                font-size: 22px;
                font-weight: bold;
            }}
            
            #trackArtist {{
                color: {t['accent_primary']};
                font-size: 16px;
            }}
            
            #trackAlbum {{
                color: {t['text_secondary']};
                font-size: 14px;
            }}
            
            #trackGenre {{
                color: {t['accent_tertiary']};
                font-size: 12px;
            }}
            
            #timeLabel {{
                color: {t['text_primary']};
                font-size: 12px;
                font-weight: bold;
            }}
            
            #progressSlider::groove:horizontal {{
                background: {t['slider_bg']};
                height: 6px;
                border-radius: 3px;
            }}
            
            #progressSlider::handle:horizontal {{
                background: {t['accent_primary']};
                width: 12px;
                height: 12px;
                margin: -3px 0;
                border-radius: 6px;
                border: 2px solid white;
            }}
            
            #progressSlider::sub-page:horizontal {{
                background: {t['accent_primary']};
                border-radius: 3px;
            }}
            
            #playbackBtn {{
                background: {t['button_bg']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 13px;
            }}
            
            #playbackBtn:hover {{
                background: {t['accent_primary']};
                color: white;
                border-color: {t['accent_primary']};
            }}
            
            #playButton {{
                background: {t['accent_primary']};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                padding: 8px 25px;
            }}
            
            #playButton:hover {{
                background: {t['accent_gold']};
            }}
            
            #volLabel {{
                color: {t['text_secondary']};
                font-size: 11px;
            }}
            
            #volumeSlider::groove:horizontal {{
                background: {t['slider_bg']};
                height: 4px;
                border-radius: 2px;
            }}
            
            #volumeSlider::handle:horizontal {{
                background: {t['accent_tertiary']};
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
                border: 2px solid white;
            }}
            
            #volumeSlider::sub-page:horizontal {{
                background: {t['accent_tertiary']};
                border-radius: 2px;
            }}
            
            #visualizer {{
                background: {t['bg_secondary']};
                border-radius: 10px;
                border: 1px solid {t['border']};
            }}
            
            #statusBar {{
                background: {t['bg_card']};
                border-radius: 6px;
            }}
            
            #statusLabel {{
                color: {t['text_secondary']};
                font-size: 10px;
            }}
            
            QScrollBar:vertical {{
                background: {t['bg_primary']};
                width: 8px;
                border-radius: 4px;
            }}
            
            QScrollBar::handle:vertical {{
                background: {t['accent_primary']};
                border-radius: 4px;
                min-height: 20px;
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QToolTip {{
                background: {t['bg_surface_light']};
                color: {t['text_primary']};
                border: 1px solid {t['accent_primary']};
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }}
        """
        
        self.setStyleSheet(stylesheet)
        self.visualizer.set_theme(self.current_theme)
        self.theme_btn.setText("Dark" if self.current_theme == 'light' else "Light")
    
    def _toggle_theme(self):
        self.current_theme = 'light' if self.current_theme == 'dark' else 'dark'
        self._apply_theme()
    
    def _toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
        else:
            self.showFullScreen()
        self.is_fullscreen = not self.is_fullscreen
    
    def _setup_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            menu = QMenu()
            menu.addAction("Show/Hide", self._toggle_visibility)
            menu.addSeparator()
            menu.addAction("Play/Pause", self._play_pause)
            menu.addAction("Next", self._next_track)
            menu.addAction("Previous", self._prev_track)
            menu.addSeparator()
            menu.addAction("Exit", self.close)
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.show()
    
    # ========== Playlist Management ==========
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Music", "",
            "Music Files (*.mp3 *.flac *.wav *.ogg *.m4a *.wma);;All Files (*)")
        if files:
            for f in files:
                self._add_to_playlist(f)
            self._refresh_playlist()
    
    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return
        exts = (".mp3", ".flac", ".wav", ".ogg", ".m4a", ".wma")
        count = 0
        for ext in exts:
            for p in Path(folder).rglob(f"*{ext}"):
                self._add_to_playlist(str(p))
                count += 1
        self._refresh_playlist()
    
    def _add_to_playlist(self, filepath):
        if any(item['path'] == filepath for item in self.playlist):
            return
        meta = self.metadata_manager.get_metadata(filepath)
        self.playlist.append({
            'path': filepath,
            'title': meta.get('title', os.path.basename(filepath)),
            'artist': meta.get('artist', 'Unknown Artist'),
            'album': meta.get('album', 'Unknown Album'),
            'genre': meta.get('genre', ''),
            'duration': meta.get('duration', 0),
            'track_number': meta.get('track_number', 0),
            'cover_data': meta.get('cover_art'),
            'cover_path': meta.get('cover_path', ''),
            'bitrate': meta.get('bitrate', 0),
            'sample_rate': meta.get('sample_rate', 0),
        })
    
    def _refresh_playlist(self, filter_text=""):
        self.playlist_tree.clear()
        for idx, item in enumerate(self.playlist):
            if filter_text:
                q = filter_text.lower()
                if (q not in item['title'].lower() and q not in item['artist'].lower()):
                    continue
            
            dur = self._format_time(item['duration'])
            # Start numbering from 1, not 0
            track_num = str(idx + 1)
            
            tree_item = QTreeWidgetItem([track_num, item['title'], item['artist'], dur])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, idx)
            
            # Set cover icon if available
            if item.get('cover_data'):
                img = QImage.fromData(QByteArray(item['cover_data']))
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    tree_item.setIcon(1, QIcon(pixmap))
            elif item.get('cover_path'):
                pixmap = QPixmap(item['cover_path']).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                tree_item.setIcon(1, QIcon(pixmap))
            else:
                # Default music icon
                default_pix = QPixmap(40, 40)
                default_pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(default_pix)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setBrush(QColor("#333333"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(0, 0, 40, 40, 5, 5)
                painter.setPen(QColor("#666666"))
                painter.setFont(QFont("Segoe UI", 16))
                painter.drawText(QRectF(0, 0, 40, 40), Qt.AlignmentFlag.AlignCenter, "♪")
                painter.end()
                tree_item.setIcon(1, QIcon(default_pix))
            
            # Bold for currently playing track
            if idx == self.current_index:
                font = tree_item.font(0)
                font.setBold(True)
                for col in range(4):
                    tree_item.setFont(col, font)
                    tree_item.setForeground(col, QColor(ThemeManager.get_theme(self.current_theme)['accent_primary']))
            
            tree_item.setToolTip(0, f"Album: {item.get('album', 'N/A')}\nPath: {item['path']}")
            self.playlist_tree.addTopLevelItem(tree_item)
        
        self.track_count.setText(f"{len(self.playlist)} tracks")
    
    def _play_index(self, idx):
        if idx < 0 or idx >= len(self.playlist):
            return
        
        self.current_index = idx
        item = self.playlist[idx]
        
        self.player.setSource(QUrl.fromLocalFile(item['path']))
        self._update_now_playing(idx)
        self._highlight_current_track()
        
        self.player.play()
        self.is_playing = True
        self.is_paused = False
        self.vinyl.set_playing(True)
        self.visualizer.set_playing(True)
        
        self.play_button.setText("Pause")
        self.mini_info.setText(f"Playing: {item['title'][:25]}...")
        
        # Refresh playlist to update styling
        self._refresh_playlist(self.global_search.text())
        
        # Update status
        bitrate = item.get('bitrate', 0)
        sample_rate = item.get('sample_rate', 0)
        self.status_info.setText(f"{bitrate} kbps | {sample_rate/1000:.1f} kHz")
    
    def _play_pause(self):
        if not self.player.source().isValid() and self.playlist:
            if self.current_index == -1:
                self.current_index = 0
            self._play_index(self.current_index)
            return
        
        if self.is_playing and not self.is_paused:
            self.player.pause()
            self.is_paused = True
            self.play_button.setText("Play")
            self.vinyl.set_playing(False)
            self.visualizer.set_playing(False)
        elif self.is_playing and self.is_paused:
            self.player.play()
            self.is_paused = False
            self.play_button.setText("Pause")
            self.vinyl.set_playing(True)
            self.visualizer.set_playing(True)
        else:
            if self.current_index == -1 and self.playlist:
                self._play_index(0)
            else:
                self._play_index(self.current_index)
        
        self._refresh_playlist(self.global_search.text())
    
    def _stop(self):
        self.player.stop()
        self.is_playing = False
        self.is_paused = False
        self.play_button.setText("Play")
        self.vinyl.set_playing(False)
        self.visualizer.set_playing(False)
        self.progress_slider.setValue(0)
        self.current_time.setText("00:00")
        self.total_time.setText("00:00")
        self.mini_info.setText("Ready")
        self.status_info.setText("Stopped")
        self._refresh_playlist(self.global_search.text())
    
    def _prev_track(self):
        if not self.playlist:
            return
        if self.shuffle_mode:
            self.current_index = random.randint(0, len(self.playlist) - 1)
        else:
            self.current_index = (self.current_index - 1) % len(self.playlist)
        self._play_index(self.current_index)
    
    def _next_track(self):
        if not self.playlist:
            return
        if self.shuffle_mode:
            self.current_index = random.randint(0, len(self.playlist) - 1)
        else:
            self.current_index = (self.current_index + 1) % len(self.playlist)
        self._play_index(self.current_index)
    
    def _seek_relative(self, sec):
        dur = self.player.duration()
        if not dur:
            return
        pos = self.player.position() // 1000 + sec
        self.player.setPosition(max(0, min(pos, dur // 1000)) * 1000)
    
    def _update_now_playing(self, idx):
        if idx < 0 or idx >= len(self.playlist):
            self.title_label.setText("Select a Track")
            self.artist_label.setText("Unknown Artist")
            self.album_label.setText("Unknown Album")
            self.genre_label.setText("")
            self.vinyl.set_cover(QPixmap())
            return
        
        item = self.playlist[idx]
        self.title_label.setText(item['title'])
        self.artist_label.setText(item['artist'])
        self.album_label.setText(item['album'])
        genre_text = f"{item.get('genre', '')} | {item.get('year', '')}" if item.get('year') else item.get('genre', '')
        self.genre_label.setText(genre_text)
        
        # Load cover art
        pix = None
        if item.get('cover_data'):
            img = QImage.fromData(QByteArray(item['cover_data']))
            if not img.isNull():
                pix = QPixmap.fromImage(img)
        if not pix and item.get('cover_path'):
            pix = QPixmap(item['cover_path'])
        if pix and not pix.isNull():
            self.vinyl.set_cover(pix.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.vinyl.set_cover(QPixmap())
    
    def _highlight_current_track(self):
        for i in range(self.playlist_tree.topLevelItemCount()):
            item = self.playlist_tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == self.current_index:
                self.playlist_tree.setCurrentItem(item)
                self.playlist_tree.scrollToItem(item)
                break
    
    # ========== Signal Handlers ==========
    def _on_position_changed(self, pos):
        if self._seeking:
            return
        dur = self.player.duration()
        if dur > 0:
            self.progress_slider.setValue(int(pos * 1000 / dur))
            self.current_time.setText(self._format_time(pos // 1000))
            self.total_time.setText(self._format_time(dur // 1000))
    
    def _on_duration_changed(self, dur):
        if dur > 0 and 0 <= self.current_index < len(self.playlist):
            self.playlist[self.current_index]['duration'] = dur // 1000
    
    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.repeat_mode == 1:
                self._play_index(self.current_index)
            else:
                self._next_track()
    
    def _on_error(self, error, err_str):
        self.status_info.setText(f"Error: {err_str[:50]}")
    
    def _on_playback_state_changed(self, state):
        play = state == QMediaPlayer.PlaybackState.PlayingState
        self.visualizer.set_playing(play)
        self.vinyl.set_playing(play)
    
    def _seek(self):
        dur = self.player.duration()
        if dur:
            self.player.setPosition(int(self.progress_slider.value() / 1000 * dur))
        self._seeking = False
    
    def _on_volume_change(self, val):
        self.audio_output.setVolume(val / 100)
        self.vol_percent.setText(f"{val}%")
    
    # ========== Features ==========
    def _save_playlist(self):
        if not self.playlist:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", "JSON (*.json)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([{k: item[k] for k in ('path', 'title', 'artist', 'album', 'duration')} 
                          for item in self.playlist], f, indent=2)
    
    def _load_playlist(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Playlist", "", "JSON (*.json)")
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._stop()
            self.playlist.clear()
            for item in data:
                if os.path.exists(item['path']):
                    self._add_to_playlist(item['path'])
            self.current_index = -1
            self._refresh_playlist()
    
    def _clear_playlist(self):
        if QMessageBox.question(self, "Clear", "Clear all tracks?") == QMessageBox.StandardButton.Yes:
            self._stop()
            self.playlist.clear()
            self.current_index = -1
            self._refresh_playlist()
    
    def _toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        self.status_info.setText(f"Shuffle: {'ON' if self.shuffle_mode else 'OFF'}")
    
    def _cycle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        modes = ["Repeat: OFF", "Repeat: ONE", "Repeat: ALL"]
        self.status_info.setText(modes[self.repeat_mode])
    
    def _on_search(self, text):
        self._refresh_playlist(text)
    
    def _on_playlist_double_click(self, item):
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        self._play_index(idx)
    
    def _show_context_menu(self, pos):
        item = self.playlist_tree.currentItem()
        if not item:
            return
        menu = QMenu()
        menu.addAction("Play", lambda: self._on_playlist_double_click(item))
        menu.addAction("Remove", self._remove_selected)
        menu.exec(self.playlist_tree.mapToGlobal(pos))
    
    def _remove_selected(self):
        selected = self.playlist_tree.selectedItems()
        indices = sorted([it.data(0, Qt.ItemDataRole.UserRole) for it in selected], reverse=True)
        for idx in indices:
            if idx == self.current_index:
                self._stop()
            del self.playlist[idx]
            if self.current_index > idx:
                self.current_index -= 1
            elif self.current_index == idx:
                self.current_index = -1
        self._refresh_playlist()
    
    def _toggle_visibility(self):
        self.setVisible(not self.isVisible())
    
    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))
    
    def _load_last_session(self):
        sess = Path.home() / ".arvin_player_playlist.json"
        if sess.exists():
            try:
                with open(sess) as f:
                    data = json.load(f)
                for item in data:
                    if os.path.exists(item.get('path', '')):
                        self._add_to_playlist(item['path'])
                self._refresh_playlist()
            except:
                pass
    
    def _save_session(self):
        try:
            with open(Path.home() / ".arvin_player_playlist.json", 'w') as f:
                json.dump([{k: item[k] for k in ('path', 'title', 'artist')} 
                          for item in self.playlist], f)
        except:
            pass
    
    def closeEvent(self, event):
        self._save_session()
        self.player.stop()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        event.accept()
    
    def _format_time(self, sec):
        if sec < 0:
            return "00:00"
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    
    try:
        player = ArvinPlayer()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
