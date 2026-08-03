
import sys
import os
import json
import random
import logging
import functools
import numpy as np
from pathlib import Path
from datetime import datetime
from PyQt6.QtCore import (
    Qt, QTimer, QUrl, QSize, QByteArray, QPropertyAnimation,
    QEasingCurve, QRectF, QCollator, QLocale, QStandardPaths
)
from PyQt6.QtGui import (
    QAction, QPainter, QColor, QBrush, QPen, QFont, QPixmap, QImage,
    QIcon, QLinearGradient, QPainterPath, QRadialGradient,
    QKeySequence, QShortcut, QFontDatabase
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QListWidget, QListWidgetItem,
    QStackedWidget, QSizePolicy, QFileDialog, QMessageBox, QMenu,
    QLineEdit, QFrame, QSplitter, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QProgressBar, QScrollArea, QToolButton,
    QStyle, QSystemTrayIcon, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QApplication, QDialog,
    QCheckBox, QFormLayout, QGridLayout, QSpinBox, QDialogButtonBox
)
from PyQt6.QtSvg import QSvgRenderer

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioBufferOutput, QAudioFormat
    MULTIMEDIA_OK = True
except ImportError:
    MULTIMEDIA_OK = False
    print("Warning: PyQt6 Multimedia not available")

from app.utils import (
    APP_TITLE, APP_VERSION, format_time, resource_path, find_font_file,
    load_settings, save_settings, write_json_atomic, SESSION_PATH,
    AUDIO_EXTENSIONS, PLAYLIST_EXTENSIONS, audio_name_filter, safe_mtime,
)
from app.core import ThemeManager, MetadataManager
from app.ui.widgets import (
    VinylDisc, EqualizerVisualizer, TreeItemDelegate, ElidingLabel, StayOpenMenu,
    SeekSlider,
)
from app.i18n import LANGUAGES, LANGUAGE_ORDER, DEFAULT_LANGUAGE_FALLBACK, tr
from app.ui.help_dialog import HelpDialog
from app.ui.metadata_editor import MetadataEditorDialog
from app.audio.eq_engine import EqualizerEngine, FACTORY_PRESETS, BAND_CENTERS
from app.audio.sink import RealtimeEqAudioSink
from app.audio.devices import AudioDeviceManager, SYSTEM_DEFAULT
from app.features import ExtraFeatureMixin, FeatureMixin
from app import themes
from app.ui import icons
from app import playlists

log = logging.getLogger("parch_mp.player")

_LEGACY_SESSION_PATH = Path.home() / ".arvin_player_playlist.json"


