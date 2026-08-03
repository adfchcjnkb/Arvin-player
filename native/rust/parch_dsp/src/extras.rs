pub fn fuzzy_score(query: &str, target: &str) -> Option<i32> {
    if query.is_empty() {
        return Some(0);
    }
    let q: Vec<char> = query.chars().flat_map(|c| c.to_lowercase()).collect();
    let t: Vec<char> = target.chars().collect();
    let tl: Vec<char> = target.chars().flat_map(|c| c.to_lowercase()).collect();

    let mut score = 0i32;
    let mut qi = 0usize;
    let mut prev_match: isize = -2;
    let mut streak = 0i32;

    for (i, ch) in tl.iter().enumerate() {
        if qi >= q.len() {
            break;
        }
        if *ch != q[qi] {
            continue;
        }
        let boundary = i == 0
            || matches!(tl[i - 1], ' ' | '-' | '_' | '/' | '.' | '(' | '[' | ',')
            || (t[i].is_uppercase() && !t[i - 1].is_uppercase());
        if boundary {
            score += 14;
        }
        if i as isize == prev_match + 1 {
            streak += 1;
            score += 8 + streak.min(6) * 2;
        } else {
            streak = 0;
            score -= ((i as isize - prev_match - 1).min(12) * 2) as i32;
        }
        if i < 4 {
            score += 6 - i as i32;
        }
        prev_match = i as isize;
        qi += 1;
    }

    if qi < q.len() {
        return None;
    }
    score += 20 - (tl.len().min(60) as i32) / 6;
    Some(score)
}

pub fn resample_linear(input: &[f32], channels: usize, from_rate: f64, to_rate: f64) -> Vec<f32> {
    let ch = channels.max(1);
    let frames = input.len() / ch;
    if frames == 0 || from_rate <= 0.0 || to_rate <= 0.0 {
        return Vec::new();
    }
    if (from_rate - to_rate).abs() < 0.5 {
        return input.to_vec();
    }
    let ratio = to_rate / from_rate;
    let out_frames = ((frames as f64) * ratio).floor() as usize;
    let mut out = vec![0.0f32; out_frames * ch];
    for i in 0..out_frames {
        let pos = i as f64 / ratio;
        let i0 = pos.floor() as usize;
        let frac = (pos - i0 as f64) as f32;
        let i1 = (i0 + 1).min(frames - 1);
        for c in 0..ch {
            let a = input[i0 * ch + c];
            let b = input[i1 * ch + c];
            out[i * ch + c] = a + (b - a) * frac;
        }
    }
    out
}

pub struct Crossfader {
    total: usize,
    pos: usize,
}

impl Crossfader {
    pub fn new(sample_rate: f64, seconds: f64) -> Self {
        let sr = if sample_rate > 1000.0 { sample_rate } else { 44100.0 };
        Crossfader { total: (sr * seconds.clamp(0.1, 20.0)).round() as usize, pos: 0 }
    }

    pub fn reset(&mut self) {
        self.pos = 0;
    }

    pub fn done(&self) -> bool {
        self.pos >= self.total
    }

    pub fn progress(&self) -> f32 {
        if self.total == 0 {
            1.0
        } else {
            (self.pos as f32 / self.total as f32).min(1.0)
        }
    }

    pub fn mix(&mut self, dst: &mut [f32], src: &[f32], channels: usize) -> bool {
        let ch = channels.max(1);
        let dst_frames = dst.len() / ch;
        let src_frames = src.len() / ch;
        let half_pi = std::f32::consts::FRAC_PI_2;
        for f in 0..dst_frames {
            let t = if self.total == 0 {
                1.0
            } else {
                ((self.pos + f) as f32 / self.total as f32).min(1.0)
            };
            let g_out = (t * half_pi).cos();
            let g_in = (t * half_pi).sin();
            for c in 0..ch {
                let idx = f * ch + c;
                let incoming = if f < src_frames { src[idx] } else { 0.0 };
                dst[idx] = dst[idx] * g_out + incoming * g_in;
            }
        }
        self.pos += dst_frames;
        self.done()
    }
}

pub fn apply_gain(buf: &mut [f32], gain: f32) {
    if (gain - 1.0).abs() < 1e-6 {
        return;
    }
    for s in buf.iter_mut() {
        *s *= gain;
    }
}

pub fn balance(buf: &mut [f32], channels: usize, pan: f32) {
    if channels < 2 || pan.abs() < 1e-4 {
        return;
    }
    let p = pan.clamp(-1.0, 1.0);
    let gl = if p > 0.0 { 1.0 - p } else { 1.0 };
    let gr = if p < 0.0 { 1.0 + p } else { 1.0 };
    let frames = buf.len() / channels;
    for f in 0..frames {
        buf[f * channels] *= gl;
        buf[f * channels + 1] *= gr;
    }
}
