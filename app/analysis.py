import logging
import os
from collections import deque

import numpy as np
from PyQt6.QtCore import (QEventLoop, QObject, QThread, QTimer, QUrl, pyqtSignal,
                          pyqtSlot)
from PyQt6.QtMultimedia import QAudioDecoder, QAudioFormat

from . import native
from .utils import safe_mtime

log = logging.getLogger("parch_mp.analysis")

WAVEFORM_BUCKETS = 900
MOODBAR_COLUMNS = 160
TARGET_LUFS = -18.0
_TIMEOUT_MS = 180000


def buffer_to_float32(buffer):
    fmt = buffer.format()
    channels = max(1, fmt.channelCount())
    rate = fmt.sampleRate() or 44100
    sf = fmt.sampleFormat()
    raw = bytes(buffer.data())
    if sf == QAudioFormat.SampleFormat.Float:
        arr = np.frombuffer(raw, dtype=np.float32)
    elif sf == QAudioFormat.SampleFormat.Int16:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sf == QAudioFormat.SampleFormat.Int32:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sf == QAudioFormat.SampleFormat.UInt8:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        return None, rate, channels
    return arr, rate, channels


def pack_waveform(values):
    if not len(values):
        return b""
    arr = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    return (arr * 255.0).astype(np.uint8).tobytes()


def unpack_waveform(blob):
    if not blob:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(blob, dtype=np.uint8).astype(np.float32) / 255.0


