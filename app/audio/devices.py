import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QMediaDevices

log = logging.getLogger("parch_mp.devices")

SYSTEM_DEFAULT = "@default"

_BLUETOOTH_HINTS = ("bluetooth", "bluez", "a2dp", "handsfree", "headset", "airpod")
_HEADPHONE_HINTS = ("headphone", "headset", "earphone")
_HDMI_HINTS = ("hdmi", "displayport", "display port")
_USB_HINTS = ("usb",)


def device_id(device):
    if device is None or device.isNull():
        return SYSTEM_DEFAULT
    try:
        return bytes(device.id()).decode("utf-8", "replace")
    except Exception:
        return device.description()


def kind_of(device):
    if device is None or device.isNull():
        return "speaker"
    text = f"{device.description()} {device_id(device)}".lower()
    if any(h in text for h in _BLUETOOTH_HINTS):
        return "bluetooth"
    if any(h in text for h in _HEADPHONE_HINTS):
        return "headphones"
    if any(h in text for h in _HDMI_HINTS):
        return "hdmi"
    if any(h in text for h in _USB_HINTS):
        return "usb"
    return "speaker"


def icon_for(kind):
    return {
        "bluetooth": "bluetooth",
        "headphones": "headphones",
        "hdmi": "monitor",
        "usb": "usb",
    }.get(kind, "speaker")


class AudioDeviceManager(QObject):
    devices_changed = pyqtSignal()
    active_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._media_devices = QMediaDevices(self)
        self._preferred_id = SYSTEM_DEFAULT
        self._active = None
        self._known = self._snapshot()

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._handle_change)
        self._media_devices.audioOutputsChanged.connect(self._debounce.start)

    def _snapshot(self):
        return {device_id(d): d.description() for d in QMediaDevices.audioOutputs()}

    def outputs(self):
        return [d for d in QMediaDevices.audioOutputs() if d is not None and not d.isNull()]

    def default_device(self):
        device = QMediaDevices.defaultAudioOutput()
        return None if device is None or device.isNull() else device

    def preferred_id(self):
        return self._preferred_id

    def set_preferred_id(self, identifier):
        self._preferred_id = identifier or SYSTEM_DEFAULT
        self._apply()

    def resolve(self):
        if self._preferred_id and self._preferred_id != SYSTEM_DEFAULT:
            for device in self.outputs():
                if device_id(device) == self._preferred_id:
                    return device
        return self.default_device()

    def active(self):
        return self._active

    def describe(self, device=None):
        device = device or self.resolve()
        if device is None:
            return "-"
        return device.description()

    def entries(self):
        rows = [(SYSTEM_DEFAULT, None, "default")]
        for device in self.outputs():
            rows.append((device_id(device), device, kind_of(device)))
        return rows

    def _apply(self):
        device = self.resolve()
        previous = device_id(self._active) if self._active is not None else None
        current = device_id(device) if device is not None else None
        self._active = device
        if previous != current:
            self.active_changed.emit(device)

    def refresh(self):
        self._apply()

    def _handle_change(self):
        snapshot = self._snapshot()
        added = [name for key, name in snapshot.items() if key not in self._known]
        removed = [name for key, name in self._known.items() if key not in snapshot]
        self._known = snapshot
        if added:
            log.info("audio output appeared: %s", ", ".join(added))
        if removed:
            log.info("audio output removed: %s", ", ".join(removed))
        self.devices_changed.emit()
        self._apply()

    def newest_bluetooth(self):
        for device in self.outputs():
            if kind_of(device) == "bluetooth":
                return device
        return None
