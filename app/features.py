import logging
import os
import time
import zipfile

from PyQt6.QtCore import Qt, QTimer, QSize, QRectF, QDir, QUrl, QStandardPaths
from PyQt6.QtGui import (QColor, QDesktopServices, QFileSystemModel, QKeySequence,
                         QPainter, QPixmap, QShortcut)
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTreeView, QVBoxLayout, QWidget,
)

from . import lyrics as lyrics_mod
from . import mpris
from . import native
from . import organize
from . import playlists
from . import radio
from . import themes
from . import topchart
from .analysis import AnalysisService, unpack_waveform
from .audio.devices import SYSTEM_DEFAULT, icon_for as device_icon_for
from .filterquery import help_lines
from .i18n import tr
from .library import Library
from .ui import icons
from .ui.widgets import WaveformSeekBar
from .utils import AUDIO_EXTENSIONS, PLAYLIST_EXTENSIONS, format_time, safe_mtime

log = logging.getLogger("parch_mp.features")

RATING_MAX = 5
SLEEP_PRESETS = (5, 10, 15, 30, 45, 60, 90, 120)
SPEEDS = (0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0)
ANALYSIS_DELAY_MS = 4000


class FeatureMixin:

    def _init_features(self):
        self._features_ready = False
        self.library = None
        self.analysis = None
        self.queue = []
        self.playback_speed = 1.0
        self._lyrics_lines = []
        self._lyrics_synced = False
        self._lyrics_index = -1
        self._lyrics_widget = None
        self._sleep_deadline = 0.0
        self._current_analysis = None
        self._device_announced = None
        self._pending_analysis = None

        try:
            self.library = Library()
        except Exception:
            log.exception("library unavailable")

        if self.library is not None:
            try:
                self.analysis = AnalysisService(self.library, self)
                self.analysis.ready.connect(self._on_analysis_ready)
            except Exception:
                log.exception("analysis service unavailable")
                self.analysis = None

        self.replaygain_enabled = bool(self.settings.get("replaygain", False))

        try:
            self._build_waveform_bar()
        except Exception:
            log.exception("waveform bar unavailable")
            self.waveform_bar = None
        try:
            self._setup_feature_shortcuts()
        except Exception:
            log.exception("feature shortcuts unavailable")

        self._sleep_timer = QTimer(self)
        self._sleep_timer.setInterval(1000)
        self._sleep_timer.timeout.connect(self._tick_sleep_timer)

        self._lyrics_timer = QTimer(self)
        self._lyrics_timer.setInterval(250)
        self._lyrics_timer.timeout.connect(self._tick_lyrics)

        self._sink_probe = QTimer(self)
        self._sink_probe.setSingleShot(True)
        self._sink_probe.setInterval(900)
        self._sink_probe.timeout.connect(self._verify_sink_output)

        self._analysis_timer = QTimer(self)
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.setInterval(ANALYSIS_DELAY_MS)
        self._analysis_timer.timeout.connect(self._start_pending_analysis)

        self._features_ready = True
        self._index_playlist_into_library()

    def _build_waveform_bar(self):
        self.waveform_bar = WaveformSeekBar()
        self.waveform_bar.setFixedHeight(30)
        self.waveform_bar.seek_requested.connect(self._seek_fraction)
        self.waveform_bar.setVisible(False)

        progress_frame = self.progress_slider.parentWidget()
        progress_layout = progress_frame.layout()
        inset = self.current_time.width() or 45
        gap = progress_layout.spacing() if progress_layout else 8

        self._waveform_host = QWidget()
        host_layout = QHBoxLayout(self._waveform_host)
        host_layout.setContentsMargins(inset + gap, 0, inset + gap, 4)
        host_layout.setSpacing(0)
        host_layout.addWidget(self.waveform_bar)
        self._waveform_host.setVisible(False)

        outer = progress_frame.parentWidget().layout()
        outer.insertWidget(outer.indexOf(progress_frame) + 1, self._waveform_host)

    def _setup_feature_shortcuts(self):
        pairs = (
            ("Ctrl+F", lambda: self.search_input.setFocus()),
            ("Ctrl+Shift+F", self._toggle_favorite_current),
            ("Ctrl+Q", self._open_queue_dialog),
            ("Ctrl+G", self._open_gallery),
            ("Ctrl+Y", self._open_lyrics),
            ("Ctrl+I", self._open_stats),
            ("Ctrl+E", self._open_equalizer_dialog),
            ("Ctrl+M", self._toggle_waveform_mode),
            ("Ctrl+D", self._show_device_menu),
        )
        self._feature_shortcuts = []
        for keys, slot in pairs:
            try:
                shortcut = QShortcut(QKeySequence(keys), self)
                shortcut.activated.connect(slot)
                self._feature_shortcuts.append(shortcut)
            except Exception:
                pass

    # audio devices
    def _apply_audio_device(self, device):
        try:
            if device is None or device.isNull():
                self.audio_output.setDevice(QMediaDevices.defaultAudioOutput())
            else:
                self.audio_output.setDevice(device)
        except Exception:
            log.exception("could not set output device on QAudioOutput")
        try:
            self.realtime_sink.set_output_device(device)
        except Exception:
            log.exception("could not set output device on realtime sink")

    def _on_audio_device_changed(self, device):
        self._apply_audio_device(device)
        try:
            name = self.device_manager.describe(device)
        except Exception:
            return
        if self._device_announced_ready() and self._device_announced != name:
            self._device_announced = name
            self._show_ephemeral_status(
                f"{tr(self.current_language, 'audio_output')}: {name}")
        fmt = getattr(self, "_realtime_eq_format", None)
        if self.realtime_eq_enabled and fmt:
            try:
                self.realtime_sink.restart(fmt[0], fmt[1])
            except Exception:
                log.exception("could not restart sink on new device")

    def _device_announced_ready(self):
        return hasattr(self, "status_info") and getattr(self, "_features_ready", False)

    def _on_audio_devices_listed(self):
        try:
            self.device_manager.refresh()
        except Exception:
            pass

    def _verify_sink_output(self):
        if not getattr(self, "realtime_eq_enabled", False):
            return
        try:
            producing = self.realtime_sink.is_producing()
        except Exception:
            producing = False
        if not producing:
            log.warning("realtime sink produced no audio; reverting to direct output")
            self._on_sink_stalled()

    def _arm_sink_probe(self):
        try:
            self._sink_probe.start()
        except Exception:
            pass

    def _set_realtime_eq(self, enabled):
        self.settings["realtime_eq"] = bool(enabled)
        self._save_settings_soon()
        if enabled:
            self.realtime_eq_enabled = True
            self._realtime_eq_format = None
        else:
            try:
                self.realtime_sink.stop()
            except Exception:
                pass
            self.realtime_eq_enabled = False
            self._realtime_eq_format = None
            try:
                self.audio_output.setMuted(False)
            except Exception:
                pass
        self._show_ephemeral_status(
            self._state_text("realtime_eq", enabled))

    def _state_text(self, key, enabled):
        lang = self.current_language
        state = tr(lang, "state_on") if enabled else tr(lang, "state_off")
        return f"{tr(lang, key)}: {state}"

    def _on_sink_stalled(self):
        log.warning("audio sink stalled, switching to direct output")
        try:
            self.realtime_sink.stop()
        except Exception:
            pass
        self.realtime_eq_enabled = False
        self._realtime_eq_format = None
        try:
            self.audio_output.setMuted(False)
        except Exception:
            pass
        if self._device_announced_ready():
            self._show_ephemeral_status(
                tr(self.current_language, "eq_realtime_failed"), 4000)

    def _build_device_menu(self, parent_menu=None):
        lang = self.current_language
        menu = QMenu(tr(lang, "audio_output"), parent_menu or self)
        menu.setStyleSheet(self._menu_style())
        try:
            entries = self.device_manager.entries()
            current = self.device_manager.preferred_id()
        except Exception:
            entries, current = [], SYSTEM_DEFAULT

        for identifier, device, kind in entries:
            if identifier == SYSTEM_DEFAULT:
                label = tr(lang, "device_system_default")
                try:
                    default_name = self.device_manager.describe(
                        self.device_manager.default_device())
                    label = f"{label} ({default_name})"
                except Exception:
                    pass
                icon_name = "speaker"
            else:
                label = device.description()
                icon_name = device_icon_for(kind)
            action = menu.addAction(self._icon(icon_name), label)
            action.setCheckable(True)
            action.setChecked(identifier == current)
            action.triggered.connect(
                lambda _c=False, i=identifier: self._select_audio_device(i))

        if not entries:
            menu.addAction(tr(lang, "device_none")).setEnabled(False)
        menu.addSeparator()
        refresh = menu.addAction(self._icon("repeat"), tr(lang, "device_refresh"))
        refresh.triggered.connect(self._on_audio_devices_listed)
        return menu

    def _show_device_menu(self):
        menu = self._build_device_menu()
        anchor = getattr(self, "tools_btn", None) or self
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _select_audio_device(self, identifier):
        self.settings["audio_device"] = identifier
        self._save_settings_soon()
        try:
            self.device_manager.set_preferred_id(identifier)
        except Exception:
            log.exception("could not select audio device")
        if not self.realtime_eq_enabled:
            self.realtime_eq_enabled = True
            self._realtime_eq_format = None

    # helpers
    def _device_icon_name(self):
        try:
            from .audio.devices import kind_of
            return device_icon_for(kind_of(self.device_manager.resolve()))
        except Exception:
            return "speaker"

    def _menu_style(self):
        from .core import ThemeManager
        return self._track_menu_style(ThemeManager.get_theme(self.current_theme))

    def _accent_colour(self):
        from .core import ThemeManager
        return ThemeManager.get_theme(self.current_theme).get("accent_primary", "#1DB954")

    def _icon(self, name, size=18, color=None):
        return icons.icon(name, size, color or self._icon_colour())

    def _icon_colour(self):
        from .core import ThemeManager
        return ThemeManager.get_theme(self.current_theme).get("text_primary", "#e8ecf4")

    def _index_playlist_into_library(self):
        if self.library is None or not self.playlist:
            return
        try:
            self.library.upsert_many([(t["path"], t) for t in self.playlist])
        except Exception:
            log.exception("could not index playlist")

    def _library_row(self, path):
        if self.library is None or not path:
            return None
        try:
            return self.library.get(path)
        except Exception:
            return None

    def _current_path(self):
        if 0 <= self.current_index < len(self.playlist):
            return self.playlist[self.current_index].get("path")
        return None

    # track lifecycle
    def _features_track_started(self, idx):
        if not getattr(self, "_features_ready", False):
            return
        try:
            self._track_started_inner(idx)
        except Exception:
            log.exception("feature hook failed on track start")

    def _track_started_inner(self, idx):
        if not (0 <= idx < len(self.playlist)):
            return
        track = self.playlist[idx]
        path = track.get("path")
        if not path:
            return

        if self.library is not None:
            try:
                self.library.upsert(path, track)
                self.library.note_play(path)
            except Exception:
                log.exception("library update failed")

        self._current_analysis = None
        if self.waveform_bar is not None:
            self.waveform_bar.clear()
        self._apply_cached_analysis(path)

        if self.analysis is not None:
            self._pending_analysis = path
            self._analysis_timer.start()

        self._load_lyrics(path)
        self._apply_replaygain(path)
        self._apply_speed()
        self._extra_track_started(idx)

    def _start_pending_analysis(self):
        path = self._pending_analysis
        self._pending_analysis = None
        if not path or self.analysis is None:
            return
        if path != self._current_path():
            return
        try:
            self.analysis.enqueue(path)
        except Exception:
            log.exception("could not queue analysis")

    def _apply_cached_analysis(self, path):
        if self.library is None or self.waveform_bar is None:
            return
        try:
            row = self.library.load_analysis(path, safe_mtime(path))
        except Exception:
            row = None
        if not row:
            self._set_waveform_visible(False)
            return
        self._current_analysis = row
        wave = unpack_waveform(row.get("waveform"))
        mood = row.get("moodbar") or b""
        self.waveform_bar.set_analysis(wave, mood)
        self.waveform_bar.set_theme(self.current_theme, self._accent_colour())
        self._set_waveform_visible(bool(self.settings.get("waveform_bar", True))
                                   and (wave.size > 0 or len(mood) > 0))

    def _set_waveform_visible(self, visible):
        visible = bool(visible)
        if self.waveform_bar is not None:
            self.waveform_bar.setVisible(visible)
        host = getattr(self, "_waveform_host", None)
        if host is not None:
            host.setVisible(visible)

    def _on_analysis_ready(self, path, result):
        try:
            if path == self._current_path():
                self._apply_cached_analysis(path)
                self._apply_replaygain(path)
            self._refresh_playlist(self._current_filter())
        except Exception:
            log.exception("could not apply analysis result")

    def _apply_replaygain(self, path):
        if not hasattr(self, "eq_engine"):
            return
        gain = 0.0
        if getattr(self, "replaygain_enabled", False):
            row = self._library_row(path)
            if row:
                try:
                    gain = float(row.get("replaygain") or 0.0)
                except (TypeError, ValueError):
                    gain = 0.0
        gain = max(-15.0, min(6.0, gain))
        try:
            self.eq_engine.set_replaygain_db(gain)
        except Exception:
            log.exception("could not apply replaygain")

    def _apply_speed(self):
        try:
            self.player.setPlaybackRate(float(self.playback_speed))
        except Exception:
            pass

    def _seek_fraction(self, fraction):
        duration = self.player.duration()
        if duration > 0:
            self.player.setPosition(int(max(0.0, min(1.0, fraction)) * duration))

    def _features_position_changed(self, position_ms):
        bar = getattr(self, "waveform_bar", None)
        if bar is not None and bar.isVisible():
            bar.set_position(position_ms / 1000.0)

    def _features_duration_changed(self, duration_ms):
        bar = getattr(self, "waveform_bar", None)
        if bar is not None:
            bar.set_duration(duration_ms / 1000.0)

    # queue
    def _queue_paths(self, paths, front=False):
        paths = [p for p in paths if p]
        if not paths:
            return
        if front:
            self.queue[0:0] = paths
        else:
            self.queue.extend(paths)
        self._show_ephemeral_status(
            f"{tr(self.current_language, 'queue')}: {len(self.queue)}")

    def _queue_take(self):
        while getattr(self, "queue", None):
            path = self.queue.pop(0)
            for i, track in enumerate(self.playlist):
                if track.get("path") == path:
                    return i
        return -1

    def _open_queue_dialog(self):
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "queue"))
        dialog.resize(520, 420)
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lookup = {t.get("path"): t for t in self.playlist}
        for path in self.queue:
            track = lookup.get(path, {})
            label = track.get("title") or os.path.basename(path)
            artist = track.get("artist") or ""
            item = QListWidgetItem(f"{label}  -  {artist}" if artist else label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            listing.addItem(item)
        if not self.queue:
            listing.addItem(QListWidgetItem(tr(lang, "queue_empty")))
        layout.addWidget(listing)

        row = QHBoxLayout()
        remove = QPushButton(tr(lang, "remove_word"))
        clear = QPushButton(tr(lang, "clear_word"))
        row.addWidget(remove)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)

        def do_remove():
            for item in listing.selectedItems():
                path = item.data(Qt.ItemDataRole.UserRole)
                if path in self.queue:
                    self.queue.remove(path)
                listing.takeItem(listing.row(item))

        def do_clear():
            self.queue.clear()
            listing.clear()

        remove.clicked.connect(do_remove)
        clear.clicked.connect(do_clear)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    # favourites and ratings
    def _toggle_favorite_current(self):
        path = self._current_path()
        if not path or self.library is None:
            return
        state = self.library.toggle_favorite(path)
        lang = self.current_language
        self._show_ephemeral_status(
            tr(lang, "favourite_add") if state else tr(lang, "favourite_remove"))
        self._refresh_playlist(self._current_filter())

    def _toggle_favorite_path(self, path):
        if not path or self.library is None:
            return
        self.library.toggle_favorite(path)
        self._refresh_playlist(self._current_filter())

    def _set_rating(self, path, rating):
        if self.library is None or not path:
            return
        self.library.set_rating(path, rating)
        self._refresh_playlist(self._current_filter())

    def _is_favorite(self, path):
        row = self._library_row(path)
        return bool(row and row.get("favorite"))

    def _feature_menu_entries(self, menu, idx):
        if self.library is None or not (0 <= idx < len(self.playlist)):
            return
        lang = self.current_language
        path = self.playlist[idx].get("path")
        row = self._library_row(path) or {}

        menu.addSeparator()
        queue_next = menu.addAction(self._icon("queue"), tr(lang, "queue_next"))
        queue_next.triggered.connect(lambda: self._queue_paths([path], front=True))
        queue_add = menu.addAction(self._icon("plus"), tr(lang, "queue_add"))
        queue_add.triggered.connect(lambda: self._queue_paths([path]))

        favourite = row.get("favorite")
        fav = menu.addAction(
            self._icon("heart_filled" if favourite else "heart"),
            tr(lang, "favourite_remove") if favourite else tr(lang, "favourite_add"))
        fav.triggered.connect(lambda: self._toggle_favorite_path(path))

        rating_menu = menu.addMenu(self._icon("star"), tr(lang, "rating"))
        rating_menu.setStyleSheet(self._menu_style())
        for value in range(RATING_MAX, -1, -1):
            label = ("★" * value + "☆" * (RATING_MAX - value)) if value \
                else tr(lang, "rating_none")
            act = rating_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(int(row.get("rating") or 0) == value)
            act.triggered.connect(lambda _c=False, v=value, p=path: self._set_rating(p, v))

        bpm = int(row.get("bpm") or 0)
        info = menu.addAction(
            f"{tr(lang, 'plays')}: {int(row.get('play_count') or 0)}"
            + (f"   {tr(lang, 'bpm_word')}: {bpm}" if bpm else ""))
        info.setEnabled(False)

    # lyrics
    def _load_lyrics(self, path):
        try:
            self._lyrics_lines, self._lyrics_synced = lyrics_mod.load(path)
        except Exception:
            self._lyrics_lines, self._lyrics_synced = [], False
        self._lyrics_index = -1
        if self._lyrics_widget is not None:
            self._fill_lyrics_widget()

    def _fill_lyrics_widget(self):
        widget = self._lyrics_widget
        if widget is None:
            return
        widget.clear()
        if not self._lyrics_lines:
            widget.addItem(QListWidgetItem(tr(self.current_language, "lyrics_none")))
            return
        for stamp, text in self._lyrics_lines:
            item = QListWidgetItem(text or " ")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if stamp is not None:
                item.setData(Qt.ItemDataRole.UserRole, stamp)
            widget.addItem(item)

    def _tick_lyrics(self):
        widget = self._lyrics_widget
        if widget is None or not self._lyrics_synced or not self._lyrics_lines:
            return
        position = self.player.position() / 1000.0
        index = lyrics_mod.active_index(self._lyrics_lines, position)
        if index != self._lyrics_index and index >= 0:
            self._lyrics_index = index
            widget.setCurrentRow(index)
            widget.scrollToItem(widget.item(index),
                                QAbstractItemView.ScrollHint.PositionAtCenter)

    def _open_lyrics(self):
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "lyrics"))
        dialog.resize(460, 560)
        layout = QVBoxLayout(dialog)

        header = QLabel()
        if 0 <= self.current_index < len(self.playlist):
            track = self.playlist[self.current_index]
            header.setText(f"{track.get('title','')}\n{track.get('artist','')}")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        self._lyrics_widget = QListWidget()
        self._lyrics_widget.setWordWrap(True)
        layout.addWidget(self._lyrics_widget, 1)

        def jump(item):
            stamp = item.data(Qt.ItemDataRole.UserRole)
            if stamp is not None:
                self.player.setPosition(int(float(stamp) * 1000))

        self._lyrics_widget.itemDoubleClicked.connect(jump)
        path = self._current_path()
        if path and not self._lyrics_lines:
            self._load_lyrics(path)
        self._fill_lyrics_widget()
        self._lyrics_timer.start()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        self._lyrics_timer.stop()
        self._lyrics_widget = None

    # gallery
    def _open_gallery(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "gallery"))
        dialog.resize(900, 620)
        layout = QVBoxLayout(dialog)

        search = QLineEdit()
        search.setPlaceholderText(tr(lang, "filter_albums"))
        layout.addWidget(search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(14)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

        albums = self.library.albums()

        def populate(text=""):
            while grid.count():
                item = grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            needle = (text or "").lower()
            shown = 0
            for entry in albums:
                label = f"{entry.get('aartist') or ''} {entry.get('album') or ''}".lower()
                if needle and needle not in label:
                    continue
                grid.addWidget(self._album_card(entry, dialog), shown // 5, shown % 5)
                shown += 1
                if shown >= 200:
                    break

        search.textChanged.connect(populate)
        populate()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _album_card(self, entry, parent):
        card = QWidget(parent)
        box = QVBoxLayout(card)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(4)

        art = QLabel()
        art.setFixedSize(140, 140)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = self._cover_for(entry.get("sample"))
        if pix is not None and not pix.isNull():
            art.setPixmap(pix.scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation))
        else:
            canvas = QPixmap(140, 140)
            canvas.fill(QColor("#2a2e37"))
            painter = QPainter(canvas)
            icons.paint(painter, "disc", QRectF(45, 45, 50, 50), QColor("#6d7688"), 2.0)
            painter.end()
            art.setPixmap(canvas)
        box.addWidget(art)

        title = QLabel(entry.get("album") or "")
        title.setWordWrap(True)
        title.setMaximumWidth(140)
        artist = QLabel(entry.get("aartist") or "")
        artist.setWordWrap(True)
        artist.setMaximumWidth(140)
        artist.setStyleSheet("color: #8a93a6;")
        box.addWidget(title)
        box.addWidget(artist)

        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mouseDoubleClickEvent = lambda _e, e=entry: self._play_album(e)
        return card

    def _cover_for(self, path):
        if not path:
            return None
        try:
            meta = self.metadata_manager.get_metadata(path)
            data = meta.get("cover_art") or meta.get("cover")
            if data:
                pix = QPixmap()
                pix.loadFromData(data)
                return pix
        except Exception:
            pass
        return None

    def _play_album(self, entry):
        tracks = self.library.album_tracks(entry.get("aartist"), entry.get("album"))
        paths = [t["path"] for t in tracks if t.get("path") and os.path.exists(t["path"])]
        if not paths:
            return
        for path in paths:
            self._add_to_playlist(path)
        self._after_playlist_added()
        for i, track in enumerate(self.playlist):
            if track.get("path") == paths[0]:
                self._play_index(i)
                break

    # statistics
    def _open_stats(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "statistics"))
        dialog.resize(620, 560)
        layout = QVBoxLayout(dialog)

        stats = self.library.stats()
        listened = float(stats.get("listened") or 0)
        summary = QLabel(
            f"{tr(lang, 'tracks_word')}: {stats.get('tracks', 0)}    "
            f"{tr(lang, 'albums_word')}: {stats.get('albums', 0)}    "
            f"{tr(lang, 'artists_word')}: {stats.get('artists', 0)}\n"
            f"{tr(lang, 'plays')}: {stats.get('plays', 0)}    "
            f"{tr(lang, 'listening_time')}: {format_time(int(listened))}"
        )
        layout.addWidget(summary)

        tabs = QComboBox()
        tabs.addItems([tr(lang, "top_tracks"), tr(lang, "top_artists"),
                       tr(lang, "recently_played"), tr(lang, "recently_added"),
                       tr(lang, "never_played"), tr(lang, "favourites")])
        layout.addWidget(tabs)

        listing = QListWidget()
        layout.addWidget(listing, 1)

        def label_of(row):
            return f"{row.get('artist') or '?'} - {row.get('title') or '?'}"

        def refresh(index):
            listing.clear()
            if index == 0:
                for row in self.library.top_tracks(60):
                    listing.addItem(f"{row.get('play_count', 0):>4}  {label_of(row)}")
            elif index == 1:
                for row in self.library.top_artists(40):
                    listing.addItem(f"{row.get('plays', 0):>4}  {row.get('name')}")
            elif index == 2:
                for row in self.library.recently_played(60):
                    when = time.strftime("%Y-%m-%d %H:%M",
                                         time.localtime(row.get("last_played") or 0))
                    listing.addItem(f"{when}   {label_of(row)}")
            elif index == 3:
                for row in self.library.recently_added(60):
                    listing.addItem(label_of(row))
            elif index == 4:
                for row in self.library.never_played(60):
                    listing.addItem(label_of(row))
            else:
                for row in self.library.favorites():
                    listing.addItem(label_of(row))

        tabs.currentIndexChanged.connect(refresh)
        refresh(0)

        clock = self.library.listening_clock()
        peak = max(clock) if clock else 0
        if peak:
            bars = QLabel(" ".join(
                f"{h:02d}:{'█' * max(0, round(count / peak * 6))}"
                for h, count in enumerate(clock) if count))
            bars.setWordWrap(True)
            bars.setStyleSheet("color: #8a93a6;")
            layout.addWidget(bars)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # smart search
    def _open_smart_search(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "smart_search"))
        dialog.resize(640, 520)
        layout = QVBoxLayout(dialog)

        query = QLineEdit()
        query.setPlaceholderText(help_lines()[0])
        layout.addWidget(query)

        hint = QLabel("\n".join(help_lines()))
        hint.setStyleSheet("color: #8a93a6;")
        layout.addWidget(hint)

        listing = QListWidget()
        listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(listing, 1)

        def run():
            listing.clear()
            try:
                rows = self.library.search(query.text(), limit=500)
            except Exception:
                log.exception("smart search failed")
                return
            for row in rows:
                item = QListWidgetItem(
                    f"{row.get('artist') or '?'} - {row.get('title') or '?'}"
                    f"   [{row.get('album') or ''}]")
                item.setData(Qt.ItemDataRole.UserRole, row.get("path"))
                listing.addItem(item)
            hint.setText(tr(lang, "matches").format(n=len(rows)))

        query.returnPressed.connect(run)
        query.textChanged.connect(lambda: QTimer.singleShot(220, run))

        row = QHBoxLayout()
        add = QPushButton(tr(lang, "add_to_playlist"))
        save = QPushButton(tr(lang, "save_smart_playlist"))
        row.addWidget(add)
        row.addWidget(save)
        row.addStretch(1)
        layout.addLayout(row)

        def do_add():
            items = listing.selectedItems() or [listing.item(i) for i in range(listing.count())]
            for item in items:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    self._add_to_playlist(path)
            self._after_playlist_added()
            dialog.accept()

        def do_save():
            text = query.text().strip()
            if text:
                self.library.create_playlist(text[:40], kind="smart", query=text)
                self._show_ephemeral_status(tr(lang, "smart_playlist_saved"))

        add.clicked.connect(do_add)
        save.clicked.connect(do_save)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # timers and speed
    def _tick_sleep_timer(self):
        if self._sleep_deadline <= 0:
            return
        remaining = self._sleep_deadline - time.time()
        if remaining <= 0:
            self._sleep_deadline = 0.0
            self._sleep_timer.stop()
            self.player.pause()
            self.is_paused = True
            self._update_transport_icons()
            self._show_ephemeral_status(tr(self.current_language, "sleep_done"))

    def _start_sleep_timer(self, minutes):
        self._sleep_deadline = time.time() + minutes * 60
        self._sleep_timer.start()
        self._show_ephemeral_status(
            tr(self.current_language, "sleep_set").format(n=minutes))

    def _cancel_sleep_timer(self):
        self._sleep_deadline = 0.0
        self._sleep_timer.stop()
        self._show_ephemeral_status(tr(self.current_language, "sleep_off"))

    def _set_speed(self, speed):
        self.playback_speed = float(speed)
        self._apply_speed()
        self._show_ephemeral_status(
            tr(self.current_language, "speed_set").format(v=f"{speed:g}"))

    def _toggle_waveform_mode(self):
        if self.waveform_bar is None or not self.waveform_bar.has_data():
            return
        mode = self.waveform_bar.toggle_mode()
        lang = self.current_language
        self._show_ephemeral_status(
            tr(lang, "moodbar") if mode == "mood" else tr(lang, "waveform"))

    # archive import
    def _import_archive(self):
        lang = self.current_language
        path, _ = QFileDialog.getOpenFileName(
            self, tr(lang, "import_archive"), "", "Archives (*.zip);;All Files (*)")
        if not path:
            return
        target = os.path.join(os.path.dirname(path),
                              os.path.splitext(os.path.basename(path))[0])
        try:
            os.makedirs(target, exist_ok=True)
            with zipfile.ZipFile(path) as archive:
                archive.extractall(target)
        except Exception as exc:
            QMessageBox.warning(self, tr(lang, "import_archive"), str(exc))
            return
        from .utils import AUDIO_EXTENSIONS
        added = 0
        for root, _dirs, files in os.walk(target):
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                    if self._add_to_playlist(os.path.join(root, name)):
                        added += 1
        self._after_playlist_added()
        self._show_ephemeral_status(tr(lang, "imported_tracks").format(n=added))

    # tools menu
    def _show_tools_menu(self):
        lang = self.current_language
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())

        menu.addAction(self._icon("search"), tr(lang, "smart_search"),
                       self._open_smart_search)
        menu.addAction(self._icon("grid"), tr(lang, "gallery"), self._open_gallery)
        menu.addAction(self._icon("folder_open"), tr(lang, "file_browser"),
                       self._open_file_browser)
        menu.addAction(self._icon("chart"), tr(lang, "statistics"), self._open_stats)
        menu.addAction(self._icon("cover"), tr(lang, "topchart"), self._open_topchart)
        menu.addSeparator()

        menu.addAction(self._icon("queue"), tr(lang, "queue"), self._open_queue_dialog)
        menu.addAction(self._icon("lyrics"), tr(lang, "lyrics"), self._open_lyrics)
        menu.addAction(self._icon("globe"), tr(lang, "radio"), self._open_radio)
        menu.addSeparator()

        device_menu = self._build_device_menu(menu)
        device_menu.setIcon(self._icon("speaker"))
        try:
            device_menu.setTitle(
                f"{tr(lang, 'audio_output')}: {self.device_manager.describe()}")
        except Exception:
            pass
        menu.addMenu(device_menu)

        speed_menu = menu.addMenu(
            self._icon("speed"),
            f"{tr(lang, 'playback_speed')}: {self.playback_speed:g}x")
        speed_menu.setStyleSheet(self._menu_style())
        for value in SPEEDS:
            act = speed_menu.addAction(f"{value:g}x")
            act.setCheckable(True)
            act.setChecked(abs(self.playback_speed - value) < 1e-6)
            act.triggered.connect(lambda _c=False, v=value: self._set_speed(v))

        gain = menu.addAction(self._icon("headphones"),
                              self._state_text("normalisation", self.replaygain_enabled))
        gain.setCheckable(True)
        gain.setChecked(self.replaygain_enabled)
        gain.toggled.connect(self._toggle_replaygain)

        realtime = bool(self.settings.get("realtime_eq", True))
        rt = menu.addAction(self._icon("equalizer"),
                            self._state_text("realtime_eq", realtime))
        rt.setCheckable(True)
        rt.setChecked(realtime)
        rt.toggled.connect(self._set_realtime_eq)
        menu.addSeparator()

        wave_on = bool(self.settings.get("waveform_bar", True))
        wave = menu.addAction(self._icon("wave"),
                              self._state_text("waveform_bar", wave_on))
        wave.setCheckable(True)
        wave.setChecked(wave_on)
        wave.toggled.connect(self._toggle_waveform_bar)

        mode_now = self.waveform_bar.mode if self.waveform_bar is not None else "wave"
        mood = menu.addAction(
            self._icon("cover"),
            f"{tr(lang, 'moodbar')} / {tr(lang, 'waveform')}: "
            f"{tr(lang, 'moodbar') if mode_now == 'mood' else tr(lang, 'waveform')}")
        mood.triggered.connect(self._toggle_waveform_mode)

        sleep_active = getattr(self, "_sleep_deadline", 0) > 0
        sleep_menu = menu.addMenu(
            self._icon("timer"), self._state_text("sleep_timer", sleep_active))
        sleep_menu.setStyleSheet(self._menu_style())
        for minutes in SLEEP_PRESETS:
            act = sleep_menu.addAction(tr(lang, "minutes_short").format(n=minutes))
            act.triggered.connect(lambda _c=False, m=minutes: self._start_sleep_timer(m))
        sleep_menu.addSeparator()
        sleep_menu.addAction(tr(lang, "sleep_cancel"), self._cancel_sleep_timer)

        theme_menu = self._build_theme_menu(menu)
        theme_menu.setIcon(self._icon("moon"))
        theme_menu.setTitle(
            f"{tr(lang, 'theme_menu')}: "
            f"{self._theme_label(self.current_theme, themes.catalogue().get(self.current_theme, {}))}")
        menu.addMenu(theme_menu)

        notify_on = bool(self.settings.get("notifications", True))
        notify = menu.addAction(self._icon("info"),
                                self._state_text("notifications", notify_on))
        notify.setCheckable(True)
        notify.setChecked(notify_on)
        notify.toggled.connect(self._toggle_notifications)

        menu.addSeparator()
        menu.addAction(self._icon("import"), tr(lang, "import_archive"),
                       self._import_archive)
        menu.addAction(self._icon("edit"), tr(lang, "organise"), self._open_organiser)
        info = menu.addAction(
            f"{tr(lang, 'plays')}: {int(row.get('play_count') or 0)}"
            + (f"   {tr(lang, 'bpm_word')}: {bpm}" if bpm else ""))
        info.setEnabled(False)

    # lyrics
    def _load_lyrics(self, path):
        try:
            self._lyrics_lines, self._lyrics_synced = lyrics_mod.load(path)
        except Exception:
            self._lyrics_lines, self._lyrics_synced = [], False
        self._lyrics_index = -1
        if self._lyrics_widget is not None:
            self._fill_lyrics_widget()

    def _fill_lyrics_widget(self):
        widget = self._lyrics_widget
        if widget is None:
            return
        widget.clear()
        if not self._lyrics_lines:
            widget.addItem(QListWidgetItem(tr(self.current_language, "lyrics_none")))
            return
        for stamp, text in self._lyrics_lines:
            item = QListWidgetItem(text or " ")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if stamp is not None:
                item.setData(Qt.ItemDataRole.UserRole, stamp)
            widget.addItem(item)

    def _tick_lyrics(self):
        widget = self._lyrics_widget
        if widget is None or not self._lyrics_synced or not self._lyrics_lines:
            return
        position = self.player.position() / 1000.0
        index = lyrics_mod.active_index(self._lyrics_lines, position)
        if index != self._lyrics_index and index >= 0:
            self._lyrics_index = index
            widget.setCurrentRow(index)
            widget.scrollToItem(widget.item(index),
                                QAbstractItemView.ScrollHint.PositionAtCenter)

    def _open_lyrics(self):
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "lyrics"))
        dialog.resize(460, 560)
        layout = QVBoxLayout(dialog)

        header = QLabel()
        if 0 <= self.current_index < len(self.playlist):
            track = self.playlist[self.current_index]
            header.setText(f"{track.get('title','')}\n{track.get('artist','')}")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        self._lyrics_widget = QListWidget()
        self._lyrics_widget.setWordWrap(True)
        layout.addWidget(self._lyrics_widget, 1)

        def jump(item):
            stamp = item.data(Qt.ItemDataRole.UserRole)
            if stamp is not None:
                self.player.setPosition(int(float(stamp) * 1000))

        self._lyrics_widget.itemDoubleClicked.connect(jump)
        path = self._current_path()
        if path and not self._lyrics_lines:
            self._load_lyrics(path)
        self._fill_lyrics_widget()
        self._lyrics_timer.start()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        self._lyrics_timer.stop()
        self._lyrics_widget = None

    # gallery
    def _open_gallery(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "gallery"))
        dialog.resize(900, 620)
        layout = QVBoxLayout(dialog)

        search = QLineEdit()
        search.setPlaceholderText(tr(lang, "filter_albums"))
        layout.addWidget(search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(14)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

        albums = self.library.albums()

        def populate(text=""):
            while grid.count():
                item = grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            needle = (text or "").lower()
            shown = 0
            for entry in albums:
                label = f"{entry.get('aartist') or ''} {entry.get('album') or ''}".lower()
                if needle and needle not in label:
                    continue
                grid.addWidget(self._album_card(entry, dialog), shown // 5, shown % 5)
                shown += 1
                if shown >= 200:
                    break

        search.textChanged.connect(populate)
        populate()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _album_card(self, entry, parent):
        card = QWidget(parent)
        box = QVBoxLayout(card)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(4)

        art = QLabel()
        art.setFixedSize(140, 140)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = self._cover_for(entry.get("sample"))
        if pix is not None and not pix.isNull():
            art.setPixmap(pix.scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation))
        else:
            canvas = QPixmap(140, 140)
            canvas.fill(QColor("#2a2e37"))
            painter = QPainter(canvas)
            icons.paint(painter, "disc", QRectF(45, 45, 50, 50), QColor("#6d7688"), 2.0)
            painter.end()
            art.setPixmap(canvas)
        box.addWidget(art)

        title = QLabel(entry.get("album") or "")
        title.setWordWrap(True)
        title.setMaximumWidth(140)
        artist = QLabel(entry.get("aartist") or "")
        artist.setWordWrap(True)
        artist.setMaximumWidth(140)
        artist.setStyleSheet("color: #8a93a6;")
        box.addWidget(title)
        box.addWidget(artist)

        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mouseDoubleClickEvent = lambda _e, e=entry: self._play_album(e)
        return card

    def _cover_for(self, path):
        if not path:
            return None
        try:
            meta = self.metadata_manager.get_metadata(path)
            data = meta.get("cover_art") or meta.get("cover")
            if data:
                pix = QPixmap()
                pix.loadFromData(data)
                return pix
        except Exception:
            pass
        return None

    def _play_album(self, entry):
        tracks = self.library.album_tracks(entry.get("aartist"), entry.get("album"))
        paths = [t["path"] for t in tracks if t.get("path") and os.path.exists(t["path"])]
        if not paths:
            return
        for path in paths:
            self._add_to_playlist(path)
        self._after_playlist_added()
        for i, track in enumerate(self.playlist):
            if track.get("path") == paths[0]:
                self._play_index(i)
                break

    # statistics
    def _open_stats(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "statistics"))
        dialog.resize(620, 560)
        layout = QVBoxLayout(dialog)

        stats = self.library.stats()
        listened = float(stats.get("listened") or 0)
        summary = QLabel(
            f"{tr(lang, 'tracks_word')}: {stats.get('tracks', 0)}    "
            f"{tr(lang, 'albums_word')}: {stats.get('albums', 0)}    "
            f"{tr(lang, 'artists_word')}: {stats.get('artists', 0)}\n"
            f"{tr(lang, 'plays')}: {stats.get('plays', 0)}    "
            f"{tr(lang, 'listening_time')}: {format_time(int(listened))}"
        )
        layout.addWidget(summary)

        tabs = QComboBox()
        tabs.addItems([tr(lang, "top_tracks"), tr(lang, "top_artists"),
                       tr(lang, "recently_played"), tr(lang, "recently_added"),
                       tr(lang, "never_played"), tr(lang, "favourites")])
        layout.addWidget(tabs)

        listing = QListWidget()
        layout.addWidget(listing, 1)

        def label_of(row):
            return f"{row.get('artist') or '?'} - {row.get('title') or '?'}"

        def refresh(index):
            listing.clear()
            if index == 0:
                for row in self.library.top_tracks(60):
                    listing.addItem(f"{row.get('play_count', 0):>4}  {label_of(row)}")
            elif index == 1:
                for row in self.library.top_artists(40):
                    listing.addItem(f"{row.get('plays', 0):>4}  {row.get('name')}")
            elif index == 2:
                for row in self.library.recently_played(60):
                    when = time.strftime("%Y-%m-%d %H:%M",
                                         time.localtime(row.get("last_played") or 0))
                    listing.addItem(f"{when}   {label_of(row)}")
            elif index == 3:
                for row in self.library.recently_added(60):
                    listing.addItem(label_of(row))
            elif index == 4:
                for row in self.library.never_played(60):
                    listing.addItem(label_of(row))
            else:
                for row in self.library.favorites():
                    listing.addItem(label_of(row))

        tabs.currentIndexChanged.connect(refresh)
        refresh(0)

        clock = self.library.listening_clock()
        peak = max(clock) if clock else 0
        if peak:
            bars = QLabel(" ".join(
                f"{h:02d}:{'█' * max(0, round(count / peak * 6))}"
                for h, count in enumerate(clock) if count))
            bars.setWordWrap(True)
            bars.setStyleSheet("color: #8a93a6;")
            layout.addWidget(bars)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # smart search
    def _open_smart_search(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "smart_search"))
        dialog.resize(640, 520)
        layout = QVBoxLayout(dialog)

        query = QLineEdit()
        query.setPlaceholderText(help_lines()[0])
        layout.addWidget(query)

        hint = QLabel("\n".join(help_lines()))
        hint.setStyleSheet("color: #8a93a6;")
        layout.addWidget(hint)

        listing = QListWidget()
        listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(listing, 1)

        def run():
            listing.clear()
            try:
                rows = self.library.search(query.text(), limit=500)
            except Exception:
                log.exception("smart search failed")
                return
            for row in rows:
                item = QListWidgetItem(
                    f"{row.get('artist') or '?'} - {row.get('title') or '?'}"
                    f"   [{row.get('album') or ''}]")
                item.setData(Qt.ItemDataRole.UserRole, row.get("path"))
                listing.addItem(item)
            hint.setText(tr(lang, "matches").format(n=len(rows)))

        query.returnPressed.connect(run)
        query.textChanged.connect(lambda: QTimer.singleShot(220, run))

        row = QHBoxLayout()
        add = QPushButton(tr(lang, "add_to_playlist"))
        save = QPushButton(tr(lang, "save_smart_playlist"))
        row.addWidget(add)
        row.addWidget(save)
        row.addStretch(1)
        layout.addLayout(row)

        def do_add():
            items = listing.selectedItems() or [listing.item(i) for i in range(listing.count())]
            for item in items:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    self._add_to_playlist(path)
            self._after_playlist_added()
            dialog.accept()

        def do_save():
            text = query.text().strip()
            if text:
                self.library.create_playlist(text[:40], kind="smart", query=text)
                self._show_ephemeral_status(tr(lang, "smart_playlist_saved"))

        add.clicked.connect(do_add)
        save.clicked.connect(do_save)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # timers and speed
    def _tick_sleep_timer(self):
        if self._sleep_deadline <= 0:
            return
        remaining = self._sleep_deadline - time.time()
        if remaining <= 0:
            self._sleep_deadline = 0.0
            self._sleep_timer.stop()
            self.player.pause()
            self.is_paused = True
            self._update_transport_icons()
            self._show_ephemeral_status(tr(self.current_language, "sleep_done"))

    def _start_sleep_timer(self, minutes):
        self._sleep_deadline = time.time() + minutes * 60
        self._sleep_timer.start()
        self._show_ephemeral_status(
            tr(self.current_language, "sleep_set").format(n=minutes))

    def _cancel_sleep_timer(self):
        self._sleep_deadline = 0.0
        self._sleep_timer.stop()
        self._show_ephemeral_status(tr(self.current_language, "sleep_off"))

    def _set_speed(self, speed):
        self.playback_speed = float(speed)
        self._apply_speed()
        self._show_ephemeral_status(
            tr(self.current_language, "speed_set").format(v=f"{speed:g}"))

    def _toggle_waveform_mode(self):
        if self.waveform_bar is None or not self.waveform_bar.has_data():
            return
        mode = self.waveform_bar.toggle_mode()
        lang = self.current_language
        self._show_ephemeral_status(
            tr(lang, "moodbar") if mode == "mood" else tr(lang, "waveform"))

    # archive import
    def _import_archive(self):
        lang = self.current_language
        path, _ = QFileDialog.getOpenFileName(
            self, tr(lang, "import_archive"), "", "Archives (*.zip);;All Files (*)")
        if not path:
            return
        target = os.path.join(os.path.dirname(path),
                              os.path.splitext(os.path.basename(path))[0])
        try:
            os.makedirs(target, exist_ok=True)
            with zipfile.ZipFile(path) as archive:
                archive.extractall(target)
        except Exception as exc:
            QMessageBox.warning(self, tr(lang, "import_archive"), str(exc))
            return
        from .utils import AUDIO_EXTENSIONS
        added = 0
        for root, _dirs, files in os.walk(target):
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                    if self._add_to_playlist(os.path.join(root, name)):
                        added += 1
        self._after_playlist_added()
        self._show_ephemeral_status(tr(lang, "imported_tracks").format(n=added))

    # tools menu
    def _show_tools_menu(self):
        lang = self.current_language
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())

        menu.addAction(self._icon("search"), tr(lang, "smart_search"),
                       self._open_smart_search)
        menu.addAction(self._icon("grid"), tr(lang, "gallery"), self._open_gallery)
        menu.addAction(self._icon("folder_open"), tr(lang, "file_browser"),
                       self._open_file_browser)
        menu.addAction(self._icon("chart"), tr(lang, "statistics"), self._open_stats)
        menu.addAction(self._icon("cover"), tr(lang, "topchart"), self._open_topchart)
        menu.addSeparator()

        menu.addAction(self._icon("queue"), tr(lang, "queue"), self._open_queue_dialog)
        menu.addAction(self._icon("lyrics"), tr(lang, "lyrics"), self._open_lyrics)
        menu.addAction(self._icon("globe"), tr(lang, "radio"), self._open_radio)
        menu.addSeparator()

        device_menu = self._build_device_menu(menu)
        device_menu.setIcon(self._icon("speaker"))
        try:
            device_menu.setTitle(
                f"{tr(lang, 'audio_output')}: {self.device_manager.describe()}")
        except Exception:
            pass
        menu.addMenu(device_menu)

        speed_menu = menu.addMenu(
            self._icon("speed"),
            f"{tr(lang, 'playback_speed')}: {self.playback_speed:g}x")
        speed_menu.setStyleSheet(self._menu_style())
        for value in SPEEDS:
            act = speed_menu.addAction(f"{value:g}x")
            act.setCheckable(True)
            act.setChecked(abs(self.playback_speed - value) < 1e-6)
            act.triggered.connect(lambda _c=False, v=value: self._set_speed(v))

        gain = menu.addAction(self._icon("headphones"),
                              self._state_text("normalisation", self.replaygain_enabled))
        gain.setCheckable(True)
        gain.setChecked(self.replaygain_enabled)
        gain.toggled.connect(self._toggle_replaygain)

        realtime = bool(self.settings.get("realtime_eq", True))
        rt = menu.addAction(self._icon("equalizer"),
                            self._state_text("realtime_eq", realtime))
        rt.setCheckable(True)
        rt.setChecked(realtime)
        rt.toggled.connect(self._set_realtime_eq)
        menu.addSeparator()

        wave_on = bool(self.settings.get("waveform_bar", True))
        wave = menu.addAction(self._icon("wave"),
                              self._state_text("waveform_bar", wave_on))
        wave.setCheckable(True)
        wave.setChecked(wave_on)
        wave.toggled.connect(self._toggle_waveform_bar)

        mode_now = self.waveform_bar.mode if self.waveform_bar is not None else "wave"
        mood = menu.addAction(
            self._icon("cover"),
            f"{tr(lang, 'moodbar')} / {tr(lang, 'waveform')}: "
            f"{tr(lang, 'moodbar') if mode_now == 'mood' else tr(lang, 'waveform')}")
        mood.triggered.connect(self._toggle_waveform_mode)

        sleep_active = getattr(self, "_sleep_deadline", 0) > 0
        sleep_menu = menu.addMenu(
            self._icon("timer"), self._state_text("sleep_timer", sleep_active))
        sleep_menu.setStyleSheet(self._menu_style())
        for minutes in SLEEP_PRESETS:
            act = sleep_menu.addAction(tr(lang, "minutes_short").format(n=minutes))
            act.triggered.connect(lambda _c=False, m=minutes: self._start_sleep_timer(m))
        sleep_menu.addSeparator()
        sleep_menu.addAction(tr(lang, "sleep_cancel"), self._cancel_sleep_timer)

        theme_menu = self._build_theme_menu(menu)
        theme_menu.setIcon(self._icon("moon"))
        theme_menu.setTitle(
            f"{tr(lang, 'theme_menu')}: "
            f"{self._theme_label(self.current_theme, themes.catalogue().get(self.current_theme, {}))}")
        menu.addMenu(theme_menu)

        notify_on = bool(self.settings.get("notifications", True))
        notify = menu.addAction(self._icon("info"),
                                self._state_text("notifications", notify_on))
        notify.setCheckable(True)
        notify.setChecked(notify_on)
        notify.toggled.connect(self._toggle_notifications)

        menu.addSeparator()
        menu.addAction(self._icon("import"), tr(lang, "import_archive"),
                       self._import_archive)
        menu.addAction(self._icon("edit"), tr(lang, "organise"), self._open_organiser)
        info = menu.addAction(
            f"{tr(lang, 'engine')}: {self.eq_engine.backend} | {native.backend_name()}")
        info.setEnabled(False)

        anchor = getattr(self, "tools_btn", None)
        if anchor is not None:
            menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
        else:
            menu.exec(self.cursor().pos())

    def _toggle_waveform_bar(self, enabled):
        self.settings["waveform_bar"] = bool(enabled)
        self._save_settings_soon()
        self._set_waveform_visible(
            bool(enabled) and self.waveform_bar is not None
            and self.waveform_bar.has_data())
        self._show_ephemeral_status(self._state_text("waveform_bar", enabled))

    def _toggle_notifications(self, enabled):
        self.settings["notifications"] = bool(enabled)
        self._save_settings_soon()
        self._show_ephemeral_status(self._state_text("notifications", enabled))

    def _toggle_replaygain(self, enabled):
        self.replaygain_enabled = bool(enabled)
        self.settings["replaygain"] = self.replaygain_enabled
        self._save_settings_soon()
        self._apply_replaygain(self._current_path())
        self._show_ephemeral_status(self._state_text("normalisation", enabled))

    def _features_shutdown(self):
        try:
            if getattr(self, "_mpris", None) is not None:
                self._mpris.stop()
        except Exception:
            pass
        try:
            if self.analysis is not None:
                self.analysis.stop()
        except Exception:
            pass
        try:
            if self.library is not None:
                self.library.close()
        except Exception:
            pass


