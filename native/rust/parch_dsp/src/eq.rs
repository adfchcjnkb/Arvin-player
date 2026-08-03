use crate::biquad::{layout, Coeffs, Shape, State};
use std::f64::consts::PI;

pub const MAX_CHANNELS: usize = 8;

const SLEW_DB_PER_S: f32 = 140.0;
const SCALAR_TAU: f32 = 0.035;
const LIMIT_T: f32 = 0.94;

pub struct Equalizer {
    sample_rate: f64,
    centers: Vec<f64>,
    q: f64,
    target: Vec<f32>,
    current: Vec<f32>,
    coeffs: Vec<Coeffs>,
    states: Vec<State>,
    preamp_lin: f32,
    replaygain_lin: f32,
    auto_gain: bool,
    auto_lin: f32,
    scalar_cur: f32,
    scalar_target: f32,
    bypass: bool,
    reduction: f32,
}

impl Equalizer {
    pub fn new(bands: usize, sample_rate: f64) -> Self {
        let centers = layout(bands);
        let n = centers.len();
        let mut eq = Equalizer {
            sample_rate: if sample_rate > 1000.0 { sample_rate } else { 44100.0 },
            centers,
            q: 1.0,
            target: vec![0.0; n],
            current: vec![0.0; n],
            coeffs: vec![Coeffs::identity(); n],
            states: vec![State::default(); n * MAX_CHANNELS],
            preamp_lin: 1.0,
            replaygain_lin: 1.0,
            auto_gain: true,
            auto_lin: 1.0,
            scalar_cur: 1.0,
            scalar_target: 1.0,
            bypass: false,
            reduction: 0.0,
        };
        eq.redesign_all();
        eq
    }

    fn shape(&self, i: usize) -> Shape {
        if i == 0 {
            Shape::LowShelf
        } else if i + 1 == self.centers.len() {
            Shape::HighShelf
        } else {
            Shape::Peaking
        }
    }

    fn redesign(&mut self, i: usize) {
        let shape = self.shape(i);
        self.coeffs[i] = Coeffs::design(
            self.sample_rate,
            self.centers[i],
            self.current[i] as f64,
            self.q,
            shape,
        );
    }

    fn redesign_all(&mut self) {
        for i in 0..self.centers.len() {
            self.redesign(i);
        }
    }

    pub fn bands(&self) -> usize {
        self.centers.len()
    }

    pub fn centers(&self) -> &[f64] {
        &self.centers
    }

    pub fn set_layout(&mut self, bands: usize) {
        let centers = layout(bands);
        if centers.len() == self.centers.len() && centers == self.centers {
            return;
        }
        let n = centers.len();
        self.centers = centers;
        self.target = vec![0.0; n];
        self.current = vec![0.0; n];
        self.coeffs = vec![Coeffs::identity(); n];
        self.states = vec![State::default(); n * MAX_CHANNELS];
        self.redesign_all();
        self.recompute_auto();
    }

    pub fn set_sample_rate(&mut self, sr: f64) {
        if sr > 1000.0 && (sr - self.sample_rate).abs() > 0.5 {
            self.sample_rate = sr;
            self.redesign_all();
            self.recompute_auto();
            self.reset();
        }
    }

    pub fn set_gains(&mut self, gains: &[f32]) {
        for i in 0..self.target.len() {
            let g = gains.get(i).copied().unwrap_or(0.0);
            self.target[i] = g.clamp(-24.0, 24.0);
        }
        self.recompute_auto();
    }

    pub fn set_band(&mut self, index: usize, gain_db: f32) {
        if index < self.target.len() {
            self.target[index] = gain_db.clamp(-24.0, 24.0);
            self.recompute_auto();
        }
    }

    pub fn gains(&self) -> Vec<f32> {
        self.target.clone()
    }

    pub fn set_q(&mut self, q: f64) {
        self.q = q.clamp(0.3, 6.0);
        self.redesign_all();
        self.recompute_auto();
    }

    pub fn set_preamp_db(&mut self, db: f32) {
        self.preamp_lin = 10f32.powf(db.clamp(-24.0, 24.0) / 20.0);
        self.recompute_auto();
    }

    pub fn set_replaygain_db(&mut self, db: f32) {
        self.replaygain_lin = 10f32.powf(db.clamp(-24.0, 24.0) / 20.0);
        self.recompute_auto();
    }

    pub fn set_auto_gain(&mut self, enabled: bool) {
        self.auto_gain = enabled;
        self.recompute_auto();
    }

    pub fn auto_gain(&self) -> bool {
        self.auto_gain
    }

    pub fn set_bypass(&mut self, bypass: bool) {
        self.bypass = bypass;
    }

