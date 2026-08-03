import numpy as np
from scipy.signal import sosfilt, sosfreqz

from .. import native

BAND_CENTERS = {
    5: [80, 250, 1000, 4000, 12000],
    10: [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000],
    15: [25, 40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000, 6300, 10000, 16000],
    31: [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800,
         1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000],
}

FACTORY_PRESETS = {
    "flat":       [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "bass_boost": [7, 6, 4.5, 2.5, 1, 0, 0, 0, 0, 0],
    "treble_boost": [0, 0, 0, 0, 0, 1, 2.5, 4.5, 6, 7],
    "vocal":      [-2, -2, -1, 1, 3, 3, 2, 1, 0, -1],
    "rock":       [4, 3, -1, -2, -1, 1, 2, 3, 3, 3],
    "pop":        [-1, 1, 3, 3, 1, -1, -1, 0, 1, 1],
    "jazz":       [3, 2, 1, 1.5, -1, -1, 0, 1, 2, 3],
    "classical":  [4, 3, 2, 1, -1, -1, -1, 0, 2, 3],
    "electronic": [5, 4, 1, 0, -2, 1, 0, 1, 3, 4],
    "loudness":   [6, 4, 0, -1, -1, -1, -1, 0, 4, 6],
    "hiphop":     [6, 5, 2, 1, -1, -1, 1, 2, 3, 3],
    "metal":      [5, 3, -1, -2, 1, 2, 1, 3, 4, 4],
    "acoustic":   [3, 3, 2, 1, 1, 1, 2, 3, 3, 2],
    "dance":      [6, 5, 3, 0, -1, -2, 0, 3, 5, 5],
    "podcast":    [-4, -3, -1, 2, 4, 4, 3, 1, -1, -3],
    "late_night": [-3, -2, 0, 2, 3, 3, 2, 1, -1, -2],
    "small_speakers": [-6, -4, 0, 3, 4, 3, 2, 2, 1, 0],
    "headphones": [4, 3, 1, 0, -1, -1, 0, 2, 3, 4],
}


def expand_preset(gains, centers):
    base = np.asarray(BAND_CENTERS[10], dtype=np.float64)
    vals = np.asarray(gains, dtype=np.float64)
    if len(centers) == len(vals):
        return [float(v) for v in vals]
    target = np.asarray(centers, dtype=np.float64)
    return [float(v) for v in np.interp(np.log10(target), np.log10(base), vals)]


def _design_sos(sample_rate, freq, gain_db, q, kind):
    sr = max(1000.0, sample_rate)
    f0 = min(max(freq, 1.0), sr * 0.49)
    q = max(0.05, q)
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / (2 * q)

    if kind == "lowshelf":
        sqa = np.sqrt(a)
        tsa = 2 * sqa * alpha
        b0 = a * ((a + 1) - (a - 1) * cos_w0 + tsa)
        b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
        b2 = a * ((a + 1) - (a - 1) * cos_w0 - tsa)
        a0 = (a + 1) + (a - 1) * cos_w0 + tsa
        a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
        a2 = (a + 1) + (a - 1) * cos_w0 - tsa
    elif kind == "highshelf":
        sqa = np.sqrt(a)
        tsa = 2 * sqa * alpha
        b0 = a * ((a + 1) + (a - 1) * cos_w0 + tsa)
        b1 = -2 * a * ((a - 1) + (a + 1) * cos_w0)
        b2 = a * ((a + 1) + (a - 1) * cos_w0 - tsa)
        a0 = (a + 1) - (a - 1) * cos_w0 + tsa
        a1 = 2 * ((a - 1) - (a + 1) * cos_w0)
        a2 = (a + 1) - (a - 1) * cos_w0 - tsa
    else:
        b0 = 1 + alpha * a
        b1 = -2 * cos_w0
        b2 = 1 - alpha * a
        a0 = 1 + alpha / a
        a1 = -2 * cos_w0
        a2 = 1 - alpha / a

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


class _Band:

    __slots__ = ("freq", "gain_db", "q", "kind", "sample_rate", "sos", "zi")

    def __init__(self, sample_rate, freq, gain_db, q, kind, max_channels=8):
        self.sample_rate = sample_rate
        self.freq = freq
        self.gain_db = gain_db
        self.q = q
        self.kind = kind
        self.sos = _design_sos(sample_rate, freq, gain_db, q, kind)
        self.zi = np.zeros((max_channels, 1, 2), dtype=np.float64)

    def _design(self):
        self.sos = _design_sos(self.sample_rate, self.freq, self.gain_db, self.q, self.kind)

    def set_params(self, freq, gain_db, q, kind):
        if (freq, gain_db, q, kind) == (self.freq, self.gain_db, self.q, self.kind):
            return
        self.freq, self.gain_db, self.q, self.kind = freq, gain_db, q, kind
        self._design()

    def process(self, x: np.ndarray, channel: int) -> np.ndarray:
        y, zf = sosfilt(self.sos, x, zi=self.zi[channel])
        self.zi[channel] = zf
        return y

    def reset(self):
        self.zi[:] = 0.0


class _PurePythonEqualizer:
    MAX_CHANNELS = 8

    _GAIN_SLEW_DB_PER_S = 120.0
    _SCALAR_TAU_S = 0.04
    _LIMIT_T = 0.95

    def __init__(self, num_bands=10, sample_rate=44100.0):
        self.sample_rate = float(sample_rate)
        centers = BAND_CENTERS.get(num_bands, BAND_CENTERS[10])
        self._centers = list(centers)
        self.bands = []
        for i, f in enumerate(centers):
            self.bands.append(_Band(self.sample_rate, f, 0.0, 1.0, self._kind(i), self.MAX_CHANNELS))

        n = len(self.bands)
        self.target_gains = np.zeros(n, dtype=np.float64)
        self.current_gains = np.zeros(n, dtype=np.float64)

        self.user_preamp_lin = 1.0
        self.replaygain_lin = 1.0
        self.auto_gain = True
        self._auto_gain_lin = 1.0
        self._scalar_target = 1.0
        self._scalar_cur = 1.0
        self.bypass = False

    def _kind(self, i):
        last = len(self._centers) - 1 if self._centers else 0
        return "lowshelf" if i == 0 else ("highshelf" if i == last else "peaking")

    def num_bands(self):
        return len(self.bands)

    def _redesign_all(self):
        for i, b in enumerate(self.bands):
            b.set_params(self._centers[i], float(self.current_gains[i]), 1.0, self._kind(i))

    def set_sample_rate(self, sr):
        if abs(sr - self.sample_rate) > 0.5:
            self.sample_rate = sr
            for b in self.bands:
                b.sample_rate = sr
            self._redesign_all()
            self._recompute_auto_gain()
            self.reset()

    def set_band(self, index, freq_hz, gain_db, q, filter_type="peaking", enabled=True):
        if 0 <= index < len(self.bands):
            self.target_gains[index] = max(-24.0, min(24.0, gain_db))
            self._recompute_auto_gain()

    def set_graphic_gains(self, gains_db):
        for i in range(len(self.bands)):
            if i < len(gains_db):
                self.target_gains[i] = max(-24.0, min(24.0, float(gains_db[i])))
        self._recompute_auto_gain()

    def set_preamp_db(self, db):
        self.user_preamp_lin = 10 ** (max(-24.0, min(24.0, db)) / 20.0)
        self._recompute_auto_gain()

    def set_replaygain_db(self, db):
        self.replaygain_lin = 10 ** (max(-24.0, min(24.0, db)) / 20.0)
        self._recompute_auto_gain()

    def set_auto_gain(self, enabled: bool):
        self.auto_gain = bool(enabled)
        self._recompute_auto_gain()

    def set_bypass(self, bypass):
        self.bypass = bypass

    def reset(self):
        for b in self.bands:
            b.reset()
        self.current_gains[:] = self.target_gains
        self._redesign_all()
        self._recompute_auto_gain()
        self._scalar_cur = self._scalar_target

    def _recompute_auto_gain(self):
        if not self.auto_gain:
            self._auto_gain_lin = 1.0
        else:
            peak_lin = 10 ** (self._combined_peak_db(self.target_gains) / 20.0)
            self._auto_gain_lin = 1.0 / max(
                1.0, peak_lin * self.user_preamp_lin * self.replaygain_lin)
        self._update_scalar_target()

    def _update_scalar_target(self):
        self._scalar_target = self.user_preamp_lin * self.replaygain_lin * self._auto_gain_lin

    def _combined_peak_db(self, gains):
        gains = np.asarray(gains, dtype=np.float64)
        if not np.any(np.abs(gains) > 0.01):
            return 0.0
        sos = np.vstack([
            _design_sos(self.sample_rate, self._centers[i], float(gains[i]), 1.0, self._kind(i))
            for i in range(len(self.bands))
        ])
        _, h = sosfreqz(sos, worN=512, fs=self.sample_rate)
        peak = float(np.max(np.abs(h)))
        if peak <= 1e-9:
            return 0.0
        return 20.0 * np.log10(peak)

    def _advance_band_gains(self, n_frames):
        diff = self.target_gains - self.current_gains
        if not np.any(np.abs(diff) > 1e-3):
            return
        max_step = max(0.25, self._GAIN_SLEW_DB_PER_S * n_frames / self.sample_rate)
        self.current_gains += np.clip(diff, -max_step, max_step)
        close = np.abs(self.target_gains - self.current_gains) < 1e-2
        self.current_gains[close] = self.target_gains[close]
        for i, b in enumerate(self.bands):
            b.set_params(self._centers[i], float(self.current_gains[i]), 1.0, self._kind(i))

    def _apply_scalar_ramp(self, buffer):
        target = self._scalar_target
        cur = self._scalar_cur
        denom = max(1.0, self.sample_rate * self._SCALAR_TAU_S)
        alpha = min(1.0, buffer.size / denom)
        new = cur + (target - cur) * alpha
        if abs(new - cur) < 1e-7:
            self._scalar_cur = target
            if abs(target - 1.0) > 1e-7:
                buffer *= target
            return
        ramp = np.linspace(cur, new, buffer.size, endpoint=True, dtype=np.float32)
        buffer *= ramp
        self._scalar_cur = new

    def process_f32(self, buffer: np.ndarray, channels: int):
        if self.bypass:
            return
        channels = max(1, min(channels, self.MAX_CHANNELS))
        n_frames = buffer.size // channels
        if n_frames <= 0:
            return

        self._advance_band_gains(n_frames)
        self._apply_scalar_ramp(buffer)

        for ch in range(channels):
            x = buffer[ch::channels].astype(np.float64, copy=False)
            for band in self.bands:
                x = band.process(x, ch)
            buffer[ch::channels] = x

        t = self._LIMIT_T
        mag = np.abs(buffer)
        over = mag > t
        if np.any(over):
            knee = (mag[over] - t) / (1.0 - t)
            buffer[over] = np.sign(buffer[over]) * (t + (1.0 - t) * np.tanh(knee))


class _NativeEqualizer:
    def __init__(self, factory, num_bands, sample_rate):
        self._eq = factory(num_bands, float(sample_rate))
        self.sample_rate = float(sample_rate)

    @property
    def auto_gain(self):
        return self._eq.auto_gain

    def centers(self):
        return list(self._eq.centers)

    def set_layout(self, num_bands):
        self._eq.set_layout(num_bands)

    def set_sample_rate(self, sr):
        self.sample_rate = float(sr)
        self._eq.set_sample_rate(float(sr))

    def set_graphic_gains(self, gains):
        self._eq.set_gains([float(g) for g in gains])

    def set_preamp_db(self, db):
        self._eq.set_preamp_db(float(db))

    def set_replaygain_db(self, db):
        self._eq.set_replaygain_db(float(db))

    def set_auto_gain(self, enabled):
        self._eq.set_auto_gain(bool(enabled))

    def set_bypass(self, bypass):
        self._eq.set_bypass(bool(bypass))

    def reset(self):
        self._eq.reset()

    def headroom_db(self):
        return float(self._eq.headroom_db)

    def reduction_db(self):
        return float(self._eq.reduction_db)

    def process_f32(self, buffer, channels):
        self._eq.process(buffer, channels)


def available_backends():
    out = []
    if native.HAVE_DSP and hasattr(native.dsp, "Equalizer"):
        out.append("rust")
    if native.HAVE_CORE and hasattr(native.core, "Equalizer"):
        out.append("cpp")
    out.append("python")
    return out


def _make_impl(name, num_bands, sample_rate):
    if name == "rust" and native.HAVE_DSP and hasattr(native.dsp, "Equalizer"):
        return _NativeEqualizer(native.dsp.Equalizer, num_bands, sample_rate)
    if name == "cpp" and native.HAVE_CORE and hasattr(native.core, "Equalizer"):
        return _NativeEqualizer(native.core.Equalizer, num_bands, sample_rate)
    if name == "python":
        return _PurePythonEqualizer(num_bands, float(sample_rate))
    return None


class EqualizerEngine:
    def __init__(self, num_bands=10, sample_rate=44100.0, backend=None):
        self.num_bands_requested = num_bands
        order = available_backends()
        if backend and backend in order:
            order = [backend] + [b for b in order if b != backend]
        self._impl = None
        self.backend = "python"
        for name in order:
            try:
                impl = _make_impl(name, num_bands, sample_rate)
            except Exception:
                impl = None
            if impl is not None:
                self._impl = impl
                self.backend = name
                break
        if self._impl is None:
            self._impl = _PurePythonEqualizer(num_bands, float(sample_rate))
            self.backend = "python"
        self.enabled = True
        self.current_preset = "flat"
        self.gains = [0.0] * len(self.centers())
        self.preamp_db = 0.0
        self.replaygain_db = 0.0

    def centers(self):
        impl = self._impl
        if hasattr(impl, "centers"):
            return impl.centers()
        return list(BAND_CENTERS.get(self.num_bands_requested, BAND_CENTERS[10]))

    def num_bands(self):
        return len(self.centers())

    @property
    def auto_gain(self) -> bool:
        return self._impl.auto_gain

    def set_layout(self, num_bands):
        if num_bands == self.num_bands_requested:
            return
        curve = list(self.gains)
        old_centers = self.centers()
        if hasattr(self._impl, "set_layout"):
            self._impl.set_layout(num_bands)
        else:
            self._impl = _PurePythonEqualizer(num_bands, self._impl.sample_rate)
        self.num_bands_requested = num_bands
        centers = self.centers()
        if curve and len(old_centers) == len(curve):
            base = np.log10(np.asarray(old_centers, dtype=np.float64))
            self.gains = [float(v) for v in np.interp(
                np.log10(np.asarray(centers, dtype=np.float64)), base,
                np.asarray(curve, dtype=np.float64))]
        else:
            self.gains = [0.0] * len(centers)
        self._impl.set_graphic_gains(self.gains)
        self._impl.set_preamp_db(self.preamp_db)

    def set_sample_rate(self, sr):
        self._impl.set_sample_rate(float(sr))

    def set_band_gain(self, index, gain_db):
        if 0 <= index < len(self.gains):
            self.gains[index] = gain_db
            self._impl.set_graphic_gains(self.gains)
            self.current_preset = "custom"

    def set_gains(self, gains):
        self.gains = [float(g) for g in gains]
        self._impl.set_graphic_gains(self.gains)
        self.current_preset = "custom"

    def apply_preset(self, name):
        if name in FACTORY_PRESETS:
            self.gains = expand_preset(FACTORY_PRESETS[name], self.centers())
            self._impl.set_graphic_gains(self.gains)
            self.current_preset = name

    def set_preamp_db(self, db):
        self.preamp_db = db
        self._impl.set_preamp_db(db)

    def set_replaygain_db(self, db):
        self.replaygain_db = float(db)
        if hasattr(self._impl, "set_replaygain_db"):
            self._impl.set_replaygain_db(self.replaygain_db)

    def set_auto_gain(self, enabled: bool):
        self._impl.set_auto_gain(enabled)

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self._impl.set_bypass(not enabled)

    def headroom_db(self):
        if hasattr(self._impl, "headroom_db"):
            return self._impl.headroom_db()
        return 20.0 * np.log10(max(1e-6, self._impl._auto_gain_lin))

    def reduction_db(self):
        if hasattr(self._impl, "reduction_db"):
            return self._impl.reduction_db()
        return 0.0

    def reset_state(self):
        self._impl.reset()

    def process(self, interleaved_f32: np.ndarray, channels: int):
        self._impl.process_f32(interleaved_f32, channels)
