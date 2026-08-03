mod biquad;
mod eq;
mod extras;
mod loudness;

use pyo3::buffer::PyBuffer;
use pyo3::exceptions::{PyBufferError, PyValueError};
use pyo3::prelude::*;

fn writable(obj: &Bound<'_, PyAny>) -> PyResult<(&'static mut [f32], PyBuffer<f32>)> {
    let buf = PyBuffer::<f32>::get(obj)?;
    if buf.readonly() {
        return Err(PyBufferError::new_err("buffer is read-only"));
    }
    if !buf.is_c_contiguous() {
        return Err(PyBufferError::new_err("buffer must be contiguous"));
    }
    let n = buf.item_count();
    let ptr = buf.buf_ptr() as *mut f32;
    let slice = unsafe { std::slice::from_raw_parts_mut(ptr, n) };
    Ok((slice, buf))
}

fn readable(obj: &Bound<'_, PyAny>) -> PyResult<(&'static [f32], PyBuffer<f32>)> {
    let buf = PyBuffer::<f32>::get(obj)?;
    if !buf.is_c_contiguous() {
        return Err(PyBufferError::new_err("buffer must be contiguous"));
    }
    let n = buf.item_count();
    let ptr = buf.buf_ptr() as *const f32;
    let slice = unsafe { std::slice::from_raw_parts(ptr, n) };
    Ok((slice, buf))
}

#[pyclass(name = "Equalizer")]
struct PyEqualizer {
    inner: eq::Equalizer,
}

#[pymethods]
impl PyEqualizer {
    #[new]
    #[pyo3(signature = (bands = 10, sample_rate = 44100.0))]
    fn new(bands: usize, sample_rate: f64) -> Self {
        PyEqualizer { inner: eq::Equalizer::new(bands, sample_rate) }
    }

    #[getter]
    fn bands(&self) -> usize {
        self.inner.bands()
    }

    #[getter]
    fn centers(&self) -> Vec<f64> {
        self.inner.centers().to_vec()
    }

    #[getter]
    fn auto_gain(&self) -> bool {
        self.inner.auto_gain()
    }

    #[getter]
    fn headroom_db(&self) -> f32 {
        self.inner.headroom_db()
    }

    #[getter]
    fn reduction_db(&self) -> f32 {
        self.inner.reduction_db()
    }

    fn set_layout(&mut self, bands: usize) {
        self.inner.set_layout(bands);
    }

    fn set_sample_rate(&mut self, sr: f64) {
        self.inner.set_sample_rate(sr);
    }

    fn set_gains(&mut self, gains: Vec<f32>) {
        self.inner.set_gains(&gains);
    }

    fn set_band(&mut self, index: usize, gain_db: f32) {
        self.inner.set_band(index, gain_db);
    }

    fn gains(&self) -> Vec<f32> {
        self.inner.gains()
    }

    fn set_q(&mut self, q: f64) {
        self.inner.set_q(q);
    }

    fn set_preamp_db(&mut self, db: f32) {
        self.inner.set_preamp_db(db);
    }

    fn set_replaygain_db(&mut self, db: f32) {
        self.inner.set_replaygain_db(db);
    }

    fn set_auto_gain(&mut self, enabled: bool) {
        self.inner.set_auto_gain(enabled);
    }

    fn set_bypass(&mut self, bypass: bool) {
        self.inner.set_bypass(bypass);
    }

    fn reset(&mut self) {
        self.inner.reset();
    }

    fn process(&mut self, data: &Bound<'_, PyAny>, channels: usize) -> PyResult<()> {
        let (slice, _hold) = writable(data)?;
        self.inner.process(slice, channels);
        Ok(())
    }
}

#[pyclass(name = "LoudnessMeter")]
struct PyLoudness {
    inner: loudness::LoudnessMeter,
}

#[pymethods]
impl PyLoudness {
    #[new]
    #[pyo3(signature = (sample_rate = 44100.0, channels = 2))]
    fn new(sample_rate: f64, channels: usize) -> Self {
        PyLoudness { inner: loudness::LoudnessMeter::new(sample_rate, channels) }
    }

    fn feed(&mut self, data: &Bound<'_, PyAny>, channels: usize) -> PyResult<()> {
        let (slice, _hold) = readable(data)?;
        self.inner.feed(slice, channels);
        Ok(())
    }

    fn reset(&mut self) {
        self.inner.reset();
    }

