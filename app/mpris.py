import logging
import os
import sys

log = logging.getLogger("parch_mp.mpris")

SERVICE = "org.mpris.MediaPlayer2.parchmp"
ROOT_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

available = False
_QDBusConnection = None

if sys.platform.startswith("linux"):
    try:
        from PyQt6.QtDBus import (QDBusConnection, QDBusMessage, QDBusVariant)
        from PyQt6.QtCore import QObject, pyqtSlot, QVariant
        _QDBusConnection = QDBusConnection
        available = True
    except Exception:
        available = False


class MprisService:
    def __init__(self, player):
        self.player = player
        self.connection = None
        self.adaptor = None
        self.ok = False

    def start(self):
        if not available:
            return False
        try:
            self.connection = _QDBusConnection.sessionBus()
            if not self.connection.isConnected():
                return False
            if not self.connection.registerService(SERVICE):
                return False
            self.adaptor = _MprisObject(self.player)
            registered = self.connection.registerObject(
                ROOT_PATH, self.adaptor,
                _QDBusConnection.RegisterOption.ExportAllSlots |
                _QDBusConnection.RegisterOption.ExportAllProperties)
            self.ok = bool(registered)
            if self.ok:
                log.info("mpris service registered")
            return self.ok
        except Exception:
            log.warning("mpris unavailable", exc_info=True)
            return False

    def stop(self):
        if self.connection is not None and self.ok:
            try:
                self.connection.unregisterObject(ROOT_PATH)
                self.connection.unregisterService(SERVICE)
            except Exception:
                pass
        self.ok = False

    def notify(self):
        if not self.ok:
            return
        try:
            message = QDBusMessage.createSignal(
                ROOT_PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged")
            message.setArguments([PLAYER_IFACE, self.adaptor.player_properties(), []])
            self.connection.send(message)
        except Exception:
            pass


if available:

    class _MprisObject(QObject):
        def __init__(self, player):
            super().__init__()
            self.player = player

        def _track(self):
            idx = getattr(self.player, "current_index", -1)
            playlist = getattr(self.player, "playlist", [])
            if 0 <= idx < len(playlist):
                return playlist[idx]
            return {}

        def player_properties(self):
            track = self._track()
            state = "Playing"
            if not getattr(self.player, "is_playing", False):
                state = "Stopped"
            elif getattr(self.player, "is_paused", False):
                state = "Paused"
            metadata = {
                "xesam:title": track.get("title", ""),
                "xesam:album": track.get("album", ""),
                "xesam:artist": [track.get("artist", "")],
                "mpris:length": int((track.get("duration") or 0) * 1000000),
            }
            path = track.get("path")
            if path and os.path.exists(path):
                metadata["xesam:url"] = "file://" + path
            return {
                "PlaybackStatus": state,
                "Metadata": metadata,
                "CanGoNext": True,
                "CanGoPrevious": True,
                "CanPlay": True,
                "CanPause": True,
                "CanSeek": True,
                "CanControl": True,
            }

        @pyqtSlot()
        def Play(self):
            if not getattr(self.player, "is_playing", False) or \
                    getattr(self.player, "is_paused", False):
                self.player._play_pause()

        @pyqtSlot()
        def Pause(self):
            if getattr(self.player, "is_playing", False) and \
                    not getattr(self.player, "is_paused", False):
                self.player._play_pause()

        @pyqtSlot()
        def PlayPause(self):
            self.player._play_pause()

        @pyqtSlot()
        def Stop(self):
            self.player._stop()

        @pyqtSlot()
        def Next(self):
            self.player._next_track()

        @pyqtSlot()
        def Previous(self):
            self.player._prev_track()

        @pyqtSlot()
        def Raise(self):
            self.player.showNormal()
            self.player.activateWindow()

        @pyqtSlot()
        def Quit(self):
            self.player.close()

else:

    class _MprisObject:
        def __init__(self, player):
            self.player = player
