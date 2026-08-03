use crate::biquad::{Coeffs, State64};

const SHELF_F0: f64 = 1681.974450955533;
const SHELF_G: f64 = 3.999843853973347;
const SHELF_Q: f64 = 0.7071752369554196;
const HP_F0: f64 = 38.13547087602444;
const HP_Q: f64 = 0.5003270373238773;

const ABS_GATE: f64 = -70.0;
const OFFSET: f64 = -0.691;

pub struct LoudnessMeter {
    sample_rate: f64,
    channels: usize,
    shelf: Coeffs,
    hp: Coeffs,
    shelf_state: Vec<State64>,
    hp_state: Vec<State64>,
    sub_len: usize,
    sub_fill: usize,
    sub_acc: Vec<f64>,
    ring: Vec<Vec<f64>>,
    ring_len: usize,
    blocks: Vec<f64>,
    short_ring: Vec<f64>,
    peak: f32,
    momentary: f64,
    short_term: f64,
    frames: u64,
}

fn weight(ch: usize, total: usize) -> f64 {
    if total >= 5 && (ch == 3 || ch == 4) {
        1.41
    } else if total >= 6 && (ch == 4 || ch == 5) {
        1.41
    } else {
        1.0
    }
}

impl LoudnessMeter {
    pub fn new(sample_rate: f64, channels: usize) -> Self {
        let sr = if sample_rate > 1000.0 { sample_rate } else { 44100.0 };
        let ch = channels.clamp(1, 8);
        let sub_len = (sr * 0.1).round() as usize;
        LoudnessMeter {
            sample_rate: sr,
            channels: ch,
            shelf: Coeffs::design(sr, SHELF_F0, SHELF_G, SHELF_Q, crate::biquad::Shape::HighShelf),
            hp: Coeffs::high_pass(sr, HP_F0, HP_Q),
            shelf_state: vec![State64::default(); ch],
            hp_state: vec![State64::default(); ch],
            sub_len,
            sub_fill: 0,
            sub_acc: vec![0.0; ch],
            ring: Vec::new(),
            ring_len: 4,
            blocks: Vec::new(),
            short_ring: Vec::new(),
            peak: 0.0,
            momentary: f64::NEG_INFINITY,
            short_term: f64::NEG_INFINITY,
            frames: 0,
        }
    }

    pub fn reset(&mut self) {
        for s in self.shelf_state.iter_mut() {
            s.reset();
        }
        for s in self.hp_state.iter_mut() {
            s.reset();
        }
        self.sub_fill = 0;
        self.sub_acc.iter_mut().for_each(|v| *v = 0.0);
        self.ring.clear();
        self.blocks.clear();
        self.short_ring.clear();
        self.peak = 0.0;
        self.momentary = f64::NEG_INFINITY;
        self.short_term = f64::NEG_INFINITY;
        self.frames = 0;
    }

    fn block_loudness(sums: &[f64], len: usize, channels: usize) -> f64 {
        let mut acc = 0.0;
        for c in 0..channels {
            acc += weight(c, channels) * sums[c] / len as f64;
        }
        if acc <= 0.0 {
            f64::NEG_INFINITY
        } else {
            OFFSET + 10.0 * acc.log10()
        }
    }

    fn close_subblock(&mut self) {
        let acc = self.sub_acc.clone();
        self.sub_acc.iter_mut().for_each(|v| *v = 0.0);
        self.ring.push(acc);
        if self.ring.len() > 30 {
            self.ring.remove(0);
        }

        let n = self.ring.len();
        if n >= self.ring_len {
            let mut sums = vec![0.0; self.channels];
            for i in n - self.ring_len..n {
                for c in 0..self.channels {
                    sums[c] += self.ring[i][c];
                }
            }
            let l = Self::block_loudness(&sums, self.sub_len * self.ring_len, self.channels);
            self.momentary = l;
            if l > ABS_GATE {
                self.blocks.push(l);
            }
        }

        if n >= 30 {
            let mut sums = vec![0.0; self.channels];
            for i in n - 30..n {
                for c in 0..self.channels {
                    sums[c] += self.ring[i][c];
                }
            }
            self.short_term = Self::block_loudness(&sums, self.sub_len * 30, self.channels);
            self.short_ring.push(self.short_term);
        }
    }

    pub fn feed(&mut self, buf: &[f32], channels: usize) {
        let ch = channels.clamp(1, 8).min(self.channels);
        let frames = buf.len() / channels.max(1);
        for f in 0..frames {
            let base = f * channels;
            for c in 0..ch {
                let x = buf[base + c];
                let a = x.abs();
                if a > self.peak {
                    self.peak = a;
                }
                let y = self.hp_state.get_mut(c).unwrap().step(
                    self.shelf_state.get_mut(c).unwrap().step(x as f64, &self.shelf),
                    &self.hp,
                );
                self.sub_acc[c] += y * y;
            }
            self.sub_fill += 1;
            if self.sub_fill >= self.sub_len {
                self.sub_fill = 0;
                self.close_subblock();
            }
        }
        self.frames += frames as u64;
    }

    pub fn integrated(&self) -> f64 {
        if self.blocks.is_empty() {
            return f64::NEG_INFINITY;
        }
        let mean_pow = |set: &[f64]| -> f64 {
            let mut acc = 0.0;
            for l in set {
                acc += 10f64.powf((l - OFFSET) / 10.0);
            }
            acc / set.len() as f64
        };
        let first = mean_pow(&self.blocks);
        if first <= 0.0 {
            return f64::NEG_INFINITY;
        }
        let rel = OFFSET + 10.0 * first.log10() - 10.0;
        let gated: Vec<f64> = self.blocks.iter().copied().filter(|l| *l > rel).collect();
        if gated.is_empty() {
            return f64::NEG_INFINITY;
        }
        let second = mean_pow(&gated);
        if second <= 0.0 {
            f64::NEG_INFINITY
        } else {
            OFFSET + 10.0 * second.log10()
        }
    }

    pub fn range(&self) -> f64 {
        if self.short_ring.len() < 4 {
            return 0.0;
        }
        let mut v: Vec<f64> = self
            .short_ring
            .iter()
            .copied()
            .filter(|l| l.is_finite() && *l > ABS_GATE)
            .collect();
        if v.len() < 4 {
            return 0.0;
        }
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let lo = v[(v.len() as f64 * 0.10) as usize];
        let hi = v[((v.len() as f64 * 0.95) as usize).min(v.len() - 1)];
        (hi - lo).max(0.0)
    }

    pub fn momentary(&self) -> f64 {
        self.momentary
    }

    pub fn short_term(&self) -> f64 {
        self.short_term
    }

    pub fn peak(&self) -> f32 {
        self.peak
    }

    pub fn gain_db(&self, target_lufs: f64) -> f64 {
        let i = self.integrated();
        if !i.is_finite() {
            return 0.0;
        }
        let want = target_lufs - i;
        let headroom = if self.peak > 0.0 {
            -20.0 * (self.peak as f64).log10()
        } else {
            24.0
        };
        want.min(headroom).clamp(-24.0, 24.0)
    }

    pub fn duration(&self) -> f64 {
        self.frames as f64 / self.sample_rate
    }
}
