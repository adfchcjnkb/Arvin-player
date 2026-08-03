import logging
import time
from collections import deque

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioSink, QAudioFormat, QMediaDevices

log = logging.getLogger("parch_mp.audio_sink")

_TARGET_BUFFER_MS = 160
_FLUSH_INTERVAL_MS = 15
_STALL_SECONDS = 1.5


class RealtimeEqAudioSink(QObject):
    stalled = pyqtSignal()

    def __init__(self, eq_engine, parent=None):
        super().__init__(parent)
        self.eq_engine = eq_engine
        self._sink = None
        self._device = None
        self._queue = deque()
        self._format = None
        self._volume = 1.0
        self._active = False
        self._output_device = None
        self._written = 0
        self._pushed = 0
        self._last_progress = 0.0
        self._stall_reported = False

        self._timer = QTimer(self)
        self._timer.setInterval(_FLUSH_INTERVAL_MS)
        self._timer.timeout.connect(self._flush)

    def is_active(self) -> bool:
        return self._active

    def bytes_written(self) -> int:
        return self._written

    def is_producing(self) -> bool:
        if not self._active or self._sink is None:
            return False
        try:
            return self._sink.processedUSecs() > 0 or self._written > 0
        except Exception:
            return self._written > 0

    def current_device(self):
        return self._output_device

    def set_output_device(self, device):
        self._output_device = device
        if self._active and self._format is not None:
            fmt = self._format
            self.restart(fmt.sampleRate(), fmt.channelCount())

    def restart(self, sample_rate, channel_count):
        was_active = self._active
        self.stop()
        if was_active:
            return self.start(sample_rate, channel_count)
        return False

    def _resolve_device(self, fmt):
        candidates = []
        if self._output_device is not None and not self._output_device.isNull():
            candidates.append(self._output_device)
        default = QMediaDevices.defaultAudioOutput()
        if default is not None and not default.isNull():
            candidates.append(default)
        for device in QMediaDevices.audioOutputs():
            if device is not None and not device.isNull():
                candidates.append(device)

        for device in candidates:
            try:
                if device.isFormatSupported(fmt):
                    return device, fmt
            except Exception:
                continue

        for device in candidates:
            try:
                preferred = device.preferredFormat()
                if preferred is not None and preferred.isValid():
                    return device, preferred
            except Exception:
                continue
        return None, fmt

    def start(self, sample_rate: int, channel_count: int) -> bool:
        try:
            wanted = QAudioFormat()
            wanted.setSampleRate(int(sample_rate))
            wanted.setChannelCount(int(channel_count))
            wanted.setSampleFormat(QAudioFormat.SampleFormat.Float)

            device, fmt = self._resolve_device(wanted)
            if device is None:
                log.warning("no audio output device accepts the realtime EQ format")
                return False

            self.stop()
            self._sink = QAudioSink(device, fmt)
            self._sink.setVolume(self._volume)
            self._sink.setBufferSize(
                int(fmt.sampleRate() * fmt.channelCount() * 4 * _TARGET_BUFFER_MS / 1000))
            self._device = self._sink.start()
            if self._device is None or not self._device.isOpen():
                log.warning("could not start QAudioSink on %s", device.description())
                self._sink = None
                self._device = None
                return False

            self._format = fmt
            self._queue.clear()
            self._written = 0
            self._pushed = 0
            self._last_progress = time.monotonic()
            self._stall_reported = False
            self.eq_engine.set_sample_rate(fmt.sampleRate())
            self.eq_engine.reset_state()
            self._active = True
            self._timer.start()
            log.info("realtime EQ sink on %s", device.description())
            return True
        except Exception:
            log.exception("could not start realtime EQ audio sink")
            self._sink = None
            self._device = None
            self._active = False
            return False

    def stop(self):
        self._timer.stop()
        if self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                pass
        self._sink = None
        self._device = None
        self._queue.clear()
        self._active = False

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    def set_paused(self, paused: bool):
        if self._sink is None:
            return
        try:
            if paused:
                self._sink.suspend()
            else:
                self._sink.resume()
        except Exception:
            pass
        self._last_progress = time.monotonic()

    def push_float_frame(self, samples: np.ndarray, channels: int):
        if not self._active:
            return
        try:
            self.eq_engine.process(samples, channels)
        except Exception:
            log.exception("realtime EQ processing failed; passing audio through")
        try:
            self._queue.append(samples.tobytes())
            self._pushed += 1
            max_chunks = 40
            while len(self._queue) > max_chunks:
                self._queue.popleft()
        except Exception:
            log.exception("could not queue processed audio")

    def _flush(self):
        if self._device is None or self._sink is None:
            return
        try:
            if self._sink.state() == QAudio.State.StoppedState:
                self._report_stall()
                return
            free = self._sink.bytesFree()
        except Exception:
            self._report_stall()
            return

        progressed = False
        while free > 0 and self._queue:
            chunk = self._queue.popleft()
            if len(chunk) > free:
                n = self._device.write(chunk[:free])
                if n > 0:
                    self._written += n
                    progressed = True
                self._queue.appendleft(chunk[free:])
                break
            written = self._device.write(chunk)
            if written > 0:
                self._written += written
                progressed = True
            if written < len(chunk):
                self._queue.appendleft(chunk[written:])
                break
            free -= len(chunk)

        now = time.monotonic()
        if progressed or not self._queue:
            self._last_progress = now
        elif now - self._last_progress > _STALL_SECONDS:
            self._report_stall()

    def _report_stall(self):
        if self._stall_reported:
            return
        self._stall_reported = True
        log.warning("realtime EQ sink stalled; falling back to direct output")
        self.stalled.emit()
