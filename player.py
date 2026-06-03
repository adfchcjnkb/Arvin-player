"""
Arvin Player - Main Player Class
"""

import sys
import os
import json
import random
from pathlib import Path
from datetime import datetime
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QSize, QByteArray, QPropertyAnimation,
    QEasingCurve, QRectF
)
from PyQt6.QtGui import (
    QAction, QPainter, QColor, QBrush, QPen, QFont, QPixmap, QImage,
    QIcon, QLinearGradient, QPainterPath, QRadialGradient,
    QKeySequence, QShortcut
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QListWidget, QListWidgetItem,
    QStackedWidget, QSizePolicy, QFileDialog, QMessageBox, QMenu,
    QLineEdit, QFrame, QSplitter, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QProgressBar, QScrollArea, QToolButton,
    QStyle, QSystemTrayIcon, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QAbstractItemView
)

# Try to import QMediaPlayer components
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    MULTIMEDIA_OK = True
except ImportError:
    MULTIMEDIA_OK = False
    print("Warning: PyQt6 Multimedia not available")

from utils import APP_TITLE, APP_VERSION, format_time, resource_path
from core import ThemeManager, MetadataManager
from widgets import VinylDisc, EqualizerVisualizer, TreeItemDelegate


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
        self.setMinimumSize(680, 270)
        
        # Set window icon
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # State
        self.current_theme = 'dark'
        self.playlist = []
        self.current_index = -1
        self.is_playing = False
        self.is_paused = False
        self.repeat_mode = 0
        self.shuffle_mode = False
        self._seeking = False
        self.is_fullscreen = False
        self.playlist_visible = True
        
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
        self.shortcut_delete = QShortcut(QKeySequence("Delete"), self)
        self.shortcut_delete.activated.connect(self._remove_selected)
        self.shortcut_playlist = QShortcut(QKeySequence("Ctrl+L"), self)
        self.shortcut_playlist.activated.connect(self._toggle_playlist)
    
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
        top_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 4, 12, 4)
        top_layout.setSpacing(6)
        
        self.playlist_toggle_btn = QPushButton("Hide List")
        self.playlist_toggle_btn.setObjectName("smallBtn")
        self.playlist_toggle_btn.setFixedWidth(70)
        self.playlist_toggle_btn.clicked.connect(self._toggle_playlist)
        top_layout.addWidget(self.playlist_toggle_btn)
        
        logo = QLabel("ARVIN PLAYER")
        logo.setObjectName("logo")
        logo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        top_layout.addWidget(logo)
        top_layout.addStretch()
        
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("Search...")
        self.global_search.setObjectName("globalSearch")
        self.global_search.setMinimumWidth(100)
        self.global_search.setMaximumWidth(250)
        self.global_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.global_search.textChanged.connect(self._on_search)
        top_layout.addWidget(self.global_search)
        
        self.theme_btn = QPushButton("Light")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setFixedSize(70, 28)
        self.theme_btn.clicked.connect(self._toggle_theme)
        top_layout.addWidget(self.theme_btn)
        
        self.mini_info = QLabel("Ready")
        self.mini_info.setObjectName("miniInfo")
        self.mini_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.mini_info.setMinimumWidth(50)
        top_layout.addWidget(self.mini_info)
        
        container_layout.addWidget(top_bar)
        
        # ===== Main Splitter =====
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setChildrenCollapsible(True)
        
        # ===== Left Panel: Playlist =====
        self.left_panel = QFrame()
        self.left_panel.setObjectName("leftPanel")
        self.left_panel.setMinimumWidth(220)
        left_layout = QVBoxLayout(self.left_panel)
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
        
        # Playlist tree: #, Title, Time, Actions
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderLabels(["#", "Title", "Time", ""])
        self.playlist_tree.setRootIsDecorated(False)
        self.playlist_tree.setAlternatingRowColors(True)
        self.playlist_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.playlist_tree.itemDoubleClicked.connect(self._on_playlist_double_click)
        self.playlist_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.playlist_tree.setObjectName("playlistTree")
        self.playlist_tree.setIconSize(QSize(40, 40))
        
        self.tree_delegate = TreeItemDelegate()
        self.playlist_tree.setItemDelegate(self.tree_delegate)
        
        self.playlist_tree.setColumnWidth(0, 35)
        self.playlist_tree.setColumnWidth(2, 60)
        self.playlist_tree.setColumnWidth(3, 35)
        self.playlist_tree.header().setStretchLastSection(False)
        self.playlist_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
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
        
        self.splitter.addWidget(self.left_panel)
        
        # ===== Right Panel: Now Playing =====
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_panel.setMinimumWidth(350)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)
        
        top_info = QHBoxLayout()
        top_info.setSpacing(20)
        
        # Vinyl disc
        self.vinyl = VinylDisc()
        self.vinyl.setFixedSize(220, 220)
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
        
        # ===== Visualizer =====
        self.visualizer = EqualizerVisualizer(100)
        self.visualizer.setObjectName("visualizer")
        self.visualizer.setMinimumHeight(100)
        right_layout.addWidget(self.visualizer, 1)
        
        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([400, 900])
        
        container_layout.addWidget(self.splitter, 1)
        
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
        
        # Handle click on actions column
        self.playlist_tree.itemClicked.connect(self._on_item_clicked)
    
    def _toggle_playlist(self):
        """Show/hide playlist panel"""
        self.playlist_visible = not self.playlist_visible
        self.left_panel.setVisible(self.playlist_visible)
        self.playlist_toggle_btn.setText("Hide List" if self.playlist_visible else "Show List")
    
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
                padding: 4px 10px;
                font-size: 11px;
                min-width: 100px;
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
            
            QScrollBar:horizontal {{
                background: {t['bg_primary']};
                height: 8px;
                border-radius: 4px;
            }}
            
            QScrollBar::handle:horizontal {{
                background: {t['accent_primary']};
                border-radius: 4px;
                min-width: 20px;
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                height: 0px;
                width: 0px;
            }}
            
            QToolTip {{
                background: {t['bg_surface_light']};
                color: {t['text_primary']};
                border: 1px solid {t['accent_primary']};
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }}
            
            QSplitter::handle {{
                background: {t['border']};
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
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
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
            
            dur = format_time(item['duration'])
            track_num = str(idx + 1)
            
            tree_item = QTreeWidgetItem([track_num, item['title'], dur, ""])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, idx)
            
            if item.get('cover_data'):
                img = QImage.fromData(QByteArray(item['cover_data']))
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    tree_item.setIcon(1, QIcon(pixmap))
            elif item.get('cover_path'):
                pixmap = QPixmap(item['cover_path']).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                tree_item.setIcon(1, QIcon(pixmap))
            else:
                default_pix = QPixmap(40, 40)
                default_pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(default_pix)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setBrush(QColor("#333333"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(0, 0, 40, 40, 5, 5)
                painter.setPen(QColor("#666666"))
                painter.setFont(QFont("Vazir", 16))
                painter.drawText(QRectF(0, 0, 40, 40), Qt.AlignmentFlag.AlignCenter, "♪")
                painter.end()
                tree_item.setIcon(1, QIcon(default_pix))
            
            if idx == self.current_index:
                font = tree_item.font(0)
                font.setBold(True)
                for col in range(4):
                    tree_item.setFont(col, font)
                    tree_item.setForeground(col, QColor(ThemeManager.get_theme(self.current_theme)['accent_primary']))
            
            tree_item.setToolTip(0, f"Title: {item['title']}\nArtist: {item.get('artist', 'N/A')}\nAlbum: {item.get('album', 'N/A')}\nPath: {item['path']}")
            self.playlist_tree.addTopLevelItem(tree_item)
        
        self.track_count.setText(f"{len(self.playlist)} tracks")
    
    def _on_item_clicked(self, item, column):
        if column == 3:
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            self._show_delete_menu(item, idx)
    
    def _show_delete_menu(self, item, idx):
        menu = QMenu(self)
        delete_action = menu.addAction("Remove from Playlist")
        
        theme = ThemeManager.get_theme(self.current_theme)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {theme['bg_card']};
                color: {theme['text_primary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 8px 20px;
                border-radius: 5px;
            }}
            QMenu::item:selected {{
                background: {theme['accent_secondary']};
                color: white;
            }}
        """)
        
        action = menu.exec(self.playlist_tree.mapToGlobal(
            self.playlist_tree.visualItemRect(item).topRight()))
        
        if action == delete_action:
            self._remove_single(idx)
    
    def _remove_single(self, idx):
        if idx == self.current_index:
            self._stop()
        del self.playlist[idx]
        if self.current_index > idx:
            self.current_index -= 1
        elif self.current_index == idx:
            self.current_index = -1
        self._refresh_playlist(self.global_search.text())
        self.status_info.setText("Track removed")
    
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
        
        self._refresh_playlist(self.global_search.text())
        
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
        
        pix = None
        if item.get('cover_data'):
            img = QImage.fromData(QByteArray(item['cover_data']))
            if not img.isNull():
                pix = QPixmap.fromImage(img)
        if not pix and item.get('cover_path'):
            pix = QPixmap(item['cover_path'])
        if pix and not pix.isNull():
            self.vinyl.set_cover(pix)
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
            self.current_time.setText(format_time(pos // 1000))
            self.total_time.setText(format_time(dur // 1000))
    
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
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu()
        menu.addAction("Play", lambda: self._on_playlist_double_click(item))
        menu.addAction("Remove", lambda: self._remove_single(idx))
        menu.exec(self.playlist_tree.mapToGlobal(pos))
    
    def _remove_selected(self):
        selected = self.playlist_tree.selectedItems()
        if not selected:
            return
        indices = sorted([it.data(0, Qt.ItemDataRole.UserRole) for it in selected], reverse=True)
        for idx in indices:
            if idx == self.current_index:
                self._stop()
            del self.playlist[idx]
            if self.current_index > idx:
                self.current_index -= 1
            elif self.current_index == idx:
                self.current_index = -1
        self._refresh_playlist(self.global_search.text())
    
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