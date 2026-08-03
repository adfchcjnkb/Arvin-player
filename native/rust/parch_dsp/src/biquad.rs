use std::f64::consts::PI;

#[derive(Clone, Copy, Debug)]
pub enum Shape {
    LowShelf,
    Peaking,
    HighShelf,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Coeffs {
    pub b0: f64,
    pub b1: f64,
    pub b2: f64,
    pub a1: f64,
    pub a2: f64,
}

impl Coeffs {
    pub fn identity() -> Self {
        Coeffs { b0: 1.0, b1: 0.0, b2: 0.0, a1: 0.0, a2: 0.0 }
    }

    pub fn design(sample_rate: f64, freq: f64, gain_db: f64, q: f64, shape: Shape) -> Self {
        let sr = sample_rate.max(8000.0);
        let f0 = freq.clamp(10.0, sr * 0.49);
        let q = q.max(0.05);
        let a = 10f64.powf(gain_db / 40.0);
        let w0 = 2.0 * PI * f0 / sr;
        let (sin_w0, cos_w0) = w0.sin_cos();
        let alpha = sin_w0 / (2.0 * q);

        let (b0, b1, b2, a0, a1, a2) = match shape {
            Shape::LowShelf => {
                let t = 2.0 * a.sqrt() * alpha;
                (
                    a * ((a + 1.0) - (a - 1.0) * cos_w0 + t),
                    2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0),
                    a * ((a + 1.0) - (a - 1.0) * cos_w0 - t),
                    (a + 1.0) + (a - 1.0) * cos_w0 + t,
                    -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0),
                    (a + 1.0) + (a - 1.0) * cos_w0 - t,
                )
            }
            Shape::HighShelf => {
                let t = 2.0 * a.sqrt() * alpha;
                (
                    a * ((a + 1.0) + (a - 1.0) * cos_w0 + t),
                    -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0),
                    a * ((a + 1.0) + (a - 1.0) * cos_w0 - t),
                    (a + 1.0) - (a - 1.0) * cos_w0 + t,
                    2.0 * ((a - 1.0) - (a + 1.0) * cos_w0),
                    (a + 1.0) - (a - 1.0) * cos_w0 - t,
                )
            }
            Shape::Peaking => (
                1.0 + alpha * a,
                -2.0 * cos_w0,
                1.0 - alpha * a,
                1.0 + alpha / a,
                -2.0 * cos_w0,
                1.0 - alpha / a,
            ),
        };

        Coeffs { b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 }
    }

    pub fn high_pass(sample_rate: f64, freq: f64, q: f64) -> Self {
        let sr = sample_rate.max(8000.0);
        let f0 = freq.clamp(1.0, sr * 0.49);
        let w0 = 2.0 * PI * f0 / sr;
        let (sin_w0, cos_w0) = w0.sin_cos();
        let alpha = sin_w0 / (2.0 * q.max(0.05));
        let a0 = 1.0 + alpha;
        Coeffs {
            b0: (1.0 + cos_w0) / 2.0 / a0,
            b1: -(1.0 + cos_w0) / a0,
            b2: (1.0 + cos_w0) / 2.0 / a0,
            a1: (-2.0 * cos_w0) / a0,
            a2: (1.0 - alpha) / a0,
        }
    }

    pub fn magnitude(&self, w: f64) -> f64 {
        let (s1, c1) = w.sin_cos();
        let (s2, c2) = (2.0 * w).sin_cos();
        let nr = self.b0 + self.b1 * c1 + self.b2 * c2;
        let ni = -(self.b1 * s1 + self.b2 * s2);
        let dr = 1.0 + self.a1 * c1 + self.a2 * c2;
        let di = -(self.a1 * s1 + self.a2 * s2);
        let num = (nr * nr + ni * ni).sqrt();
        let den = (dr * dr + di * di).sqrt().max(1e-12);
        num / den
    }
}

#[derive(Clone, Copy, Default)]
pub struct State {
    z1: f32,
    z2: f32,
}

impl State {
    #[inline(always)]
    pub fn step(&mut self, x: f32, c: &Coeffs) -> f32 {
        let b0 = c.b0 as f32;
        let b1 = c.b1 as f32;
        let b2 = c.b2 as f32;
        let a1 = c.a1 as f32;
        let a2 = c.a2 as f32;
        let y = b0 * x + self.z1;
        self.z1 = b1 * x - a1 * y + self.z2;
        self.z2 = b2 * x - a2 * y;
        y
    }

    pub fn reset(&mut self) {
        self.z1 = 0.0;
        self.z2 = 0.0;
    }
}

#[derive(Clone, Copy, Default)]
pub struct State64 {
    z1: f64,
    z2: f64,
}

impl State64 {
    #[inline(always)]
    pub fn step(&mut self, x: f64, c: &Coeffs) -> f64 {
        let y = c.b0 * x + self.z1;
        self.z1 = c.b1 * x - c.a1 * y + self.z2;
        self.z2 = c.b2 * x - c.a2 * y;
        y
    }

    pub fn reset(&mut self) {
        self.z1 = 0.0;
        self.z2 = 0.0;
    }
}

pub fn layout(bands: usize) -> Vec<f64> {
    match bands {
        5 => vec![80.0, 250.0, 1000.0, 4000.0, 12000.0],
        15 => vec![
            25.0, 40.0, 63.0, 100.0, 160.0, 250.0, 400.0, 630.0, 1000.0, 1600.0, 2500.0, 4000.0,
            6300.0, 10000.0, 16000.0,
        ],
        31 => vec![
            20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0, 200.0, 250.0, 315.0,
            400.0, 500.0, 630.0, 800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0,
            5000.0, 6300.0, 8000.0, 10000.0, 12500.0, 16000.0, 20000.0,
        ],
        _ => vec![
            31.0, 62.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0,
        ],
    }
}