class ParchPlayer(ExtraFeatureMixin, FeatureMixin, QMainWindow):
    
    def __init__(self):
        super().__init__()
        
        if not MULTIMEDIA_OK:
            QMessageBox.critical(self, "Error", 
                "PyQt6 Multimedia not available!\n\nInstall with:\npip install PyQt6-Qt6==6.5.0")
            sys.exit(1)
        
        themes.install()
        self.settings = load_settings()
        self.current_language = self.settings.get("language", DEFAULT_LANGUAGE_FALLBACK)
        if self.current_language not in LANGUAGES:
            self.current_language = DEFAULT_LANGUAGE_FALLBACK
        self._loaded_fonts = {}
        self._default_track_icon = None
        QApplication.instance().setFont(self._get_font_for_language(self.current_language))
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if LANGUAGES[self.current_language]["rtl"]
            else Qt.LayoutDirection.LeftToRight
        )

        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        self.resize(1300, 800)
        self.setMinimumSize(340, 420)
        
        icon_path = resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.current_theme = self.settings.get("theme", "dark")
        self.playlist = []
        self._playlist_paths = set()
        self.current_index = -1
        self.is_playing = False
        self.is_paused = False
        self.repeat_mode = 0
        self.shuffle_mode = False
        self._seeking = False
        self.is_fullscreen = False
        self.playlist_visible = True
        self._sort_mode = None
        self._view_mode = "all"
        self._view_context = None
        self._view_rows = []
        self._add_counter = 0
        self._play_errors = 0
        self._failed_path = None
        self._cue_start = 0.0
        self._cue_end = None
        self._cue_seek_pending = False

        self.metadata_manager = MetadataManager()
        
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        self.audio_buffer_output = QAudioBufferOutput()
        self.player.setAudioBufferOutput(self.audio_buffer_output)
        self.audio_buffer_output.audioBufferReceived.connect(self._on_audio_buffer)

        self.eq_engine = EqualizerEngine(10, 44100.0)
        self.realtime_sink = RealtimeEqAudioSink(self.eq_engine, self)
        self.realtime_eq_enabled = bool(self.settings.get("realtime_eq", True))
        self._realtime_eq_format = None

        self.device_manager = AudioDeviceManager(self)
        self.device_manager.set_preferred_id(
            self.settings.get("audio_device", SYSTEM_DEFAULT))
        self.device_manager.active_changed.connect(self._on_audio_device_changed)
        self.device_manager.devices_changed.connect(self._on_audio_devices_listed)
        self.realtime_sink.stalled.connect(self._on_sink_stalled)
        self._apply_audio_device(self.device_manager.resolve())
        
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        
        self._setup_ui()
        self.progress_slider.setInvertedAppearance(False)
        self.volume_slider.setInvertedAppearance(False)
        self._apply_theme()
        self._retranslate_ui()
        self._restore_eq_engine_state()
        
        self._setup_shortcuts()
        
        self._setup_tray()
        
        self._load_last_session()

        self._init_features()
        self._init_extra_features()

        self.show()
        QTimer.singleShot(400, self._warm_up_style)

    def _warm_up_style(self):
        if getattr(self, "_style_warmed", False):
            return
        self._style_warmed = True
        self._repolish_fonts(self._get_font_for_language(self.current_language))

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
        
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(45)
        top_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 4, 12, 4)
        top_layout.setSpacing(6)
        
        self.playlist_toggle_btn = QPushButton("Hide List")
        self.playlist_toggle_btn.setObjectName("smallBtn")
        self.playlist_toggle_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.playlist_toggle_btn.setMinimumWidth(50)
        self.playlist_toggle_btn.clicked.connect(self._toggle_playlist)
        top_layout.addWidget(self.playlist_toggle_btn)
        
        self.logo = QLabel("PARCH MP")
        self.logo.setObjectName("logo")
        self.logo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        top_layout.addWidget(self.logo)
        top_layout.addStretch()
        
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("Search...")
        self.global_search.setObjectName("globalSearch")
        self.global_search.setMinimumWidth(60)
        self.global_search.setMaximumWidth(250)
        self.global_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.global_search.textChanged.connect(self._on_search)
        top_layout.addWidget(self.global_search)

        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("langCombo")
        self.lang_combo.setMinimumWidth(70)
        self.lang_combo.setMaximumWidth(160)
        self.lang_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for code in LANGUAGE_ORDER:
            self.lang_combo.addItem(LANGUAGES[code]["native"], code)
        for i in range(self.lang_combo.count()):
            code = self.lang_combo.itemData(i)
            self.lang_combo.setItemData(i, self._get_font_for_language(code), Qt.ItemDataRole.FontRole)
        idx = self.lang_combo.findData(self.current_language)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_selected)
        top_layout.addWidget(self.lang_combo)

        self.tools_btn = QPushButton()
        self.tools_btn.setObjectName("smallBtn")
        self.tools_btn.setFixedWidth(34)
        self.tools_btn.setIconSize(QSize(17, 17))
        self.tools_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tools_btn.clicked.connect(self._show_tools_menu)
        top_layout.addWidget(self.tools_btn)

        self.device_btn = QPushButton()
        self.device_btn.setObjectName("smallBtn")
        self.device_btn.setFixedWidth(34)
        self.device_btn.setIconSize(QSize(17, 17))
        self.device_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.device_btn.clicked.connect(self._show_device_menu)
        top_layout.addWidget(self.device_btn)

        self.eq_btn = QPushButton("EQ")
        self.eq_btn.setObjectName("smallBtn")
        self.eq_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.eq_btn.setMinimumWidth(36)
        self.eq_btn.clicked.connect(self._open_equalizer_dialog)
        top_layout.addWidget(self.eq_btn)

        self.help_btn = QPushButton("?")
        self.help_btn.setObjectName("smallBtn")
        self.help_btn.setFixedWidth(30)
        self.help_btn.clicked.connect(self._open_help)
        top_layout.addWidget(self.help_btn)
        
        self.theme_btn = QPushButton("Light")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.theme_btn.setMinimumWidth(50)
        self.theme_btn.setFixedHeight(28)
        self.theme_btn.clicked.connect(self._toggle_theme)
        top_layout.addWidget(self.theme_btn)
        
        self.mini_info = QLabel("Ready")
        self.mini_info.setObjectName("miniInfo")
        self.mini_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.mini_info.setMinimumWidth(50)
        top_layout.addWidget(self.mini_info)
        
        container_layout.addWidget(top_bar)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setChildrenCollapsible(True)
        
        self.left_panel = QFrame()
        self.left_panel.setObjectName("leftPanel")
        self.left_panel.setMinimumWidth(292)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        
        pl_header = QHBoxLayout()
        self.pl_title = QLabel("Playlist")
        self.pl_title.setObjectName("sectionTitle")
        pl_header.addWidget(self.pl_title)
        self.track_count = QLabel("0 tracks")
        self.track_count.setObjectName("trackCount")
        pl_header.addWidget(self.track_count)
        pl_header.addStretch()
        self._sort_btn = QPushButton("Sort")
        self._sort_btn.setObjectName("smallBtn")
        self._sort_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._sort_btn.clicked.connect(self._show_sort_menu)
        pl_header.addWidget(self._sort_btn)
        self._files_btn = QPushButton("+ Files")
        self._files_btn.clicked.connect(self._add_files)
        self._files_btn.setObjectName("smallBtn")
        pl_header.addWidget(self._files_btn)
        self._folder_btn = QPushButton("+ Folder")
        self._folder_btn.clicked.connect(self._add_folder)
        self._folder_btn.setObjectName("smallBtn")
        pl_header.addWidget(self._folder_btn)
        left_layout.addLayout(pl_header)

        view_bar = QHBoxLayout()
        view_bar.setSpacing(4)
        self._view_buttons = {}
        for key in ("all", "albums", "artists", "favourites"):
            btn = QPushButton()
            btn.setObjectName("viewTab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _c=False, k=key: self._set_view_mode(k))
            view_bar.addWidget(btn)
            self._view_buttons[key] = btn
        left_layout.addLayout(view_bar)

        self.crumb_bar = QWidget()
        crumb_layout = QHBoxLayout(self.crumb_bar)
        crumb_layout.setContentsMargins(0, 0, 0, 0)
        crumb_layout.setSpacing(6)
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("smallBtn")
        self.back_btn.setFixedWidth(34)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self._view_go_back)
        crumb_layout.addWidget(self.back_btn)
        self.crumb_label = ElidingLabel("")
        self.crumb_label.setObjectName("crumbLabel")
        crumb_layout.addWidget(self.crumb_label, 1)
        self.crumb_play_btn = QPushButton()
        self.crumb_play_btn.setObjectName("smallBtn")
        self.crumb_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.crumb_play_btn.clicked.connect(self._play_current_group)
        crumb_layout.addWidget(self.crumb_play_btn)
        self.crumb_bar.setVisible(False)
        left_layout.addWidget(self.crumb_bar)

        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderLabels(["#", "Title", "Time", "", ""])
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
        
        self.playlist_tree.header().setStretchLastSection(False)
        self.playlist_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.playlist_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.playlist_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.playlist_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.playlist_tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._update_playlist_column_widths()
        
        left_layout.addWidget(self.playlist_tree, 1)
        
        pl_buttons = QHBoxLayout()
        pl_buttons.setSpacing(4)
        self._pl_action_buttons = {}
        self._pl_action_icons = {"save": "save", "load": "folder_open", "clear": "trash",
                                 "shuffle": "shuffle", "repeat": "repeat"}
        for key, text, slot in [("save", "Save", self._save_playlist), ("load", "Load", self._load_playlist),
                                 ("clear", "Clear", self._clear_playlist), ("shuffle", "Shuffle", self._toggle_shuffle),
                                 ("repeat", "Repeat", self._cycle_repeat)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            btn.setObjectName("smallBtn")
            btn.setMinimumWidth(0)
            btn.setIconSize(QSize(15, 15))
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            pl_buttons.addWidget(btn)
            self._pl_action_buttons[key] = btn
        left_layout.addLayout(pl_buttons)
        
        self.splitter.addWidget(self.left_panel)
        
        right_panel = QFrame()
        self.right_panel = right_panel
        right_panel.setObjectName("rightPanel")
        right_panel.setMinimumWidth(180)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)
        
        self.vinyl = VinylDisc()

        self._info_box = QWidget()
        info_v = QVBoxLayout(self._info_box)
        info_v.setContentsMargins(0, 0, 0, 0)
        info_v.setSpacing(6)
        self.title_label = ElidingLabel("Select a Track")
        self.title_label.setObjectName("trackTitle")
        self.artist_label = ElidingLabel("Unknown Artist")
        self.artist_label.setObjectName("trackArtist")
        self.album_label = ElidingLabel("Unknown Album")
        self.album_label.setObjectName("trackAlbum")
        self.genre_label = ElidingLabel("")
        self.genre_label.setObjectName("trackGenre")
        self._info_labels = (self.title_label, self.artist_label,
                             self.album_label, self.genre_label)
        info_v.addStretch()
        for lb in self._info_labels:
            info_v.addWidget(lb)
        info_v.addStretch()

        self._np_header = QWidget()
        right_layout.addWidget(self._np_header, 3)
        self._relayout_now_playing(mobile=False)

        progress_frame = QFrame()
        progress_layout = QHBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 5, 0, 5)
        progress_layout.setSpacing(8)
        
        self.current_time = QLabel("00:00")
        self.current_time.setObjectName("timeLabel")
        self.current_time.setFixedWidth(45)
        progress_layout.addWidget(self.current_time)
        
        self.progress_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.progress_slider.sliderPressed.connect(lambda: setattr(self, '_seeking', True))
        self.progress_slider.sliderMoved.connect(self._on_slider_moved)
        self.progress_slider.sliderReleased.connect(self._seek)
        self.progress_slider.setObjectName("progressSlider")
        progress_layout.addWidget(self.progress_slider, 1)
        
        self.total_time = QLabel("00:00")
        self.total_time.setObjectName("timeLabel")
        self.total_time.setFixedWidth(45)
        progress_layout.addWidget(self.total_time)
        
        right_layout.addWidget(progress_frame)
        
        controls_widget = QWidget()
        controls_widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(20)
        controls_layout.addStretch()
        self._control_buttons = {}
        for key, slot, size, obj in [
            ("previous", self._prev_track, 50, "transportBtn"),
            ("play", self._play_pause, 66, "playPauseBtn"),
            ("next", self._next_track, 50, "transportBtn"),
        ]:
            btn = QPushButton()
            btn.setObjectName(obj)
            btn.setFixedSize(size, size)
            btn.setIconSize(QSize(int(size * 0.5), int(size * 0.5)))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            controls_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            self._control_buttons[key] = btn
        self.play_button = self._control_buttons["play"]
        controls_layout.addStretch()
        right_layout.addWidget(controls_widget)
        
        vol_frame = QFrame()
        vol_layout = QHBoxLayout(vol_frame)
        vol_layout.setContentsMargins(0, 0, 0, 0)
        vol_layout.setSpacing(8)
        
        self.vol_label = QLabel("Volume")
        self.vol_label.setObjectName("volLabel")
        vol_layout.addWidget(self.vol_label)
        
        initial_volume = int(self.settings.get("volume", 70))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(initial_volume)
        self.volume_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.volume_slider.valueChanged.connect(self._on_volume_change)
        self.volume_slider.setObjectName("volumeSlider")
        vol_layout.addWidget(self.volume_slider, 1)
        self.audio_output.setVolume(initial_volume / 100)
        self.realtime_sink.set_volume(initial_volume / 100)
        
        self.vol_percent = QLabel(f"{initial_volume}%")
        self.vol_percent.setObjectName("volLabel")
        self.vol_percent.setFixedWidth(35)
        vol_layout.addWidget(self.vol_percent)
        
        right_layout.addWidget(vol_frame)
        
        self.visualizer = EqualizerVisualizer(100)
        self.visualizer.setObjectName("visualizer")
        self.visualizer.setMinimumHeight(90)
        self.visualizer.set_rtl(LANGUAGES[self.current_language]["rtl"])
        right_layout.addWidget(self.visualizer, 3)

        self.eq_dialog = None

        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([400, 900])
        
        container_layout.addWidget(self.splitter, 1)
        
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_bar.setFixedHeight(25)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 2, 10, 2)
        
        self.status_info = QLabel("Welcome to Parch MP")
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
        
        self.playlist_tree.itemClicked.connect(self._on_item_clicked)
    
    def _update_playlist_column_widths(self):
        if not hasattr(self, "playlist_tree"):
            return
        fm = self.playlist_tree.fontMetrics()
        pad = 14
        longest = max((t.get("duration") or 0) for t in self.playlist) if self.playlist else 0
        sample = "00:00:00" if longest >= 3600 else "00:00"
        idx_w = max(28, fm.horizontalAdvance(str(max(1, len(self.playlist)))) + pad)
        time_w = max(58, fm.horizontalAdvance(sample) + 20)
        self.playlist_tree.setColumnWidth(0, idx_w)
        self.playlist_tree.setColumnWidth(2, time_w)
        self.playlist_tree.setColumnWidth(3, 30)
        self.playlist_tree.setColumnWidth(4, 38)

    def _refresh_list_chrome(self):
        self._list_narrow = None
        self._apply_list_density()
        self._paint_list_buttons()
        self._update_view_chrome()

    def _toggle_playlist(self):
        if getattr(self, "_compact", False):
            show_list = not self.left_panel.isVisible()
            self.left_panel.setVisible(show_list)
            self.right_panel.setVisible(not show_list)
        else:
            self.playlist_visible = not self.playlist_visible
            self.left_panel.setVisible(self.playlist_visible)
        self._sync_toggle_label()
        if self.left_panel.isVisible():
            self._balance_splitter()
            QTimer.singleShot(0, self._refresh_list_chrome)

    def _sync_toggle_label(self):
        key = "hide_list" if self.left_panel.isVisible() else "show_list"
        if getattr(self, "_compact", False):
            color = ThemeManager.get_theme(self.current_theme)["text_primary"]
            svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><g "
                   f"fill='{color}'><rect x='3' y='5' width='18' height='2.4' rx='1.2'/>"
                   "<rect x='3' y='11' width='18' height='2.4' rx='1.2'/>"
                   "<rect x='3' y='17' width='18' height='2.4' rx='1.2'/></g></svg>")
            self.playlist_toggle_btn.setText("")
            self.playlist_toggle_btn.setIcon(self._svg_icon(svg, 20))
            self.playlist_toggle_btn.setToolTip(tr(self.current_language, key))
        else:
            self.playlist_toggle_btn.setIcon(QIcon())
            self.playlist_toggle_btn.setText(tr(self.current_language, key))
            self.playlist_toggle_btn.setToolTip("")

    def _relayout_now_playing(self, mobile: bool):
        header = self._np_header
        old = header.layout()
        if old is not None:
            old.removeWidget(self.vinyl)
            old.removeWidget(self._info_box)
            QWidget().setLayout(old)
        self.vinyl.setParent(header)
        self._info_box.setParent(header)
        for lb in self._info_labels:
            lb.setAlignment(Qt.AlignmentFlag.AlignHCenter if mobile
                            else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        if mobile:
            lay = QVBoxLayout(header)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)
            lay.addWidget(self.vinyl, 1)
            lay.addWidget(self._info_box, 0)
        else:
            lay = QHBoxLayout(header)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(20)
            lay.addWidget(self.vinyl, 3)
            lay.addWidget(self._info_box, 4)
        self.vinyl.show()
        self._info_box.show()

    def _apply_responsive(self):
        self._apply_list_density()
        self._balance_splitter()
        self._sync_waveform_geometry()
        compact = self.width() < 640
        if compact == getattr(self, "_compact", None):
            return
        self._compact = compact
        self._relayout_now_playing(mobile=compact)
        self.logo.setVisible(not compact)
        self.mini_info.setVisible(not compact)
        if compact:
            self.left_panel.setVisible(False)
            self.right_panel.setVisible(True)
        else:
            self.left_panel.setVisible(self.playlist_visible)
            self.right_panel.setVisible(True)
        self._sync_toggle_label()

    def _list_panel_width(self):
        if hasattr(self, "splitter") and self.splitter.sizes():
            return self.splitter.sizes()[0] or self.left_panel.width()
        return self.left_panel.width()

    def _apply_list_density(self):
        if not hasattr(self, "_pl_action_buttons"):
            return
        if not self.left_panel.isVisible():
            return
        width = self._list_panel_width()
        if width <= 0:
            return
        previous = getattr(self, "_list_narrow", None)
        if previous is True:
            narrow = width < 392
        elif previous is False:
            narrow = width < 352
        else:
            narrow = width < 372
        if narrow == previous:
            return
        self._list_narrow = narrow
        self._paint_list_buttons()

    def _paint_list_buttons(self):
        if not hasattr(self, "_pl_action_buttons"):
            return
        narrow = bool(getattr(self, "_list_narrow", False))
        colour = ThemeManager.get_theme(self.current_theme)["text_primary"]
        labels = self._pl_action_labels()
        for key, btn in self._pl_action_buttons.items():
            name = self._pl_action_icons.get(key)
            btn.setIcon(icons.icon(name, 15, colour))
            btn.setText("" if narrow else labels.get(key, ""))
            btn.setToolTip(labels.get(key, ""))

    def _refresh_all_icons(self):
        colour = ThemeManager.get_theme(self.current_theme)["text_primary"]
        if hasattr(self, "_control_buttons"):
            self._update_transport_icons()
        self._paint_list_buttons()
        for name, attr in (("sort", "sort_btn"), ("plus", "add_files_btn"),
                           ("folder", "add_folder_btn")):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setIcon(icons.icon(name, 14, colour))
        if hasattr(self, "help_btn"):
            self.help_btn.setIcon(self._make_help_icon())
            self.help_btn.setText("")
        if hasattr(self, "tree_delegate"):
            th = ThemeManager.get_theme(self.current_theme)
            self.tree_delegate.set_palette(
                th["text_primary"], th["text_secondary"], th["accent_primary"],
                themes.is_light(self.current_theme))
        if hasattr(self, "playlist_tree"):
            self.playlist_tree.viewport().update()

    def _pl_action_labels(self):
        t = self.current_language
        return {"save": tr(t, "save"), "load": tr(t, "load"), "clear": tr(t, "clear"),
                "shuffle": tr(t, "shuffle"), "repeat": tr(t, "repeat")}

    def _balance_splitter(self):
        if not hasattr(self, "splitter") or not self.left_panel.isVisible():
            return
        total = max(1, self.splitter.width())
        left = int(min(max(total * 0.38, 330), 460))
        if total - left < 220:
            left = max(240, total - 220)
        self.splitter.setSizes([left, max(1, total - left)])

    def _open_equalizer_dialog(self):
        if self.eq_dialog is None:
            self._build_eq_dialog()
        if getattr(self, "_compact", False):
            self.eq_dialog.setMinimumWidth(300)
            self.eq_dialog.resize(min(self.width() - 16, 460), self.eq_dialog.sizeHint().height())
        self.eq_dialog.show()
        self.eq_dialog.raise_()
        self.eq_dialog.activateWindow()

    def _build_eq_dialog(self):
        t = self.current_language
        dlg = QDialog(self)
        dlg.setObjectName("eqDialog")
        dlg.setWindowTitle(tr(t, "equalizer"))
        dlg.setMinimumWidth(300 if getattr(self, "_compact", False) else 560)
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft if LANGUAGES[t]["rtl"] else Qt.LayoutDirection.LeftToRight)
        eq_layout = QVBoxLayout(dlg)
        eq_layout.setContentsMargins(14, 12, 14, 12)
        eq_layout.setSpacing(8)

        header = QHBoxLayout()
        self.eq_title_label = QLabel(tr(t, "equalizer"))
        self.eq_title_label.setObjectName("eqTitle")
        header.addWidget(self.eq_title_label)
        header.addStretch()

        self.eq_preset_combo = QComboBox()
        self.eq_preset_combo.setObjectName("eqPresetCombo")
        for key in FACTORY_PRESETS.keys():
            self.eq_preset_combo.addItem(tr(t, "preset_" + key), key)
        self.eq_preset_combo.currentIndexChanged.connect(self._on_eq_preset_changed)
        header.addWidget(self.eq_preset_combo)
        eq_layout.addLayout(header)

        bands_row = QHBoxLayout()
        bands_row.setSpacing(6)
        self.eq_band_sliders = []
        self.eq_band_value_labels = []
        centers = BAND_CENTERS[10]
        for i, freq in enumerate(centers):
            col = QVBoxLayout()
            col.setSpacing(2)
            val_label = QLabel("0 dB")
            val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_label.setObjectName("eqValueLabel")
            col.addWidget(val_label)

            slider = QSlider(Qt.Orientation.Vertical)
            slider.setObjectName("eqBandSlider")
            slider.setRange(-24, 24)
            slider.setValue(0)
            slider.setMinimumHeight(130)
            slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            slider.valueChanged.connect(lambda v, idx=i, lbl=val_label: self._on_eq_band_changed(idx, v, lbl))
            col.addWidget(slider, 0, Qt.AlignmentFlag.AlignHCenter)

            freq_label = QLabel(f"{freq}" if freq < 1000 else f"{freq/1000:g}k")
            freq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            freq_label.setObjectName("eqFreqLabel")
            col.addWidget(freq_label)

            bands_row.addLayout(col)
            self.eq_band_sliders.append(slider)
            self.eq_band_value_labels.append(val_label)
        eq_layout.addLayout(bands_row)

        preamp_row = QHBoxLayout()
        self.eq_preamp_label = QLabel(f"{tr(t, 'eq_preamp')}: 0 dB")
        self.eq_preamp_label.setObjectName("eqPreampLabel")
        preamp_row.addWidget(self.eq_preamp_label)
        self.eq_preamp_slider = QSlider(Qt.Orientation.Horizontal)
        self.eq_preamp_slider.setRange(-24, 24)
        self.eq_preamp_slider.setValue(0)
        self.eq_preamp_slider.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.eq_preamp_slider.valueChanged.connect(self._on_eq_preamp_changed)
        preamp_row.addWidget(self.eq_preamp_slider, 1)
        eq_layout.addLayout(preamp_row)

        ag_row = QHBoxLayout()
        ag_row.setSpacing(6)
        self.eq_auto_gain_check = QCheckBox(tr(t, "eq_auto_gain"))
        self.eq_auto_gain_check.setObjectName("eqAutoGainCheck")
        self.eq_auto_gain_check.setChecked(self.eq_engine.auto_gain)
        self.eq_auto_gain_check.setToolTip(tr(t, "eq_auto_gain_tip"))
        self.eq_auto_gain_check.toggled.connect(self._on_eq_auto_gain_changed)
        ag_row.addWidget(self.eq_auto_gain_check)
        self.eq_auto_gain_help_btn = QToolButton()
        self.eq_auto_gain_help_btn.setObjectName("infoBtn")
        self.eq_auto_gain_help_btn.setIcon(self._make_help_icon())
        self.eq_auto_gain_help_btn.setIconSize(QSize(18, 18))
        self.eq_auto_gain_help_btn.setAutoRaise(True)
        self.eq_auto_gain_help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eq_auto_gain_help_btn.clicked.connect(self._show_auto_gain_help)
        ag_row.addWidget(self.eq_auto_gain_help_btn)
        ag_row.addStretch()
        eq_layout.addLayout(ag_row)

        close_row = QHBoxLayout()
        self.eq_reset_btn = QPushButton(tr(t, "eq_reset"))
        self.eq_reset_btn.setObjectName("smallBtn")
        self.eq_reset_btn.clicked.connect(self._reset_equalizer)
        close_row.addWidget(self.eq_reset_btn)
        close_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("smallBtn")
        close_btn.setFixedWidth(36)
        close_btn.clicked.connect(dlg.hide)
        close_row.addWidget(close_btn)
        eq_layout.addLayout(close_row)

        theme = ThemeManager.get_theme(self.current_theme)
        base = getattr(self, "_stylesheet", "")
        dlg.setStyleSheet(
            base + f"\nQDialog#eqDialog {{ background: {theme['bg_secondary']}; color: {theme['text_primary']}; }}")

        self.eq_dialog = dlg
        self._restore_eq_settings()

    def _reset_equalizer(self):
        self.eq_engine.apply_preset("flat")
        self.eq_engine.set_preamp_db(0.0)
        self._restore_eq_settings()
        self._save_eq_settings()

    def _on_eq_band_changed(self, index, value, label):
        self.eq_engine.set_band_gain(index, float(value))
        label.setText(f"{value:+d} dB" if value != 0 else "0 dB")
        self._sync_eq_preset_combo_to_custom()
        self._save_eq_settings()

    def _on_eq_preamp_changed(self, value):
        self.eq_engine.set_preamp_db(float(value))
        self.eq_preamp_label.setText(f"{tr(self.current_language, 'eq_preamp')}: {value:+d} dB" if value != 0 else f"{tr(self.current_language, 'eq_preamp')}: 0 dB")
        self._save_eq_settings()

    def _on_eq_auto_gain_changed(self, checked):
        self.eq_engine.set_auto_gain(bool(checked))
        self._save_eq_settings()

    def _arrow_icon_path(self, direction, colour):
        cache = getattr(self, "_arrow_cache", None)
        if cache is None:
            cache = self._arrow_cache = {}
        key = (direction, str(colour))
        if key in cache:
            return cache[key]
        import tempfile
        pix = icons.pixmap("chevron_" + direction, 18, colour, 2.6)
        handle = tempfile.NamedTemporaryFile(prefix=f"parch-{direction}-", suffix=".png",
                                             delete=False)
        handle.close()
        pix.save(handle.name, "PNG")
        path = handle.name.replace("\\", "/")
        cache[key] = path
        return path

    def _combo_arrow_css(self, t) -> str:
        import tempfile
        cache = os.path.join(tempfile.gettempdir(), "parchmp_ui")
        os.makedirs(cache, exist_ok=True)
        urls = {}
        for name, pts, color in (("down", "6,9 12,15 18,9", t['text_secondary']),
                                 ("up", "6,15 12,9 18,15", t['accent_primary'])):
            tag = color.lstrip('#')
            path = os.path.join(cache, f"arrow_{name}_{tag}.png")
            if not os.path.exists(path):
                svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
                       f"<polyline points='{pts}' fill='none' stroke='{color}' "
                       "stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/></svg>")
                self._svg_icon(svg, 28).pixmap(28, 28).save(path)
            urls[name] = path.replace("\\", "/")
        return (f"QComboBox::down-arrow{{image:url('{urls['down']}');width:14px;height:14px;margin-right:5px;}}"
                f"QComboBox::down-arrow:on{{image:url('{urls['up']}');}}")

    @staticmethod
    def _svg_icon(svg: str, px: int = 40) -> QIcon:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pix = QPixmap(px, px)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        return QIcon(pix)

    def _make_help_icon(self) -> QIcon:
        accent = ThemeManager.get_theme(self.current_theme)["accent_primary"]
        return icons.icon("help", 30, accent, 2.1)

    def _update_transport_icons(self):
        theme = ThemeManager.get_theme(self.current_theme)
        side = theme["text_primary"]
        playing = self.is_playing and not self.is_paused
        self._control_buttons["previous"].setIcon(icons.icon("prev", 28, side))
        self._control_buttons["next"].setIcon(icons.icon("next", 28, side))
        self.play_button.setIcon(icons.icon("pause" if playing else "play", 30, "#ffffff"))
        self.play_button.setToolTip(tr(self.current_language, "pause" if playing else "play"))
        if hasattr(self, "tools_btn"):
            self.tools_btn.setIcon(icons.icon("gear", 17, side))
            self.device_btn.setIcon(icons.icon(self._device_icon_name(), 17, side))

    def _show_auto_gain_help(self):
        lang = self.current_language
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr(lang, "eq_auto_gain_help_title"))
        box.setText(tr(lang, "eq_auto_gain_help_body"))
        box.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if LANGUAGES[lang]["rtl"]
            else Qt.LayoutDirection.LeftToRight)
        box.exec()

    def _on_eq_preset_changed(self, combo_index):
        preset_key = self.eq_preset_combo.itemData(combo_index)
        if not preset_key or preset_key == "custom":
            return
        self.eq_engine.apply_preset(preset_key)
        for slider, gain, label in zip(self.eq_band_sliders, self.eq_engine.gains, self.eq_band_value_labels):
            slider.blockSignals(True)
            slider.setValue(int(round(gain)))
            slider.blockSignals(False)
            label.setText(f"{int(round(gain)):+d} dB" if gain else "0 dB")
        self._save_eq_settings()

    def _sync_eq_preset_combo_to_custom(self):
        idx = self.eq_preset_combo.findData("custom")
        if idx < 0:
            self.eq_preset_combo.addItem(tr(self.current_language, "preset_custom"), "custom")
            idx = self.eq_preset_combo.count() - 1
        self.eq_preset_combo.blockSignals(True)
        self.eq_preset_combo.setCurrentIndex(idx)
        self.eq_preset_combo.blockSignals(False)

    def _save_eq_settings(self):
        self.settings["eq_gains"] = self.eq_engine.gains
        self.settings["eq_preamp"] = self.eq_engine.preamp_db
        self.settings["eq_preset"] = self.eq_engine.current_preset
        self.settings["eq_auto_gain"] = self.eq_engine.auto_gain
        self._save_settings_soon()

    def _save_settings_soon(self, delay_ms: int = 400):
        if not hasattr(self, "_settings_save_timer"):
            self._settings_save_timer = QTimer(self)
            self._settings_save_timer.setSingleShot(True)
            self._settings_save_timer.timeout.connect(self._flush_settings_save)
        self._settings_save_timer.start(delay_ms)

    def _flush_settings_save(self):
        if hasattr(self, "_settings_save_timer"):
            self._settings_save_timer.stop()
        save_settings(self.settings)

    def _restore_eq_engine_state(self):
        gains = self.settings.get("eq_gains")
        preamp = self.settings.get("eq_preamp", 0.0)
        if gains and len(gains) == len(self.eq_engine.gains):
            self.eq_engine.gains = list(gains)
            self.eq_engine._impl.set_graphic_gains(self.eq_engine.gains)
            self.eq_engine.current_preset = self.settings.get("eq_preset", "custom")
        if preamp:
            self.eq_engine.set_preamp_db(float(preamp))
        self.eq_engine.set_auto_gain(bool(self.settings.get("eq_auto_gain", True)))

    def _restore_eq_settings(self):
        for slider, gain, label in zip(self.eq_band_sliders, self.eq_engine.gains, self.eq_band_value_labels):
            slider.blockSignals(True)
            slider.setValue(int(round(gain)))
            slider.blockSignals(False)
            label.setText(f"{int(round(gain)):+d} dB" if gain else "0 dB")
        preamp = self.eq_engine.preamp_db
        self.eq_preamp_slider.blockSignals(True)
        self.eq_preamp_slider.setValue(int(round(preamp)))
        self.eq_preamp_slider.blockSignals(False)
        self.eq_preamp_label.setText(
            f"{tr(self.current_language, 'eq_preamp')}: {int(round(preamp)):+d} dB" if preamp
            else f"{tr(self.current_language, 'eq_preamp')}: 0 dB")
        preset_idx = self.eq_preset_combo.findData(self.eq_engine.current_preset)
        if preset_idx >= 0:
            self.eq_preset_combo.blockSignals(True)
            self.eq_preset_combo.setCurrentIndex(preset_idx)
            self.eq_preset_combo.blockSignals(False)

    def _apply_theme(self):
        theme = ThemeManager.get_theme(self.current_theme)
        t = theme
        if hasattr(self, "waveform_bar"):
            self.waveform_bar.set_theme(self.current_theme, t.get("accent_primary"))

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
            
            #transportBtn {{
                background: {t['button_bg']};
                border: 1px solid {t['border']};
                border-radius: 25px;
            }}
            #transportBtn:hover {{
                background: {t['bg_surface_light']};
                border-color: {t['accent_primary']};
            }}
            #transportBtn:pressed {{ background: {t['accent_primary']}; }}

            #playPauseBtn {{
                background: {t['accent_primary']};
                border: none;
                border-radius: 33px;
            }}
            #playPauseBtn:hover {{ background: {t['accent_gold']}; }}
            #playPauseBtn:pressed {{ background: {t['accent_tertiary']}; }}
            
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

            #eqTitle {{
                color: {t['text_primary']};
                font-size: 13px;
                font-weight: 600;
            }}

            #eqValueLabel {{
                color: {t['accent_tertiary']};
                font-size: 10px;
                font-weight: 600;
            }}

            #eqFreqLabel {{
                color: {t['text_secondary']};
                font-size: 9px;
            }}

            #eqPreampLabel {{
                color: {t['text_secondary']};
                font-size: 11px;
            }}

            QSlider#eqBandSlider::groove:vertical {{
                background: {t['slider_bg']};
                width: 4px;
                border-radius: 2px;
            }}

            QSlider#eqBandSlider::handle:vertical {{
                background: {t['accent_primary']};
                height: 14px;
                margin: 0 -6px;
                border-radius: 7px;
                border: 2px solid {t['bg_card']};
            }}

            QComboBox {{
                background: {t['input_bg']};
                color: {t['text_primary']};
                border: 1px solid {t['input_border']};
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QComboBox:hover {{ border-color: {t['accent_primary']}; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background: {t['bg_card']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                selection-background-color: {t['accent_primary']};
                selection-color: white;
                outline: none;
            }}
            #eqAutoGainCheck {{
                color: {t['text_primary']};
                font-size: 11px;
            }}
            #infoBtn {{
                border: none;
                background: transparent;
                padding: 0px;
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

            #viewTab {{
                background: transparent; color: {t['text_secondary']};
                border: 1px solid transparent; border-radius: 6px;
                padding: 5px 6px; font-size: 12px;
            }}
            #viewTab:hover {{ color: {t['text_primary']}; background: {t['bg_surface_light']}; }}
            #viewTab:checked {{
                background: {t['accent_primary']}; color: #ffffff;
                border: 1px solid {t['accent_primary']};
            }}
            #crumbLabel {{ color: {t['text_primary']}; font-weight: bold; }}

            QMenu {{
                background: {t['bg_card']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QMenu::item {{ padding: 8px 20px; border-radius: 5px; }}
            QMenu::item:selected {{ background: {t['accent_primary']}; color: white; }}
            QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

            QMessageBox {{ background: {t['bg_secondary']}; color: {t['text_primary']}; }}
            QMessageBox QLabel {{ color: {t['text_primary']}; }}
            QCheckBox {{ color: {t['text_primary']}; }}

            QDialog {{ background: {t['bg_secondary']}; color: {t['text_primary']}; }}
            QDialog QLabel {{ color: {t['text_primary']}; background: transparent; }}
            QDialog QCheckBox {{ color: {t['text_primary']}; }}
            QDialog QGroupBox {{ color: {t['text_primary']}; border: 1px solid {t['border']};
                                 border-radius: 6px; margin-top: 8px; padding-top: 8px; }}
            QDialog QLineEdit, QDialog QSpinBox, QDialog QDoubleSpinBox, QDialog QComboBox {{
                background: {t['input_bg']}; color: {t['text_primary']};
                border: 1px solid {t['input_border']}; border-radius: 6px; padding: 5px 8px;
            }}
            QDialog QLineEdit:focus, QDialog QSpinBox:focus, QDialog QComboBox:focus {{
                border: 1px solid {t['input_focus']};
            }}
            QDialog QListWidget, QDialog QTreeView, QDialog QTreeWidget, QDialog QTextEdit,
            QDialog QPlainTextEdit, QDialog QScrollArea, QDialog QAbstractScrollArea {{
                background: {t['bg_card']}; color: {t['text_primary']};
                border: 1px solid {t['border']}; border-radius: 6px;
            }}
            QDialog QListWidget::item {{ padding: 5px 7px; border-radius: 4px; }}
            QDialog QListWidget::item:selected, QDialog QTreeView::item:selected {{
                background: {t['accent_primary']}; color: #ffffff;
            }}
            QDialog QTreeView::item {{ padding: 3px; }}
            QDialog QHeaderView::section {{
                background: {t['bg_surface']}; color: {t['text_secondary']};
                border: none; padding: 5px; }}
            QDialog QPushButton {{
                background: {t['button_bg']}; color: {t['text_primary']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 6px 14px; min-height: 18px;
            }}
            QDialog QPushButton:hover {{ background: {t['bg_surface_light']};
                                         border: 1px solid {t['accent_primary']}; }}
            QDialog QPushButton:default {{ background: {t['accent_primary']}; color: #ffffff; }}
            QDialog QScrollBar:vertical {{ background: {t['bg_card']}; width: 10px;
                                           border-radius: 5px; }}
            QDialog QScrollBar::handle:vertical {{ background: {t['border']};
                                                   border-radius: 5px; min-height: 24px; }}
            QDialog QScrollBar::add-line, QDialog QScrollBar::sub-line {{ height: 0; }}
            QDialog QSplitter::handle {{ background: {t['border']}; }}
            QDialog QSpinBox, QDialog QDoubleSpinBox {{ padding-right: 20px; }}
            QDialog QSpinBox::up-button, QDialog QDoubleSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 18px; border-left: 1px solid {t['input_border']};
                border-top-right-radius: 6px; background: {t['bg_surface_light']};
            }}
            QDialog QSpinBox::down-button, QDialog QDoubleSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 18px; border-left: 1px solid {t['input_border']};
                border-bottom-right-radius: 6px; background: {t['bg_surface_light']};
            }}
            QDialog QSpinBox::up-button:hover, QDialog QSpinBox::down-button:hover,
            QDialog QDoubleSpinBox::up-button:hover,
            QDialog QDoubleSpinBox::down-button:hover {{
                background: {t['accent_primary']};
            }}
            QDialog QSpinBox::up-arrow, QDialog QDoubleSpinBox::up-arrow {{
                image: url("{self._arrow_icon_path('up', t['text_primary'])}");
                width: 9px; height: 9px;
            }}
            QDialog QSpinBox::down-arrow, QDialog QDoubleSpinBox::down-arrow {{
                image: url("{self._arrow_icon_path('down', t['text_primary'])}");
                width: 9px; height: 9px;
            }}
        """

        stylesheet += self._combo_arrow_css(t)
        self._stylesheet = stylesheet
        self.setStyleSheet(stylesheet)
        icons.clear_cache()
        self._refresh_all_icons()
        if getattr(self, "eq_dialog", None) is not None:
            self.eq_dialog.setStyleSheet(
                stylesheet + f"QDialog#eqDialog {{ background: {t['bg_secondary']}; color: {t['text_primary']}; }}")
        self.visualizer.set_theme(self.current_theme)
        self.vinyl.set_theme(self.current_theme)
        self.tree_delegate.set_theme(self.current_theme)
        if hasattr(self, "_control_buttons"):
            self._update_transport_icons()
        if hasattr(self, "playlist_toggle_btn"):
            self._sync_toggle_label()
        self.playlist_tree.viewport().update()
        target = "theme_dark" if self.current_theme == 'light' else "theme_light"
        self.theme_btn.setText(tr(self.current_language, target))
        self.settings["theme"] = self.current_theme
        save_settings(self.settings)
    
    def _toggle_theme(self):
        self.current_theme = 'light' if self.current_theme == 'dark' else 'dark'
        self._apply_theme()
    
    def _toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
        else:
            self.showFullScreen()
        self.is_fullscreen = not self.is_fullscreen

    def _get_font_for_language(self, language: str) -> QFont:
        if language in self._loaded_fonts:
            return self._loaded_fonts[language]

        meta = LANGUAGES.get(language, LANGUAGES[DEFAULT_LANGUAGE_FALLBACK])
        family = meta["font_fallback"]
        font_file = meta.get("font_file")
        if font_file:
            font_path = find_font_file(font_file)
            if font_path:
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        family = families[0]

        font = QFont(family, 10)
        font.setFamilies([family, "Noto Sans", "DejaVu Sans", "sans-serif"])
        self._loaded_fonts[language] = font
        return font

    def _on_language_selected(self, _idx=None):
        code = self.lang_combo.currentData()
        if not code or code == self.current_language:
            return
        self._set_language(code)

    def _set_language(self, language: str):
        self.current_language = language
        self.settings["language"] = language
        self._save_settings_soon()

        new_font = self._get_font_for_language(language)
        QApplication.instance().setFont(new_font)
        self.setFont(new_font)
        is_rtl = LANGUAGES[language]["rtl"]
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl else Qt.LayoutDirection.LeftToRight)
        if hasattr(self, "visualizer"):
            self.visualizer.set_rtl(is_rtl)
        if hasattr(self, "progress_slider"):
            self.progress_slider.setInvertedAppearance(False)
        if hasattr(self, "volume_slider"):
            self.volume_slider.setInvertedAppearance(False)

        self._repolish_fonts(new_font)

        idx = self.lang_combo.findData(language)
        if idx >= 0 and self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)

        self._retranslate_ui()

    def _repolish_fonts(self, font: QFont):
        app = QApplication.instance()
        widgets = [self] + list(self.findChildren(QWidget))
        for w in widgets:
            w.setFont(font)
            style = w.style()
            if style is not None:
                style.unpolish(w)
                style.polish(w)
            w.update()
        if app is not None:
            app.setFont(font)

    def _retranslate_ui(self):
        lang = self.current_language
        t = lambda key: tr(lang, key)

        self.global_search.setPlaceholderText(t("search"))
        self.help_btn.setToolTip(t("help"))
        self.theme_btn.setText(t("theme_dark") if self.current_theme == 'light' else t("theme_light"))
        self.pl_title.setText(t("playlist"))
        self._sort_btn.setText(t("sort_button"))
        self._files_btn.setText(t("files"))
        self._folder_btn.setText(t("folder"))
        self.playlist_tree.setHeaderLabels(["#", t("title_col"), t("time_col"), "", ""])

        self._list_narrow = None
        self._apply_list_density()
        self._paint_list_buttons()
        self._update_view_chrome()
        self._control_buttons["previous"].setToolTip(t("previous"))
        self._control_buttons["next"].setToolTip(t("next"))
        self.play_button.setToolTip(
            t("pause") if (self.is_playing and not self.is_paused) else t("play"))

        self.vol_label.setText(t("volume"))
        self._sync_toggle_label()

        if self.current_index < 0:
            self.title_label.setText(t("select_track"))
            self.artist_label.setText(t("unknown_artist"))
            self.album_label.setText(t("unknown_album"))
            self.mini_info.setText(t("ready"))
        elif self.is_playing:
            item = self.playlist[self.current_index]
            self.mini_info.setText(f"{t('play')}: {item['title'][:25]}...")
        self._revert_status_info()

        track_count = len(self.playlist)
        self.track_count.setText(f"{track_count} {t('tracks_word')}")
        self._update_playlist_column_widths()
        self._refresh_playlist(self.global_search.text() if hasattr(self, 'global_search') else "")

        if hasattr(self, "eq_title_label"):
            self.eq_title_label.setText(t("equalizer"))
            preamp_val = self.eq_preamp_slider.value()
            self.eq_preamp_label.setText(f"{t('eq_preamp')}: {preamp_val:+d} dB" if preamp_val else f"{t('eq_preamp')}: 0 dB")
            self.eq_reset_btn.setText(t("eq_reset"))
            self.eq_preset_combo.blockSignals(True)
            for i in range(self.eq_preset_combo.count()):
                pk = self.eq_preset_combo.itemData(i)
                if pk:
                    self.eq_preset_combo.setItemText(i, t("preset_" + pk))
            self.eq_preset_combo.blockSignals(False)
            self.eq_auto_gain_check.setText(t("eq_auto_gain"))
            self.eq_auto_gain_check.setToolTip(t("eq_auto_gain_tip"))
            if self.eq_dialog is not None:
                self.eq_dialog.setWindowTitle(t("equalizer"))
                self.eq_dialog.setLayoutDirection(
                    Qt.LayoutDirection.RightToLeft if LANGUAGES[self.current_language]["rtl"]
                    else Qt.LayoutDirection.LeftToRight)

        if hasattr(self, "_tray_actions"):
            self._tray_actions["tray_toggle"].setText(t("tray_toggle"))
            self._tray_actions["play"].setText(f"{t('play')} / {t('pause')}")
            self._tray_actions["next"].setText(t("next"))
            self._tray_actions["previous"].setText(t("previous"))
            self._tray_actions["exit_app"].setText(t("exit_app"))

    def _open_help(self):
        theme = ThemeManager.get_theme(self.current_theme)
        dlg = HelpDialog(theme, self.current_language, font_loader=self._get_font_for_language, parent=self)
        dlg.resize(min(880, max(320, self.width() - 20)), min(600, max(360, self.height() - 20)))
        dlg.exec()
    
    def _setup_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            icon_path = resource_path("assets/icon.ico")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            t = self.current_language
            menu = QMenu(self)
            self._tray_actions = {
                "tray_toggle": menu.addAction(tr(t, "tray_toggle"), self._toggle_visibility),
            }
            menu.addSeparator()
            self._tray_actions["play"] = menu.addAction(f"{tr(t, 'play')} / {tr(t, 'pause')}", self._play_pause)
            self._tray_actions["next"] = menu.addAction(tr(t, "next"), self._next_track)
            self._tray_actions["previous"] = menu.addAction(tr(t, "previous"), self._prev_track)
            menu.addSeparator()
            self._tray_actions["exit_app"] = menu.addAction(tr(t, "exit_app"), self.close)
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.show()
    
    def _add_files(self):
        lang = self.current_language
        name_filter = audio_name_filter(tr(lang, "music_files"), tr(lang, "all_files"))
        files, _ = QFileDialog.getOpenFileNames(
            self, tr(lang, "files"), "", name_filter)
        if not files:
            return
        for f in files:
            if os.path.splitext(f)[1].lower() in PLAYLIST_EXTENSIONS:
                self._import_playlist_file(f)
            else:
                self._add_to_playlist(f)
        self._after_playlist_added()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr(self.current_language, "folder"))
        if not folder:
            return
        found = []
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                    found.append(os.path.join(root, name))
        found.sort()
        for path in found:
            self._add_to_playlist(path)
        self._after_playlist_added()

    def _import_playlist_file(self, path):
        entries = playlists.parse(path)
        added = 0
        for entry in entries:
            target = entry.get("path")
            if not target or not os.path.exists(target):
                continue
            if entry.get("cue_start") is not None and entry.get("cue_source"):
                if self._add_cue_entry(entry):
                    added += 1
            elif os.path.splitext(target)[1].lower() in AUDIO_EXTENSIONS:
                if self._add_to_playlist(target):
                    added += 1
        return added

    def _add_cue_entry(self, entry):
        key = f"{entry['path']}#{entry.get('cue_start', 0):.3f}"
        if key in self._playlist_paths:
            return False
        meta = self.metadata_manager.get_metadata(entry["path"])
        start = float(entry.get("cue_start") or 0.0)
        end = entry.get("cue_end")
        duration = int((end - start) if end else max(0, (meta.get("duration", 0) or 0) - start))
        self.playlist.append({
            'path': entry["path"],
            'cue_key': key,
            'cue_start': start,
            'cue_end': float(end) if end else None,
            'title': entry.get("title") or os.path.basename(entry["path"]),
            'artist': entry.get("artist") or meta.get('artist', 'Unknown Artist'),
            'album': entry.get("album") or meta.get('album', 'Unknown Album'),
            'genre': entry.get("genre") or meta.get('genre', ''),
            'year': entry.get("year") or meta.get('year', ''),
            'duration': duration,
            'track_number': entry.get("track_no", 0),
            'cover_data': meta.get('cover_art'),
            'cover_path': meta.get('cover_path', ''),
            'bitrate': meta.get('bitrate', 0),
            'sample_rate': meta.get('sample_rate', 0),
            'mtime': safe_mtime(entry["path"]),
            '_add_seq': self._add_counter,
        })
        self._add_counter += 1
        self._playlist_paths.add(key)
        return True

    def _after_playlist_added(self):
        if self._sort_mode:
            self._sort_playlist(self._sort_mode, toggle=False)
        else:
            self._refresh_playlist(self._current_filter())

    def _add_to_playlist(self, filepath):
        if filepath in self._playlist_paths:
            return False
        meta = self.metadata_manager.get_metadata(filepath)
        self.playlist.append({
            'path': filepath,
            'title': meta.get('title', os.path.basename(filepath)),
            'artist': meta.get('artist', 'Unknown Artist'),
            'album': meta.get('album', 'Unknown Album'),
            'genre': meta.get('genre', ''),
            'year': meta.get('year', ''),
            'duration': meta.get('duration', 0),
            'track_number': meta.get('track_number', 0),
            'cover_data': meta.get('cover_art'),
            'cover_path': meta.get('cover_path', ''),
            'bitrate': meta.get('bitrate', 0),
            'sample_rate': meta.get('sample_rate', 0),
            'mtime': safe_mtime(filepath),
            '_add_seq': self._add_counter,
        })
        self._add_counter += 1
        self._playlist_paths.add(filepath)
        return True

    def _current_filter(self):
        return self.global_search.text() if hasattr(self, "global_search") else ""

    _SORT_MODES = [
        ("title_asc", "sort_title_asc"), ("title_desc", "sort_title_desc"),
        ("newest", "sort_newest"), ("oldest", "sort_oldest"),
        ("duration_asc", "sort_duration_asc"), ("duration_desc", "sort_duration_desc"),
    ]

    def _show_sort_menu(self):
        t = self.current_language
        menu = StayOpenMenu(self)
        self._sort_actions = {}
        for mode, key in self._SORT_MODES:
            act = menu.addAction(tr(t, key))
            act.setCheckable(True)
            act.setChecked(self._sort_mode == mode)
            act.triggered.connect(lambda _checked=False, m=mode: self._sort_playlist(m))
            self._sort_actions[mode] = act
        menu.aboutToHide.connect(lambda: setattr(self, "_sort_actions", {}))
        menu.exec(self._sort_btn.mapToGlobal(self._sort_btn.rect().bottomLeft()))

    def _title_text(self, track):
        return (track.get("title") or os.path.basename(track.get("path", ""))).strip()

    def _sort_playlist(self, mode, toggle=True):
        if mode not in dict(self._SORT_MODES):
            return
        turning_off = toggle and (mode == self._sort_mode)
        self._sort_mode = None if turning_off else mode

        if self.playlist:
            current_path = None
            if 0 <= self.current_index < len(self.playlist):
                current_path = self.playlist[self.current_index]["path"]

            if turning_off:
                self.playlist.sort(key=lambda k: k.get("_add_seq", 0))
            elif mode in ("title_asc", "title_desc"):
                col = QCollator(QLocale(self.current_language))
                col.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                col.setNumericMode(True)
                self.playlist.sort(
                    key=functools.cmp_to_key(
                        lambda a, b: col.compare(self._title_text(a), self._title_text(b))),
                    reverse=(mode == "title_desc"))
            else:
                simple = {
                    "newest": (lambda k: k.get("mtime", 0.0), True),
                    "oldest": (lambda k: k.get("mtime", 0.0), False),
                    "duration_asc": (lambda k: k.get("duration", 0), False),
                    "duration_desc": (lambda k: k.get("duration", 0), True),
                }
                keyfn, reverse = simple[mode]
                self.playlist.sort(key=keyfn, reverse=reverse)

            if current_path is not None:
                self.current_index = next(
                    (i for i, k in enumerate(self.playlist) if k["path"] == current_path),
                    self.current_index)
            self._refresh_playlist(self._current_filter())

        for m, act in getattr(self, "_sort_actions", {}).items():
            act.setChecked(self._sort_mode == m)

    def _build_track_icon(self, item):
        if item.get('cover_data'):
            img = QImage.fromData(QByteArray(item['cover_data']))
            if not img.isNull():
                pixmap = QPixmap.fromImage(img).scaled(
                    40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                return QIcon(pixmap)
        if item.get('cover_path'):
            pixmap = QPixmap(item['cover_path']).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if not pixmap.isNull():
                return QIcon(pixmap)
        if self._default_track_icon is None:
            default_pix = QPixmap(40, 40)
            default_pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(default_pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor("#333333"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, 40, 40, 5, 5)
            painter.setPen(QColor("#666666"))
            note_font = QFont("Noto Sans", 16)
            note_font.setFamilies(["Noto Sans", "DejaVu Sans", "sans-serif"])
            painter.setFont(note_font)
            painter.drawText(QRectF(0, 0, 40, 40), Qt.AlignmentFlag.AlignCenter, "♪")
            painter.end()
            self._default_track_icon = QIcon(default_pix)
        return self._default_track_icon

    def _refresh_playlist(self, filter_text=""):
        self._update_view_chrome()
        if self._view_mode != "all":
            self._refresh_browse_view(filter_text)
            self._update_playlist_column_widths()
            return
        self.playlist_tree.clear()
        self._view_rows = []
        library_rows = {}
        if getattr(self, "library", None) is not None:
            try:
                library_rows = self.library.get_many([t['path'] for t in self.playlist])
            except Exception:
                library_rows = {}
        for idx, item in enumerate(self.playlist):
            if filter_text:
                q = filter_text.lower()
                if (q not in item['title'].lower() and q not in item['artist'].lower()):
                    continue
            
            dur = format_time(item['duration'])
            track_num = str(idx + 1)
            
            tree_item = QTreeWidgetItem([track_num, item['title'], dur, "", ""])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, idx)
            row = library_rows.get(item['path']) if library_rows else None
            tree_item.setData(3, TreeItemDelegate.FAVOURITE_ROLE,
                              bool(row and row.get('favorite')))
            tree_item.setData(3, TreeItemDelegate.RATING_ROLE,
                              int(row.get('rating') or 0) if row else 0)
            
            icon = item.get('_icon_cache')
            if icon is None:
                icon = self._build_track_icon(item)
                item['_icon_cache'] = icon
            tree_item.setIcon(1, icon)
            
            if idx == self.current_index:
                font = tree_item.font(0)
                font.setBold(True)
                for col in range(3):
                    tree_item.setFont(col, font)
                    tree_item.setForeground(col, QColor(ThemeManager.get_theme(self.current_theme)['accent_primary']))
            
            _t = self.current_language
            tree_item.setToolTip(0, f"{tr(_t,'md_title')}: {item['title']}\n{tr(_t,'md_artist')}: {item.get('artist','')}\n{tr(_t,'md_album')}: {item.get('album','')}\n{tr(_t,'md_path')}: {item['path']}")
            self.playlist_tree.addTopLevelItem(tree_item)
        
        self.track_count.setText(f"{len(self.playlist)} {tr(self.current_language, 'tracks_word')}")
        self._update_playlist_column_widths()
    
    def _set_view_mode(self, mode, context=None):
        self._view_mode = mode
        self._view_context = context
        for key, btn in self._view_buttons.items():
            btn.setChecked(key == mode)
        self._refresh_playlist(self._current_filter())

    def _view_go_back(self):
        if self._view_context is not None:
            self._set_view_mode(self._view_mode, None)
        else:
            self._set_view_mode("all")

    def _play_current_group(self):
        rows = [r for r in self._view_rows if r.get("path")]
        if not rows:
            return
        first = None
        for row in rows:
            path = row["path"]
            if not os.path.exists(path):
                continue
            self._add_to_playlist(path)
            if first is None:
                first = path
        self._after_playlist_added()
        if first is None:
            return
        for i, track in enumerate(self.playlist):
            if track.get("path") == first:
                self._play_index(i)
                break

    def _update_view_chrome(self):
        t = self.current_language
        labels = {"all": tr(t, "view_all"), "albums": tr(t, "view_albums"),
                  "artists": tr(t, "view_artists"), "favourites": tr(t, "favourites")}
        for key, btn in self._view_buttons.items():
            btn.setText(labels[key])
        colour = ThemeManager.get_theme(self.current_theme)["text_primary"]
        rtl = LANGUAGES[self.current_language]["rtl"]
        self.back_btn.setIcon(icons.icon("chevron_right" if rtl else "chevron_left", 15, colour))
        self.back_btn.setToolTip(tr(t, "back"))
        self.crumb_play_btn.setIcon(icons.icon("play", 13, colour))
        self.crumb_play_btn.setText(tr(t, "play_all"))
        show = self._view_context is not None
        self.crumb_bar.setVisible(show)
        if show:
            self.crumb_label.setText(str(self._view_context.get("label", "")))

    def _refresh_browse_view(self, filter_text=""):
        self.playlist_tree.clear()
        self._view_rows = []
        if self.library is None:
            return
        needle = (filter_text or "").lower()
        mode = self._view_mode
        context = self._view_context

        if mode == "favourites":
            rows = self.library.favorites()
            self._fill_track_rows(rows, needle)
            return

        if context is not None:
            if mode == "albums":
                rows = self.library.album_tracks(context.get("artist"), context.get("album"))
            else:
                rows = self.library.search(f'artist:"{context.get("artist")}"')
            self._fill_track_rows(rows, needle)
            return

        if mode == "albums":
            entries = self.library.albums()
            for entry in entries:
                label = f"{entry.get('album') or '?'}"
                artist = entry.get("aartist") or ""
                if needle and needle not in (label + " " + artist).lower():
                    continue
                item = QTreeWidgetItem(["", label, str(entry.get("tracks") or 0), "", ""])
                item.setToolTip(1, f"{artist}\n{label}")
                item.setData(0, Qt.ItemDataRole.UserRole + 5,
                             {"kind": "album", "artist": artist, "album": entry.get("album"),
                              "label": f"{artist} - {label}" if artist else label})
                icon = self._group_icon(entry.get("sample"))
                if icon is not None:
                    item.setIcon(1, icon)
                item.setText(2, str(entry.get("tracks") or 0))
                self.playlist_tree.addTopLevelItem(item)
            self.track_count.setText(
                f"{self.playlist_tree.topLevelItemCount()} {tr(self.current_language, 'albums_word')}")
            return

        if mode == "artists":
            for entry in self.library.artists():
                name = entry.get("name") or "?"
                if needle and needle not in name.lower():
                    continue
                item = QTreeWidgetItem(["", name, str(entry.get("tracks") or 0), "", ""])
                item.setData(0, Qt.ItemDataRole.UserRole + 5,
                             {"kind": "artist", "artist": name, "label": name})
                self.playlist_tree.addTopLevelItem(item)
            self.track_count.setText(
                f"{self.playlist_tree.topLevelItemCount()} {tr(self.current_language, 'artists_word')}")

    def _fill_track_rows(self, rows, needle=""):
        theme = ThemeManager.get_theme(self.current_theme)
        current = self._current_path()
        shown = 0
        for row in rows:
            title = row.get("title") or os.path.basename(row.get("path", ""))
            artist = row.get("artist") or ""
            if needle and needle not in f"{title} {artist}".lower():
                continue
            shown += 1
            item = QTreeWidgetItem([str(shown), title,
                                    format_time(int(row.get("duration") or 0)), "", ""])
            item.setData(0, Qt.ItemDataRole.UserRole + 6, row.get("path"))
            item.setData(3, TreeItemDelegate.FAVOURITE_ROLE, bool(row.get("favorite")))
            item.setToolTip(1, f"{artist}\n{row.get('album') or ''}")
            icon = self._group_icon(row.get("path"))
            if icon is not None:
                item.setIcon(1, icon)
            if current and row.get("path") == current:
                font = item.font(1)
                font.setBold(True)
                item.setFont(1, font)
                item.setForeground(1, QColor(theme["accent_primary"]))
            self.playlist_tree.addTopLevelItem(item)
            self._view_rows.append(row)
        self.track_count.setText(
            f"{shown} {tr(self.current_language, 'tracks_word')}")

    def _group_icon(self, path):
        if not path:
            return None
        cache = getattr(self, "_group_icon_cache", None)
        if cache is None:
            cache = self._group_icon_cache = {}
        if path in cache:
            return cache[path]
        icon = None
        try:
            meta = self.metadata_manager.get_metadata(path)
            data = meta.get("cover_art")
            if data:
                pix = QPixmap()
                if pix.loadFromData(data):
                    icon = QIcon(pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        except Exception:
            icon = None
        if icon is None:
            icon = self._build_default_track_icon()
        if len(cache) < 400:
            cache[path] = icon
        return icon

    def _build_default_track_icon(self):
        if self._default_track_icon is None:
            colour = ThemeManager.get_theme(self.current_theme)["text_secondary"]
            self._default_track_icon = icons.icon("note", 34, colour)
        return self._default_track_icon

    def _on_item_clicked(self, item, column):
        group = item.data(0, Qt.ItemDataRole.UserRole + 5)
        if group is not None:
            self._set_view_mode(self._view_mode, group)
            return
        browse_path = item.data(0, Qt.ItemDataRole.UserRole + 6)
        if browse_path is not None:
            if column == 3:
                self._toggle_favorite_path(browse_path)
            return
        if column == 3:
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            if idx is not None and 0 <= idx < len(self.playlist):
                self._toggle_favorite_path(self.playlist[idx].get('path'))
            return
        if column == 4:
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            pos = self.playlist_tree.mapToGlobal(
                self.playlist_tree.visualItemRect(item).topRight())
            self._show_track_menu(item, idx, pos)

    def _track_menu_style(self, theme):
        return f"""
            QMenu {{
                background: {theme['bg_card']};
                color: {theme['text_primary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QMenu::item {{ padding: 8px 20px; border-radius: 5px; }}
            QMenu::item:selected {{ background: {theme['accent_primary']}; color: white; }}
            QMenu::separator {{ height: 1px; background: {theme['border']}; margin: 4px 8px; }}
        """

    def _show_track_menu(self, item, idx, global_pos):
        t = self.current_language
        menu = QMenu(self)
        menu.setStyleSheet(self._track_menu_style(ThemeManager.get_theme(self.current_theme)))
        menu.addAction(tr(t, "play"), lambda: self._on_playlist_double_click(item))
        menu.addAction(tr(t, "edit_metadata"), lambda: self._edit_metadata(idx))
        track = self.playlist[idx] if 0 <= idx < len(self.playlist) else {}
        if track.get("cover_data") or track.get("cover_path"):
            menu.addAction(tr(t, "save_cover"), lambda: self._save_cover(idx))
        menu.addSeparator()
        menu.addAction(tr(t, "remove_action"), lambda: self._remove_single(idx))
        self._feature_menu_entries(menu, idx)
        menu.exec(global_pos)

    @staticmethod
    def _safe_filename(name):
        name = "".join(c for c in (name or "") if c not in '<>:"/\\|?*').strip()
        return (name or "cover")[:80]

    def _save_cover(self, idx):
        if not (0 <= idx < len(self.playlist)):
            return
        track = self.playlist[idx]
        data = track.get("cover_data")
        ext = ".jpg"
        if not data and track.get("cover_path") and os.path.exists(track["cover_path"]):
            try:
                with open(track["cover_path"], "rb") as f:
                    data = f.read()
                ext = os.path.splitext(track["cover_path"])[1] or ".jpg"
            except OSError:
                data = None
        if not data:
            self.status_info.setText(tr(self.current_language, "cover_save_failed"))
            return
        data = bytes(data)
        if data[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"

        downloads = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if not downloads or not os.path.isdir(downloads):
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(downloads):
            downloads = os.path.expanduser("~")
        suggested = os.path.join(downloads, self._safe_filename(track.get("title")) + ext)
        lang = self.current_language
        dest, _ = QFileDialog.getSaveFileName(
            self, tr(lang, "save_cover"), suggested,
            f"{tr(lang, 'md_images')} (*.jpg *.jpeg *.png *.webp);;{tr(lang, 'all_files')} (*)")
        if not dest:
            return
        try:
            with open(dest, "wb") as f:
                f.write(data)
            self.status_info.setText(tr(lang, "cover_saved").format(name=os.path.basename(dest)))
        except OSError:
            self.status_info.setText(tr(lang, "cover_save_failed"))

    def _confirm(self, title_key, text):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr(self.current_language, title_key))
        box.setText(text)
        yes = box.addButton(tr(self.current_language, "yes"),
                            QMessageBox.ButtonRole.YesRole)
        box.addButton(tr(self.current_language, "no"), QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes)
        if hasattr(self, "_stylesheet"):
            box.setStyleSheet(self._stylesheet)
        box.exec()
        return box.clickedButton() is yes

    def _remove_single(self, idx):
        if not (0 <= idx < len(self.playlist)):
            return
        name = self.playlist[idx].get("title") or ""
        if not self._confirm("remove_action",
                             tr(self.current_language, "confirm_remove_one").format(name=name)):
            return
        was_current = (idx == self.current_index)
        if was_current:
            self._stop()
            self.player.setSource(QUrl())
        self._playlist_paths.discard(self.playlist[idx]['path'])
        del self.playlist[idx]
        if self.current_index > idx:
            self.current_index -= 1
        elif self.current_index == idx:
            self.current_index = -1
        if was_current:
            self._update_now_playing(-1)
        self._refresh_playlist(self.global_search.text())
        self.status_info.setText(tr(self.current_language, "track_removed"))
    
    def _play_index(self, idx):
        if idx < 0 or idx >= len(self.playlist):
            return
        
        self.current_index = idx
        item = self.playlist[idx]
        self._failed_path = None

        if getattr(self, "_compact", False):
            self.left_panel.setVisible(False)
            self.right_panel.setVisible(True)
            self._sync_toggle_label()

        self._cue_start = float(item.get('cue_start') or 0.0)
        self._cue_end = item.get('cue_end')
        self._cue_seek_pending = self._cue_start > 0.0
        self.player.setSource(QUrl.fromLocalFile(item['path']))
        if hasattr(self, "eq_engine"):
            self.eq_engine.reset_state()
        self._update_now_playing(idx)
        self._highlight_current_track()
        
        self.player.play()
        self.is_playing = True
        self.is_paused = False
        self.vinyl.set_playing(True)
        self.visualizer.set_playing(True)
        
        self._update_transport_icons()
        self.mini_info.setText(f"{tr(self.current_language, 'play')}: {item['title'][:25]}...")
        
        self._update_track_highlight()

        bitrate = item.get('bitrate', 0)
        sample_rate = item.get('sample_rate', 0)
        self.status_info.setText(f"{bitrate} kbps | {sample_rate/1000:.1f} kHz")

        self._features_track_started(idx)

    def _play_pause(self):
        if not self.player.source().isValid() and self.playlist:
            if self.current_index == -1:
                self.current_index = 0
            self._play_index(self.current_index)
            return
        
        if self.is_playing and not self.is_paused:
            self.player.pause()
            self.is_paused = True
            self._update_transport_icons()
            self.vinyl.set_playing(False)
            self.visualizer.set_playing(False)
        elif self.is_playing and self.is_paused:
            self.player.play()
            self.is_paused = False
            self._update_transport_icons()
            self.vinyl.set_playing(True)
            self.visualizer.set_playing(True)
        else:
            if self.current_index == -1 and self.playlist:
                self._play_index(0)
            else:
                self._play_index(self.current_index)
        
        self._update_track_highlight()
    
    def _stop(self):
        self.player.stop()
        self.is_playing = False
        self.is_paused = False
        self._update_transport_icons()
        self.vinyl.set_playing(False)
        self.visualizer.set_playing(False)
        self.progress_slider.setValue(0)
        self.current_time.setText("00:00")
        self.total_time.setText("00:00")
        self.mini_info.setText(tr(self.current_language, "ready"))
        self.status_info.setText(tr(self.current_language, "stopped"))
        self._update_track_highlight()
    
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
        queued = self._queue_take()
        if queued >= 0:
            self.current_index = queued
            self._play_index(queued)
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
            self.title_label.setText(tr(self.current_language, "select_track"))
            self.artist_label.setText(tr(self.current_language, "unknown_artist"))
            self.album_label.setText(tr(self.current_language, "unknown_album"))
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
    
    def _update_track_highlight(self):
        accent = QColor(ThemeManager.get_theme(self.current_theme)['accent_primary'])
        default_brush = QBrush()
        for i in range(self.playlist_tree.topLevelItemCount()):
            item = self.playlist_tree.topLevelItem(i)
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            is_current = (idx == self.current_index)
            font = item.font(0)
            if font.bold() != is_current:
                font.setBold(is_current)
                for col in range(4):
                    item.setFont(col, font)
            for col in range(4):
                item.setForeground(col, accent if is_current else default_brush)
        self._highlight_current_track()

    def _highlight_current_track(self):
        for i in range(self.playlist_tree.topLevelItemCount()):
            item = self.playlist_tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == self.current_index:
                self.playlist_tree.setCurrentItem(item)
                self.playlist_tree.scrollToItem(item)
                break
    
    def _on_position_changed(self, pos):
        if self._seeking:
            return
        dur = self.player.duration()
        if dur > 0:
            self.progress_slider.setValue(int(pos * 1000 / dur))
            self.current_time.setText(format_time(pos // 1000))
            self.total_time.setText(format_time(dur // 1000))
        self._check_cue_bounds(pos)
        self._features_position_changed(pos)

    def _check_cue_bounds(self, pos):
        end = getattr(self, "_cue_end", None)
        if end is not None and pos >= int(end * 1000) - 40:
            self._cue_end = None
            self._next_track()

    def _apply_cue_seek(self):
        if getattr(self, "_cue_seek_pending", False):
            self._cue_seek_pending = False
            self.player.setPosition(int(self._cue_start * 1000))

    def _on_duration_changed(self, dur):
        if dur > 0 and 0 <= self.current_index < len(self.playlist):
            self.playlist[self.current_index]['duration'] = dur // 1000
        self._features_duration_changed(dur)
    
    def _on_media_status(self, status):
        MS = QMediaPlayer.MediaStatus
        if status in (MS.LoadedMedia, MS.BufferedMedia):
            self._apply_cue_seek()
            self._play_errors = 0
            self._failed_path = None
            pending = getattr(self, "_pending_seek", None)
            if pending is not None:
                pos, resume = pending
                self._pending_seek = None
                if pos > 0:
                    self.player.setPosition(pos)
                if resume:
                    self.player.play()
        elif status == MS.InvalidMedia:
            self._handle_playback_failure()
        elif status == MS.EndOfMedia:
            if self.repeat_mode == 1:
                self._play_index(self.current_index)
            else:
                self._next_track()

    def _on_error(self, error, err_str):
        if error != QMediaPlayer.Error.NoError:
            self._handle_playback_failure()

    def _handle_playback_failure(self):
        path = None
        if 0 <= self.current_index < len(self.playlist):
            path = self.playlist[self.current_index]["path"]
        if path is not None and path == self._failed_path:
            return
        self._failed_path = path
        self._play_errors += 1
        name = os.path.basename(path) if path else ""
        self.status_info.setText(tr(self.current_language, "cannot_play").format(name=name))
        if not self.playlist or self._play_errors >= len(self.playlist):
            self.player.stop()
            self.is_playing = False
            self.status_info.setText(tr(self.current_language, "cannot_play_any"))
            return
        QTimer.singleShot(60, self._next_track)
    
    def _on_playback_state_changed(self, state):
        play = state == QMediaPlayer.PlaybackState.PlayingState
        self.visualizer.set_playing(play)
        self.vinyl.set_playing(play)
        if hasattr(self, "realtime_sink") and self.realtime_sink.is_active():
            self.realtime_sink.set_paused(not play)

    def _on_audio_buffer(self, buffer):
        if not self.is_playing or not buffer.isValid():
            return
        try:
            fmt = buffer.format()
            channels = max(1, fmt.channelCount())
            sample_rate = fmt.sampleRate()
            sample_format = fmt.sampleFormat()
            raw = bytes(buffer.data())

            if sample_format == QAudioFormat.SampleFormat.Int16:
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_format == QAudioFormat.SampleFormat.Int32:
                arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
            elif sample_format == QAudioFormat.SampleFormat.UInt8:
                arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            elif sample_format == QAudioFormat.SampleFormat.Float:
                arr = np.frombuffer(raw, dtype=np.float32)
            else:
                return

            if self.realtime_eq_enabled:
                self._feed_realtime_eq(arr, sample_rate, channels)

            if channels > 1:
                usable = (len(arr) // channels) * channels
                if usable <= 0:
                    return
                mono = arr[:usable].reshape(-1, channels).mean(axis=1)
            else:
                mono = arr

            self.visualizer.feed_audio(mono, sample_rate)
        except Exception:
            pass

    def _feed_realtime_eq(self, arr: np.ndarray, sample_rate: int, channels: int):
        fmt_key = (sample_rate, channels)
        if not self.realtime_sink.is_active() or self._realtime_eq_format != fmt_key:
            ok = self.realtime_sink.start(sample_rate, channels)
            self._realtime_eq_format = fmt_key
            if not ok:
                self.realtime_eq_enabled = False
                self.audio_output.setMuted(False)
                self.status_info.setText(tr(self.current_language, "eq_realtime_failed"))
                return
            self.audio_output.setMuted(True)
            self._arm_sink_probe()
        self.realtime_sink.push_float_frame(arr.astype(np.float32, copy=True), channels)

    def _on_slider_moved(self, value):
        dur = self.player.duration()
        if dur:
            self.current_time.setText(format_time(int(value / 1000 * dur) // 1000))

    def _seek(self):
        dur = self.player.duration()
        if dur:
            self.player.setPosition(int(self.progress_slider.value() / 1000 * dur))
        self._seeking = False
    
    def _on_volume_change(self, val):
        self.audio_output.setVolume(val / 100)
        if hasattr(self, "realtime_sink"):
            self.realtime_sink.set_volume(val / 100)
        self.vol_percent.setText(f"{val}%")
        self.settings["volume"] = val
        self._save_settings_soon()
    
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
            self._playlist_paths.clear()
            for item in data:
                if os.path.exists(item['path']):
                    self._add_to_playlist(item['path'])
            self.current_index = -1
            self._refresh_playlist()
    
    def _clear_playlist(self):
        t = self.current_language
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr(t, "confirm_clear_title"))
        box.setText(tr(t, "confirm_clear_text"))
        box.setInformativeText(tr(t, "confirm_clear_detail"))
        yes_btn = box.addButton(tr(t, "yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(tr(t, "no"), QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes_btn)
        if hasattr(self, "_stylesheet"):
            box.setStyleSheet(self._stylesheet)
        box.exec()
        if box.clickedButton() is not yes_btn:
            return

        self._stop()
        self.player.setSource(QUrl())
        self.playlist.clear()
        self._playlist_paths.clear()
        self.current_index = -1
        if hasattr(self, "queue"):
            self.queue.clear()
        self._group_icon_cache = {}
        self._view_context = None
        self._current_analysis = None
        if getattr(self, "waveform_bar", None) is not None:
            self.waveform_bar.clear()
            self._set_waveform_visible(False)
        if getattr(self, "analysis", None) is not None:
            try:
                self.analysis.stop()
            except Exception:
                pass
            self.analysis = None
        if getattr(self, "library", None) is not None:
            try:
                self.library.wipe()
            except Exception:
                log.exception("could not wipe library")
            try:
                from app.analysis import AnalysisService
                self.analysis = AnalysisService(self.library, self)
                self.analysis.ready.connect(self._on_analysis_ready)
            except Exception:
                self.analysis = None
        self._update_now_playing(-1)
        self._set_view_mode("all")
        self._show_ephemeral_status(tr(t, "library_cleared"))

    def _toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        key = "shuffle_on" if self.shuffle_mode else "shuffle_off"
        self._show_ephemeral_status(tr(self.current_language, key))

    def _cycle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        keys = ["repeat_off", "repeat_one", "repeat_all"]
        self._show_ephemeral_status(tr(self.current_language, keys[self.repeat_mode]))

    def _show_ephemeral_status(self, text: str, timeout_ms: int = 2500):
        self.status_info.setText(text)
        if not hasattr(self, "_status_revert_timer"):
            self._status_revert_timer = QTimer(self)
            self._status_revert_timer.setSingleShot(True)
            self._status_revert_timer.timeout.connect(self._revert_status_info)
        self._status_revert_timer.start(timeout_ms)

    def _revert_status_info(self):
        t = self.current_language
        if self.is_playing and 0 <= self.current_index < len(self.playlist):
            item = self.playlist[self.current_index]
            bitrate = item.get('bitrate', 0)
            sample_rate = item.get('sample_rate', 0)
            self.status_info.setText(f"{bitrate} kbps | {sample_rate/1000:.1f} kHz")
        elif self.playlist:
            self.status_info.setText(tr(t, "stopped"))
        else:
            self.status_info.setText(tr(t, "welcome"))
    
    def _on_search(self, text):
        self._pending_search = text
        if not hasattr(self, "_search_debounce_timer"):
            self._search_debounce_timer = QTimer(self)
            self._search_debounce_timer.setSingleShot(True)
            self._search_debounce_timer.timeout.connect(
                lambda: self._refresh_playlist(self._pending_search))
        self._search_debounce_timer.start(150)
    
    def _on_playlist_double_click(self, item):
        group = item.data(0, Qt.ItemDataRole.UserRole + 5)
        if group is not None:
            self._set_view_mode(self._view_mode, group)
            return
        browse_path = item.data(0, Qt.ItemDataRole.UserRole + 6)
        if browse_path is not None:
            if not os.path.exists(browse_path):
                return
            self._add_to_playlist(browse_path)
            self._after_playlist_added()
            for i, track in enumerate(self.playlist):
                if track.get("path") == browse_path:
                    self._play_index(i)
                    break
            return
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is not None:
            self._play_index(idx)
    def _show_context_menu(self, pos):
        item = self.playlist_tree.itemAt(pos) or self.playlist_tree.currentItem()
        if not item:
            return
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        self._show_track_menu(item, idx, self.playlist_tree.mapToGlobal(pos))

    def _edit_metadata(self, idx):
        if idx is None or not (0 <= idx < len(self.playlist)):
            return
        track = self.playlist[idx]
        theme = ThemeManager.get_theme(self.current_theme)
        dlg = MetadataEditorDialog(track, theme, self.current_language, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_fields is None:
            return

        args = dict(cover_action=dlg.cover_action, cover_bytes=dlg.cover_bytes,
                    cover_mime=dlg.cover_mime)
        ok, err = self.metadata_manager.write_metadata(track["path"], dlg.result_fields, **args)
        is_current = (idx == self.current_index)
        if not ok and is_current:
            pos = self.player.position()
            resume = self.is_playing and not self.is_paused
            self.player.stop()
            self.player.setSource(QUrl())
            QApplication.processEvents()
            ok, err = self.metadata_manager.write_metadata(track["path"], dlg.result_fields, **args)
            self._pending_seek = (pos, resume)
            self.player.setSource(QUrl.fromLocalFile(track["path"]))

        if ok:
            self._reload_track_metadata(idx)
            self.status_info.setText(tr(self.current_language, "md_saved"))
        else:
            self.status_info.setText(tr(self.current_language, "md_save_failed"))

    def _reload_track_metadata(self, idx):
        track = self.playlist[idx]
        meta = self.metadata_manager.get_metadata(track["path"])
        track.update({
            "title": meta.get("title", track["title"]),
            "artist": meta.get("artist", ""),
            "album": meta.get("album", ""),
            "genre": meta.get("genre", ""),
            "year": meta.get("year", ""),
            "track_number": meta.get("track_number", 0),
            "cover_data": meta.get("cover_art"),
            "cover_path": meta.get("cover_path", ""),
        })
        track.pop("_icon_cache", None)
        self._refresh_playlist(self._current_filter())
        if idx == self.current_index:
            self._update_now_playing(idx)
    
    def _remove_selected_confirmed(self):
        return self._confirm("remove_action",
                             tr(self.current_language, "confirm_remove_selected"))

    def _remove_selected(self):
        if self._view_mode != "all":
            return
        selected = self.playlist_tree.selectedItems()
        if not selected:
            return
        if not self._remove_selected_confirmed():
            return
        indices = sorted([it.data(0, Qt.ItemDataRole.UserRole) for it in selected
                          if it.data(0, Qt.ItemDataRole.UserRole) is not None], reverse=True)
        removed_current = False
        for idx in indices:
            if idx == self.current_index:
                self._stop()
                removed_current = True
            self._playlist_paths.discard(self.playlist[idx]['path'])
            del self.playlist[idx]
            if self.current_index > idx:
                self.current_index -= 1
            elif self.current_index == idx:
                self.current_index = -1
        if removed_current:
            self.player.setSource(QUrl())
            self._update_now_playing(-1)
        self._refresh_playlist(self.global_search.text())
    
    def _toggle_visibility(self):
        self.setVisible(not self.isVisible())
    
    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))
    
    def _load_last_session(self):
        sess = SESSION_PATH if SESSION_PATH.exists() else _LEGACY_SESSION_PATH
        if not sess.exists():
            return
        try:
            with open(sess, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            log.warning("Could not read last session from %s", sess, exc_info=True)
            return
        if not isinstance(data, list):
            return
        for item in data:
            path = item.get('path', '') if isinstance(item, dict) else ''
            if path and os.path.exists(path):
                self._add_to_playlist(path)
        self._refresh_playlist()

    def _save_session(self):
        data = [{k: item[k] for k in ('path', 'title', 'artist')} for item in self.playlist]
        write_json_atomic(SESSION_PATH, data)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive()
        if not hasattr(self, "_resize_debounce_timer"):
            self._resize_debounce_timer = QTimer(self)
            self._resize_debounce_timer.setSingleShot(True)
            self._resize_debounce_timer.timeout.connect(self._on_resize_settled)
        self._resize_debounce_timer.start(120)

    def _sync_waveform_geometry(self):
        host = getattr(self, "_waveform_host", None)
        if host is None or not hasattr(self, "progress_slider"):
            return
        layout = host.layout()
        if layout is None:
            return
        slider = self.progress_slider
        frame = slider.parentWidget()
        try:
            left = slider.mapTo(frame, slider.rect().topLeft()).x()
            right = frame.width() - (left + slider.width())
        except Exception:
            return
        left = max(0, left)
        right = max(0, right)
        current = layout.contentsMargins()
        if current.left() != left or current.right() != right:
            layout.setContentsMargins(left, 0, right, 4)

    def _on_resize_settled(self):
        self._update_playlist_column_widths()

    def closeEvent(self, event):
        self._flush_settings_save()
        self._save_session()
        self.player.stop()
        if hasattr(self, "realtime_sink"):
            self.realtime_sink.stop()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        self._features_shutdown()
        event.accept()