    #[getter]
    fn integrated(&self) -> f64 {
        let v = self.inner.integrated();
        if v.is_finite() {
            v
        } else {
            -70.0
        }
    }

    #[getter]
    fn momentary(&self) -> f64 {
        let v = self.inner.momentary();
        if v.is_finite() {
            v
        } else {
            -70.0
        }
    }

    #[getter]
    fn short_term(&self) -> f64 {
        let v = self.inner.short_term();
        if v.is_finite() {
            v
        } else {
            -70.0
        }
    }

    #[getter]
    fn range(&self) -> f64 {
        self.inner.range()
    }

    #[getter]
    fn peak(&self) -> f32 {
        self.inner.peak()
    }

    #[getter]
    fn duration(&self) -> f64 {
        self.inner.duration()
    }

    #[pyo3(signature = (target_lufs = -18.0))]
    fn gain_db(&self, target_lufs: f64) -> f64 {
        self.inner.gain_db(target_lufs)
    }
}

#[pyclass(name = "Crossfader")]
struct PyCrossfader {
    inner: extras::Crossfader,
}

#[pymethods]
impl PyCrossfader {
    #[new]
    #[pyo3(signature = (sample_rate = 44100.0, seconds = 4.0))]
    fn new(sample_rate: f64, seconds: f64) -> Self {
        PyCrossfader { inner: extras::Crossfader::new(sample_rate, seconds) }
    }

    fn reset(&mut self) {
        self.inner.reset();
    }

    #[getter]
    fn done(&self) -> bool {
        self.inner.done()
    }

    #[getter]
    fn progress(&self) -> f32 {
        self.inner.progress()
    }

    fn mix(
        &mut self,
        outgoing: &Bound<'_, PyAny>,
        incoming: &Bound<'_, PyAny>,
        channels: usize,
    ) -> PyResult<bool> {
        let (dst, _h1) = writable(outgoing)?;
        let (src, _h2) = readable(incoming)?;
        Ok(self.inner.mix(dst, src, channels))
    }
}

#[pyfunction]
fn fuzzy_score(query: &str, target: &str) -> Option<i32> {
    extras::fuzzy_score(query, target)
}

#[pyfunction]
#[pyo3(signature = (query, items, limit = 0))]
fn fuzzy_filter(query: &str, items: Vec<String>, limit: usize) -> Vec<(usize, i32)> {
    let mut hits: Vec<(usize, i32)> = items
        .iter()
        .enumerate()
        .filter_map(|(i, s)| extras::fuzzy_score(query, s).map(|sc| (i, sc)))
        .collect();
    hits.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    if limit > 0 && hits.len() > limit {
        hits.truncate(limit);
    }
    hits
}

#[pyfunction]
fn resample(data: &Bound<'_, PyAny>, channels: usize, from_rate: f64, to_rate: f64) -> PyResult<Vec<f32>> {
    let (slice, _hold) = readable(data)?;
    if channels == 0 {
        return Err(PyValueError::new_err("channels must be positive"));
    }
    Ok(extras::resample_linear(slice, channels, from_rate, to_rate))
}

#[pyfunction]
fn apply_gain(data: &Bound<'_, PyAny>, gain: f32) -> PyResult<()> {
    let (slice, _hold) = writable(data)?;
    extras::apply_gain(slice, gain);
    Ok(())
}

#[pyfunction]
fn balance(data: &Bound<'_, PyAny>, channels: usize, pan: f32) -> PyResult<()> {
    let (slice, _hold) = writable(data)?;
    extras::balance(slice, channels, pan);
    Ok(())
}

#[pyfunction]
fn band_centers(bands: usize) -> Vec<f64> {
    biquad::layout(bands)
}

#[pymodule]
fn parch_dsp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyEqualizer>()?;
    m.add_class::<PyLoudness>()?;
    m.add_class::<PyCrossfader>()?;
    m.add_function(wrap_pyfunction!(fuzzy_score, m)?)?;
    m.add_function(wrap_pyfunction!(fuzzy_filter, m)?)?;
    m.add_function(wrap_pyfunction!(resample, m)?)?;
    m.add_function(wrap_pyfunction!(apply_gain, m)?)?;
    m.add_function(wrap_pyfunction!(balance, m)?)?;
    m.add_function(wrap_pyfunction!(band_centers, m)?)?;
    m.add("__version__", "1.0.0")?;
    Ok(())
}