    pub fn headroom_db(&self) -> f32 {
        20.0 * self.auto_lin.max(1e-6).log10()
    }

    pub fn reduction_db(&self) -> f32 {
        self.reduction
    }

    pub fn reset(&mut self) {
        for s in self.states.iter_mut() {
            s.reset();
        }
        self.current.copy_from_slice(&self.target);
        self.redesign_all();
        self.recompute_auto();
        self.scalar_cur = self.scalar_target;
        self.reduction = 0.0;
    }

    fn combined_peak_db(&self) -> f64 {
        if !self.target.iter().any(|g| g.abs() > 0.01) {
            return 0.0;
        }
        let nyq = self.sample_rate * 0.5;
        let f_lo = 18.0f64;
        let f_hi = (nyq * 0.94).max(f_lo * 2.0);
        let steps = 220;
        let mut peak: f64 = 0.0;
        for k in 0..=steps {
            let t = k as f64 / steps as f64;
            let f = f_lo * (f_hi / f_lo).powf(t);
            let w = 2.0 * PI * f / self.sample_rate;
            let mut mag = 1.0f64;
            for i in 0..self.centers.len() {
                let c = Coeffs::design(
                    self.sample_rate,
                    self.centers[i],
                    self.target[i] as f64,
                    self.q,
                    self.shape(i),
                );
                mag *= c.magnitude(w);
            }
            if mag > peak {
                peak = mag;
            }
        }
        if peak <= 1e-9 {
            0.0
        } else {
            20.0 * peak.log10()
        }
    }

    fn recompute_auto(&mut self) {
        self.auto_lin = if self.auto_gain {
            let peak = 10f32.powf(self.combined_peak_db() as f32 / 20.0);
            1.0 / (peak * self.preamp_lin * self.replaygain_lin).max(1.0)
        } else {
            1.0
        };
        self.scalar_target = self.preamp_lin * self.replaygain_lin * self.auto_lin;
    }

    fn advance_gains(&mut self, frames: usize) {
        let mut moved = false;
        let max_step =
            (SLEW_DB_PER_S * frames as f32 / self.sample_rate as f32).max(0.2);
        for i in 0..self.target.len() {
            let diff = self.target[i] - self.current[i];
            if diff.abs() <= 1e-3 {
                continue;
            }
            self.current[i] += diff.clamp(-max_step, max_step);
            if (self.target[i] - self.current[i]).abs() < 1e-2 {
                self.current[i] = self.target[i];
            }
            self.redesign(i);
            moved = true;
        }
        let _ = moved;
    }

    pub fn process(&mut self, buf: &mut [f32], channels: usize) {
        let ch = channels.clamp(1, MAX_CHANNELS);
        let frames = buf.len() / ch;
        if frames == 0 {
            return;
        }

        if self.bypass {
            let g = self.replaygain_lin;
            if (g - 1.0).abs() > 1e-6 {
                for s in buf.iter_mut() {
                    *s *= g;
                }
            }
            return;
        }

        self.advance_gains(frames);

        let nbands = self.centers.len();
        let denom = (self.sample_rate as f32 * SCALAR_TAU).max(1.0);
        let alpha = (frames as f32 / denom).min(1.0);
        let start = self.scalar_cur;
        let end = start + (self.scalar_target - start) * alpha;
        let step = if frames > 1 { (end - start) / (frames - 1) as f32 } else { 0.0 };
        self.scalar_cur = end;

        let coeffs = &self.coeffs;
        let states = &mut self.states;
        let mut worst: f32 = 0.0;

        for f in 0..frames {
            let g = start + step * f as f32;
            let base = f * ch;
            for c in 0..ch {
                let idx = base + c;
                let mut x = unsafe { *buf.get_unchecked(idx) } * g;
                for b in 0..nbands {
                    let st = unsafe { states.get_unchecked_mut(b * MAX_CHANNELS + c) };
                    let co = unsafe { coeffs.get_unchecked(b) };
                    x = st.step(x, co);
                }
                let a = x.abs();
                if a > LIMIT_T {
                    let knee = (a - LIMIT_T) / (1.0 - LIMIT_T);
                    let shaped = LIMIT_T + (1.0 - LIMIT_T) * knee.tanh();
                    let g2 = shaped / a;
                    if g2 < worst || worst == 0.0 {
                        worst = g2;
                    }
                    x *= g2;
                }
                unsafe {
                    *buf.get_unchecked_mut(idx) = x;
                }
            }
        }

        let inst = if worst > 0.0 && worst < 1.0 { -20.0 * worst.log10() } else { 0.0 };
        self.reduction = if inst > self.reduction {
            inst
        } else {
            self.reduction * 0.7
        };
    }
}