class ExtraFeatureMixin:

    def _init_extra_features(self):
        self._mpris = None
        self._radio_stations = radio.load()
        try:
            themes.install()
            themes.clear_cache()
        except Exception:
            log.exception("themes unavailable")
        try:
            self._setup_media_keys()
        except Exception:
            log.exception("media keys unavailable")
        try:
            if mpris.available:
                self._mpris = mpris.MprisService(self)
                if not self._mpris.start():
                    self._mpris = None
        except Exception:
            log.exception("mpris unavailable")
            self._mpris = None

    def _setup_media_keys(self):
        pairs = (
            (Qt.Key.Key_MediaPlay, self._play_pause),
            (Qt.Key.Key_MediaTogglePlayPause, self._play_pause),
            (Qt.Key.Key_MediaPause, self._play_pause),
            (Qt.Key.Key_MediaStop, self._stop),
            (Qt.Key.Key_MediaNext, self._next_track),
            (Qt.Key.Key_MediaPrevious, self._prev_track),
        )
        self._media_shortcuts = []
        for key, slot in pairs:
            try:
                shortcut = QShortcut(QKeySequence(key), self)
                shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
                shortcut.activated.connect(slot)
                self._media_shortcuts.append(shortcut)
            except Exception:
                pass

    def _notify_track(self, idx):
        if not bool(self.settings.get("notifications", True)):
            return
        tray = getattr(self, "tray_icon", None)
        if tray is None or not tray.isVisible():
            return
        if not (0 <= idx < len(self.playlist)):
            return
        track = self.playlist[idx]
        try:
            tray.showMessage(track.get("title", ""),
                             f"{track.get('artist', '')}\n{track.get('album', '')}",
                             tray.icon(), 4000)
        except Exception:
            pass

    def _extra_track_started(self, idx):
        try:
            self._notify_track(idx)
        except Exception:
            pass
        try:
            if self._mpris is not None:
                self._mpris.notify()
        except Exception:
            pass

    # file browser
    def _open_file_browser(self):
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "file_browser"))
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)

        model = QFileSystemModel()
        model.setRootPath("")
        model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files |
                        QDir.Filter.NoDotAndDotDot)
        patterns = ["*" + e for e in sorted(AUDIO_EXTENSIONS | PLAYLIST_EXTENSIONS)]
        model.setNameFilters(patterns)
        model.setNameFilterDisables(False)

        view = QTreeView()
        view.setModel(model)
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setColumnWidth(0, 360)
        for column in (2, 3):
            view.hideColumn(column)
        start = self.settings.get("browse_dir") or QDir.homePath()
        if not os.path.isdir(start):
            start = QDir.homePath()
        view.setRootIndex(model.index(QDir.rootPath()))
        view.setCurrentIndex(model.index(start))
        view.expand(model.index(start))
        view.scrollTo(model.index(start))
        layout.addWidget(view, 1)

        row = QHBoxLayout()
        add_btn = QPushButton(tr(lang, "add_to_playlist"))
        play_btn = QPushButton(tr(lang, "play"))
        row.addWidget(add_btn)
        row.addWidget(play_btn)
        row.addStretch(1)
        layout.addLayout(row)

        def collect():
            paths = []
            for index in view.selectionModel().selectedIndexes():
                if index.column() != 0:
                    continue
                path = model.filePath(index)
                if os.path.isdir(path):
                    for root, _dirs, files in os.walk(path):
                        for name in sorted(files):
                            if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                                paths.append(os.path.join(root, name))
                elif os.path.isfile(path):
                    paths.append(path)
            return paths

        def do_add(play=False):
            paths = collect()
            if not paths:
                return
            self.settings["browse_dir"] = os.path.dirname(paths[0])
            self._save_settings_soon()
            first = len(self.playlist)
            added = 0
            for path in paths:
                if playlists.is_container(path):
                    added += self._import_playlist_file(path)
                elif self._add_to_playlist(path):
                    added += 1
            self._after_playlist_added()
            self._show_ephemeral_status(tr(lang, "imported_tracks").format(n=added))
            if play and added and first < len(self.playlist):
                self._play_index(first)
                dialog.accept()

        add_btn.clicked.connect(lambda: do_add(False))
        play_btn.clicked.connect(lambda: do_add(True))
        view.doubleClicked.connect(lambda: do_add(True))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # top chart
    def _open_topchart(self):
        if self.library is None:
            return
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "topchart"))
        dialog.resize(560, 240)
        layout = QVBoxLayout(dialog)

        form = QHBoxLayout()
        rows = QSpinBox()
        rows.setRange(1, 10)
        rows.setValue(3)
        cols = QSpinBox()
        cols.setRange(1, 10)
        cols.setValue(3)
        size = QSpinBox()
        size.setRange(120, 600)
        size.setSingleStep(20)
        size.setValue(300)
        form.addWidget(QLabel(tr(lang, "rows")))
        form.addWidget(rows)
        form.addWidget(QLabel(tr(lang, "columns")))
        form.addWidget(cols)
        form.addWidget(QLabel(tr(lang, "tile_size")))
        form.addWidget(size)
        form.addStretch(1)
        layout.addLayout(form)

        title_edit = QLineEdit()
        title_edit.setPlaceholderText(tr(lang, "chart_title"))
        layout.addWidget(title_edit)

        labels = QCheckBox(tr(lang, "show_labels"))
        labels.setChecked(True)
        layout.addWidget(labels)

        status = QLabel("")
        status.setWordWrap(True)
        layout.addWidget(status)

        def generate():
            default = os.path.join(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.PicturesLocation) or QDir.homePath(),
                "parch-topchart.png")
            path, _ = QFileDialog.getSaveFileName(
                dialog, tr(lang, "topchart"), default, "PNG (*.png);;JPEG (*.jpg)")
            if not path:
                return
            try:
                saved = topchart.save(self.library, self.metadata_manager, path,
                                      rows.value(), cols.value(), size.value(),
                                      title_edit.text().strip(), labels.isChecked())
            except Exception as exc:
                status.setText(str(exc))
                return
            status.setText(saved or tr(lang, "chart_failed"))
            if saved:
                self._show_ephemeral_status(tr(lang, "chart_saved"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        generate_btn = QPushButton(tr(lang, "generate"))
        generate_btn.clicked.connect(generate)
        buttons.addButton(generate_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # organiser
    def _open_organiser(self):
        lang = self.current_language
        if not self.playlist:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "organise"))
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)

        root_row = QHBoxLayout()
        root_edit = QLineEdit(self.settings.get("organise_root") or QDir.homePath())
        browse = QPushButton("...")
        browse.setFixedWidth(36)
        root_row.addWidget(QLabel(tr(lang, "destination")))
        root_row.addWidget(root_edit, 1)
        root_row.addWidget(browse)
        layout.addLayout(root_row)

        pattern_edit = QLineEdit(self.settings.get("organise_pattern")
                                 or organize.DEFAULT_PATTERN)
        layout.addWidget(pattern_edit)
        hint = QLabel(" ".join(f"%{t}%" for t in organize.TOKENS))
        hint.setStyleSheet("color: #8a93a6;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        move_box = QCheckBox(tr(lang, "move_files"))
        move_box.setChecked(False)
        layout.addWidget(move_box)

        preview = QListWidget()
        layout.addWidget(preview, 1)

        state = {"entries": []}

        def refresh():
            root = root_edit.text().strip() or QDir.homePath()
            state["entries"] = organize.plan(self.playlist, pattern_edit.text(), root)
            preview.clear()
            for entry in state["entries"][:400]:
                preview.addItem(organize.preview_line(entry, root))
            hint.setText(tr(lang, "matches").format(n=len(state["entries"])))

        def choose():
            chosen = QFileDialog.getExistingDirectory(dialog, tr(lang, "destination"),
                                                      root_edit.text())
            if chosen:
                root_edit.setText(chosen)
                refresh()

        def run():
            if not state["entries"]:
                return
            answer = QMessageBox.question(
                dialog, tr(lang, "organise"),
                tr(lang, "organise_confirm").format(n=len(state["entries"])))
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.settings["organise_root"] = root_edit.text().strip()
            self.settings["organise_pattern"] = pattern_edit.text()
            self._save_settings_soon()
            done, errors = organize.apply(state["entries"], move_box.isChecked())
            if move_box.isChecked() and done:
                for entry in state["entries"]:
                    if entry.get("done"):
                        for track in self.playlist:
                            if track.get("path") == entry["source"]:
                                track["path"] = entry["target"]
                self._refresh_playlist(self._current_filter())
            message = tr(lang, "organised").format(n=done)
            if errors:
                message += f"  ({len(errors)})"
            self._show_ephemeral_status(message, 5000)
            refresh()

        browse.clicked.connect(choose)
        pattern_edit.textChanged.connect(lambda: QTimer.singleShot(250, refresh))
        root_edit.textChanged.connect(lambda: QTimer.singleShot(250, refresh))
        refresh()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        run_btn = QPushButton(tr(lang, "apply_word"))
        run_btn.clicked.connect(run)
        buttons.addButton(run_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # radio
    def _open_radio(self):
        lang = self.current_language
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(lang, "radio"))
        dialog.resize(620, 520)
        layout = QVBoxLayout(dialog)

        listing = QListWidget()
        layout.addWidget(listing, 1)

        def fill():
            listing.clear()
            for station in self._radio_stations:
                item = QListWidgetItem(
                    f"{station['name']}   [{station.get('genre') or '-'}]")
                item.setData(Qt.ItemDataRole.UserRole, station["url"])
                listing.addItem(item)

        fill()

        add_row = QHBoxLayout()
        name_edit = QLineEdit()
        name_edit.setPlaceholderText(tr(lang, "station_name"))
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://...")
        add_row.addWidget(name_edit, 1)
        add_row.addWidget(url_edit, 2)
        layout.addLayout(add_row)

        button_row = QHBoxLayout()
        add_btn = QPushButton(tr(lang, "add_station"))
        remove_btn = QPushButton(tr(lang, "remove_word"))
        play_btn = QPushButton(tr(lang, "play"))
        button_row.addWidget(add_btn)
        button_row.addWidget(remove_btn)
        button_row.addWidget(play_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        def do_add():
            if radio.add(self._radio_stations, name_edit.text(), url_edit.text()):
                radio.save(self._radio_stations)
                name_edit.clear()
                url_edit.clear()
                fill()
            else:
                self._show_ephemeral_status(tr(lang, "bad_url"))

        def do_remove():
            item = listing.currentItem()
            if item and radio.remove(self._radio_stations,
                                     item.data(Qt.ItemDataRole.UserRole)):
                radio.save(self._radio_stations)
                fill()

        def do_play():
            item = listing.currentItem()
            if not item:
                return
            url = item.data(Qt.ItemDataRole.UserRole)
            station = next((s for s in self._radio_stations if s["url"] == url), None)
            if station is None:
                return
            if url in self._playlist_paths:
                index = next(i for i, t in enumerate(self.playlist) if t["path"] == url)
            else:
                self.playlist.append(radio.as_track(station))
                self._playlist_paths.add(url)
                index = len(self.playlist) - 1
                self._refresh_playlist(self._current_filter())
            self._play_index(index)
            dialog.accept()

        add_btn.clicked.connect(do_add)
        remove_btn.clicked.connect(do_remove)
        play_btn.clicked.connect(do_play)
        listing.itemDoubleClicked.connect(do_play)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    # themes
    def _build_theme_menu(self, parent_menu=None):
        lang = self.current_language
        menu = QMenu(tr(lang, "theme_menu"), parent_menu or self)
        menu.setStyleSheet(self._menu_style())
        current = self.current_theme
        for key, info in themes.catalogue().items():
            action = menu.addAction(self._theme_label(key, info))
            action.setCheckable(True)
            action.setChecked(key == current)
            action.triggered.connect(lambda _c=False, k=key: self._select_theme(k))
        menu.addSeparator()
        folder = menu.addAction(self._icon("folder_open"), tr(lang, "theme_folder"))
        folder.triggered.connect(self._open_theme_folder)
        template = menu.addAction(self._icon("save"), tr(lang, "theme_template"))
        template.triggered.connect(self._export_theme_template)
        reload_action = menu.addAction(self._icon("repeat"), tr(lang, "theme_reload"))
        reload_action.triggered.connect(self._reload_themes)
        return menu

    def _theme_label(self, key, info):
        mapping = {"dark": "theme_dark_name", "light": "theme_light_name",
                   "midnight": "theme_midnight", "ember": "theme_ember",
                   "forest": "theme_forest", "grape": "theme_grape",
                   "paper": "theme_paper", "nord": "theme_nord"}
        token = mapping.get(key)
        if token:
            return tr(self.current_language, token)
        return info.get("label", key)

    def _select_theme(self, key):
        self.current_theme = key
        self.settings["theme"] = key
        self._save_settings_soon()
        themes.clear_cache()
        self._apply_theme()
        icons.clear_cache()
        self._update_transport_icons()
        self._list_narrow = None
        self._apply_list_density()
        if self.waveform_bar is not None:
            self.waveform_bar.set_theme(
                "light" if themes.is_light(key) else "dark", self._accent_colour())
        self._refresh_playlist(self._current_filter())

    def _reload_themes(self):
        themes.clear_cache()
        self._select_theme(self.current_theme)
        self._show_ephemeral_status(tr(self.current_language, "theme_reloaded"))

    def _open_theme_folder(self):
        path = str(themes.user_dir())
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _export_theme_template(self):
        target = os.path.join(str(themes.user_dir()), "my-theme.json")
        try:
            themes.export_template(target)
        except Exception as exc:
            self._show_ephemeral_status(str(exc))
            return
        self._show_ephemeral_status(target, 5000)