class _NumpyAnalyzer:
    def __init__(self, sample_rate):
        self.rate = float(sample_rate)
        self.peaks = []
        self.frames = 0
        self.peak = 0.0
        self.sq = 0.0

    def feed(self, arr, channels):
        if channels > 1:
            usable = (len(arr) // channels) * channels
            if usable <= 0:
                return
            mono = arr[:usable].reshape(-1, channels).mean(axis=1)
        else:
            mono = arr
        if not mono.size:
            return
        self.peak = max(self.peak, float(np.max(np.abs(mono))))
        self.sq += float(np.dot(mono, mono))
        self.frames += mono.size
        block = 1024
        pad = (-mono.size) % block
        if pad:
            mono = np.concatenate([mono, np.zeros(pad, dtype=np.float32)])
        self.peaks.extend(np.abs(mono.reshape(-1, block)).max(axis=1).tolist())

    def finish(self, columns, buckets):
        peaks = np.asarray(self.peaks, dtype=np.float32)
        if peaks.size:
            top = float(peaks.max()) or 1.0
            idx = np.linspace(0, peaks.size, buckets + 1).astype(int)
            wave = [float(peaks[a:max(a + 1, b)].max() / top) for a, b in zip(idx[:-1], idx[1:])]
        else:
            wave = []
        rms = (self.sq / self.frames) ** 0.5 if self.frames else 0.0
        return {
            "moodbar": b"",
            "waveform": wave,
            "bpm": 0.0,
            "peak": self.peak,
            "rms": rms,
            "duration": self.frames / self.rate if self.frames else 0.0,
        }


class _Worker(QObject):
    done = pyqtSignal(str, dict)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel = False

    @pyqtSlot()
    def cancel(self):
        self._cancel = True

    @pyqtSlot(str)
    def analyze(self, path):
        try:
            result = self._decode(path)
        except Exception:
            log.exception("analysis failed for %s", path)
            result = None
        if result is None:
            self.failed.emit(path)
        else:
            self.done.emit(path, result)

    def _decode(self, path):
        if not os.path.exists(path):
            return None

        decoder = QAudioDecoder()
        fmt = QAudioFormat()
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        fmt.setSampleRate(44100)
        fmt.setChannelCount(2)
        decoder.setAudioFormat(fmt)
        decoder.setSource(QUrl.fromLocalFile(path))

        state = {"analyzer": None, "meter": None, "rate": 44100, "channels": 2,
                 "blocks": 0, "error": False}
        loop = QEventLoop()

        def pump():
            while decoder.bufferAvailable():
                buf = decoder.read()
                if not buf.isValid():
                    break
                arr, rate, channels = buffer_to_float32(buf)
                if arr is None or not arr.size:
                    continue
                if state["analyzer"] is None:
                    state["rate"] = rate
                    state["channels"] = channels
                    if native.HAVE_CORE:
                        state["analyzer"] = native.core.TrackAnalyzer(
                            sample_rate=float(rate), fft_size=1024)
                    else:
                        state["analyzer"] = _NumpyAnalyzer(rate)
                    if native.HAVE_DSP:
                        state["meter"] = native.dsp.LoudnessMeter(float(rate), channels)
                contiguous = np.ascontiguousarray(arr, dtype=np.float32)
                state["analyzer"].feed(contiguous, channels)
                if state["meter"] is not None:
                    state["meter"].feed(contiguous, channels)
                state["blocks"] += 1
                if self._cancel:
                    decoder.stop()
                    loop.quit()
                    return

        def on_error(*_args):
            state["error"] = True
            loop.quit()

        decoder.bufferReady.connect(pump)
        decoder.finished.connect(loop.quit)
        decoder.error.connect(on_error)
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(loop.quit)
        guard.start(_TIMEOUT_MS)

        decoder.start()
        loop.exec()
        guard.stop()
        pump()
        decoder.stop()

        analyzer = state["analyzer"]
        if analyzer is None or state["blocks"] == 0 or self._cancel:
            return None

        result = analyzer.finish(columns=MOODBAR_COLUMNS, buckets=WAVEFORM_BUCKETS)
        meter = state["meter"]
        if meter is not None:
            result["lufs"] = float(meter.integrated)
            result["replaygain"] = float(meter.gain_db(TARGET_LUFS))
            result["range"] = float(meter.range)
            result["peak"] = max(result.get("peak", 0.0), float(meter.peak))
        else:
            result["lufs"] = 0.0
            result["replaygain"] = 0.0
            result["range"] = 0.0
        result["mtime"] = safe_mtime(path)
        result["sample_rate"] = state["rate"]
        result["channels"] = state["channels"]
        return result


class AnalysisService(QObject):
    ready = pyqtSignal(str, dict)
    request = pyqtSignal(str)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self._queue = deque()
        self._busy = False
        self._seen = set()

        self._thread = QThread()
        self._thread.setObjectName("parch-analysis")
        self._worker = _Worker()
        self._worker.moveToThread(self._thread)
        self.request.connect(self._worker.analyze)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def enqueue(self, path, priority=False):
        if not path or path in self._seen:
            return
        mtime = safe_mtime(path)
        if self.library is not None and not self.library.needs_analysis(path, mtime):
            return
        self._seen.add(path)
        if priority:
            self._queue.appendleft(path)
        else:
            self._queue.append(path)
        self._pump()

    def pending(self):
        return len(self._queue) + (1 if self._busy else 0)

    def _pump(self):
        if self._busy or not self._queue:
            return
        self._busy = True
        self.request.emit(self._queue.popleft())

    def _on_done(self, path, result):
        self._busy = False
        if self.library is not None:
            try:
                self.library.store_analysis(
                    path,
                    result.get("mtime", 0.0),
                    result.get("moodbar", b""),
                    pack_waveform(result.get("waveform", [])),
                    result.get("bpm", 0.0),
                    result.get("lufs", 0.0),
                    result.get("replaygain", 0.0),
                    result.get("peak", 0.0),
                )
            except Exception:
                log.exception("could not store analysis for %s", path)
        self.ready.emit(path, result)
        self._pump()

    def _on_failed(self, path):
        self._busy = False
        self._pump()

    def stop(self):
        self._queue.clear()
        try:
            self._worker.cancel()
        except Exception:
            pass
        self._thread.quit()
        self._thread.wait(3000)
