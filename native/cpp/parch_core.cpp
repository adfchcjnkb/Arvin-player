#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace {

struct Fft {
    int n = 0;
    int bits = 0;
    std::vector<float> wr, wi;
    std::vector<int> rev;

    void init(int size) {
        n = size;
        bits = 0;
        while ((1 << bits) < n) ++bits;
        wr.resize(n / 2);
        wi.resize(n / 2);
        for (int i = 0; i < n / 2; ++i) {
            double a = -2.0 * M_PI * (double)i / (double)n;
            wr[i] = (float)std::cos(a);
            wi[i] = (float)std::sin(a);
        }
        rev.resize(n);
        for (int i = 0; i < n; ++i) {
            int r = 0;
            for (int b = 0; b < bits; ++b)
                if (i & (1 << b)) r |= 1 << (bits - 1 - b);
            rev[i] = r;
        }
    }

    void run(float *re, float *im) const {
        for (int i = 0; i < n; ++i) {
            int j = rev[i];
            if (j > i) {
                std::swap(re[i], re[j]);
                std::swap(im[i], im[j]);
            }
        }
        for (int len = 2; len <= n; len <<= 1) {
            const int half = len >> 1;
            const int step = n / len;
            for (int i = 0; i < n; i += len) {
                int t = 0;
                for (int k = 0; k < half; ++k, t += step) {
                    const float cr = wr[t], ci = wi[t];
                    const float xr = re[i + k + half], xi = im[i + k + half];
                    const float tr = xr * cr - xi * ci;
                    const float ti = xr * ci + xi * cr;
                    re[i + k + half] = re[i + k] - tr;
                    im[i + k + half] = im[i + k] - ti;
                    re[i + k] += tr;
                    im[i + k] += ti;
                }
            }
        }
    }
};

int next_pow2(int v) {
    int n = 1;
    while (n < v) n <<= 1;
    return n;
}

void hann(std::vector<float> &w, int n) {
    w.resize(n);
    for (int i = 0; i < n; ++i)
        w[i] = 0.5f - 0.5f * (float)std::cos(2.0 * M_PI * (double)i / (double)(n - 1));
}

struct F32View {
    Py_buffer view;
    bool held = false;
    const float *data = nullptr;
    Py_ssize_t count = 0;

    bool acquire(PyObject *obj) {
        if (PyObject_GetBuffer(obj, &view, PyBUF_ANY_CONTIGUOUS | PyBUF_FORMAT) != 0) return false;
        held = true;
        if (view.itemsize != (Py_ssize_t)sizeof(float) ||
            (view.format && std::strcmp(view.format, "f") != 0)) {
            PyErr_SetString(PyExc_TypeError, "expected a contiguous float32 buffer");
            return false;
        }
        data = (const float *)view.buf;
        count = view.len / (Py_ssize_t)sizeof(float);
        return true;
    }

    ~F32View() {
        if (held) PyBuffer_Release(&view);
    }
};

const int kBarkEdges[] = {100,  200,  300,  400,  510,  630,  770,   920,
                          1080, 1270, 1480, 1720, 2000, 2320, 2700,  3150,
                          3700, 4400, 5300, 6400, 7700, 9500, 12000, 15500};
const int kBarkCount = (int)(sizeof(kBarkEdges) / sizeof(kBarkEdges[0]));

int bark_of(double freq) {
    for (int i = 0; i < kBarkCount; ++i)
        if (freq < (double)kBarkEdges[i]) return i;
    return kBarkCount - 1;
}

void contrast_stretch(std::vector<float> &v) {
    const size_t n = v.size();
    if (n < 3) return;
    float mini = v[0], maxi = v[0];
    for (size_t i = 1; i < n; ++i) {
        mini = std::min(mini, v[i]);
        maxi = std::max(maxi, v[i]);
    }
    if (maxi <= mini) {
        std::fill(v.begin(), v.end(), 0.0f);
        return;
    }

    double avg = 0.0;
    size_t cnt = 0;
    for (size_t i = 0; i < n; ++i) {
        if (v[i] != mini && v[i] != maxi) {
            avg += (double)v[i];
            ++cnt;
        }
    }
    if (cnt == 0) {
        std::fill(v.begin(), v.end(), 0.0f);
        return;
    }
    avg /= (double)cnt;

    double up = 0.0, down = 0.0;
    size_t nu = 0, nd = 0;
    for (size_t i = 0; i < n; ++i) {
        if (v[i] == mini || v[i] == maxi) continue;
        if ((double)v[i] > avg) {
            up += v[i];
            ++nu;
        } else {
            down += v[i];
            ++nd;
        }
    }
    const double avgu = nu ? up / (double)nu : avg;
    const double avgb = nd ? down / (double)nd : avg;

    double uu = 0.0, bb = 0.0;
    size_t nuu = 0, nbb = 0;
    for (size_t i = 0; i < n; ++i) {
        if (v[i] == mini || v[i] == maxi) continue;
        if ((double)v[i] > avgu) {
            uu += v[i];
            ++nuu;
        } else if ((double)v[i] < avgb) {
            bb += v[i];
            ++nbb;
        }
    }
    const double avguu = nuu ? uu / (double)nuu : avg;
    const double avgbb = nbb ? bb / (double)nbb : avg;

    double lo = std::max(avg + (avgb - avg) * 2.0, avgbb);
    double hi = std::min(avg + (avgu - avg) * 2.0, avguu);
    double delta = hi - lo;
    if (!(delta > 1e-12)) delta = 1.0;

    for (size_t i = 0; i < n; ++i) {
        double t = ((double)v[i] - lo) / delta;
        if (!std::isfinite(t)) t = 0.0;
        v[i] = (float)std::max(0.0, std::min(1.0, t));
    }
}

void downmix(const float *src, Py_ssize_t count, int channels, std::vector<float> &out) {
    const Py_ssize_t frames = channels > 0 ? count / channels : 0;
    out.resize((size_t)frames);
    if (channels == 1) {
        std::memcpy(out.data(), src, (size_t)frames * sizeof(float));
        return;
    }
    const float inv = 1.0f / (float)channels;
    for (Py_ssize_t i = 0; i < frames; ++i) {
        float s = 0.0f;
        const float *p = src + i * channels;
        for (int c = 0; c < channels; ++c) s += p[c];
        out[(size_t)i] = s * inv;
    }
}

/* ---- spectrum ---- */

struct SpectrumObject {
    PyObject_HEAD
    Fft *fft;
    int size;
    int bars;
    int fill;
    double rate;
    float floor_db;
    float ceil_db;
    float attack;
    float release;
    float tilt;
    std::vector<float> *win;
    std::vector<float> *ring;
    std::vector<float> *re;
    std::vector<float> *im;
    std::vector<float> *mag;
    std::vector<float> *level;
    std::vector<float> *peak;
    std::vector<float> *fall;
    std::vector<int> *lo;
    std::vector<int> *hi;
    std::vector<float> *center;
    std::vector<float> *mono;
};

void spectrum_edges(SpectrumObject *s) {
    const double nyq = s->rate * 0.5;
    const double fmin = 28.0;
    const double fmax = std::min(19000.0, nyq * 0.96);
    const double bin_hz = s->rate / (double)s->size;
    const int max_bin = s->size / 2 - 1;
    s->lo->resize((size_t)s->bars);
    s->hi->resize((size_t)s->bars);
    s->center->resize((size_t)s->bars);
    int prev = 1;
    for (int i = 0; i < s->bars; ++i) {
        const double t0 = (double)i / (double)s->bars;
        const double t1 = (double)(i + 1) / (double)s->bars;
        const double f0 = fmin * std::pow(fmax / fmin, t0);
        const double f1 = fmin * std::pow(fmax / fmin, t1);
        const double fc = std::sqrt(f0 * f1);
        (*s->center)[(size_t)i] =
            (float)std::max(1.0, std::min((double)max_bin, fc / bin_hz));
        int b0 = (int)std::floor(f0 / bin_hz);
        int b1 = (int)std::ceil(f1 / bin_hz);
        b0 = std::max(1, std::min(b0, max_bin));
        b1 = std::max(b0 + 1, std::min(b1, max_bin + 1));
        if (b0 < prev) b0 = prev;
        if (b1 <= b0) b1 = b0 + 1;
        if (b1 > max_bin + 1) {
            b1 = max_bin + 1;
            b0 = std::min(b0, b1 - 1);
        }
        (*s->lo)[(size_t)i] = b0;
        (*s->hi)[(size_t)i] = b1;
        prev = b0;
    }
}

void spectrum_analyse(SpectrumObject *s) {
    const int n = s->size;
    float *re = s->re->data();
    float *im = s->im->data();
    const float *w = s->win->data();
    const float *ring = s->ring->data();
    for (int i = 0; i < n; ++i) {
        re[i] = ring[i] * w[i];
        im[i] = 0.0f;
    }
    s->fft->run(re, im);

    float *mag = s->mag->data();
    const int half = n / 2;
    const float scale = 2.0f / (float)n;
    for (int i = 0; i < half; ++i)
        mag[i] = std::sqrt(re[i] * re[i] + im[i] * im[i]) * scale;

    const double bin_hz = s->rate / (double)n;
    const float span = s->ceil_db - s->floor_db;
    for (int b = 0; b < s->bars; ++b) {
        const int b0 = (*s->lo)[(size_t)b];
        const int b1 = (*s->hi)[(size_t)b];
        float rms;
        if (b1 - b0 <= 1) {
            const float c = (*s->center)[(size_t)b];
            const int k0 = std::min((int)c, half - 2);
            const float frac = c - (float)k0;
            const float m0 = mag[k0], m1 = mag[k0 + 1];
            const float f = (float)(bin_hz * (double)c);
            rms = (m0 + (m1 - m0) * frac) * std::pow(f * 0.001f, s->tilt);
        } else {
            float acc = 0.0f;
            for (int k = b0; k < b1; ++k) {
                const float f = (float)(bin_hz * (double)k);
                const float lift = std::pow(f * 0.001f, s->tilt);
                const float m = mag[k] * lift;
                acc += m * m;
            }
            rms = std::sqrt(acc / (float)(b1 - b0));
        }
        float db = 20.0f * std::log10(rms + 1e-9f);
        float v = (db - s->floor_db) / span;
        v = std::max(0.0f, std::min(1.0f, v));
        v = std::pow(v, 0.82f);

        float &cur = (*s->level)[(size_t)b];
        const float k = v > cur ? s->attack : s->release;
        cur += (v - cur) * k;

        float &pk = (*s->peak)[(size_t)b];
        float &vel = (*s->fall)[(size_t)b];
        if (cur >= pk) {
            pk = cur;
            vel = 0.0f;
        } else {
            vel += 0.0016f;
            pk = std::max(cur, pk - vel);
        }
    }
}

PyObject *spectrum_levels_list(SpectrumObject *s) {
    PyObject *out = PyList_New(s->bars);
    if (!out) return nullptr;
    for (int i = 0; i < s->bars; ++i) {
        PyObject *v = PyFloat_FromDouble((double)(*s->level)[(size_t)i]);
        if (!v) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, i, v);
    }
    return out;
}

PyObject *Spectrum_new(PyTypeObject *type, PyObject *, PyObject *) {
    SpectrumObject *s = (SpectrumObject *)type->tp_alloc(type, 0);
    if (!s) return nullptr;
    s->fft = new Fft();
    s->win = new std::vector<float>();
    s->ring = new std::vector<float>();
    s->re = new std::vector<float>();
    s->im = new std::vector<float>();
    s->mag = new std::vector<float>();
    s->level = new std::vector<float>();
    s->peak = new std::vector<float>();
    s->fall = new std::vector<float>();
    s->lo = new std::vector<int>();
    s->hi = new std::vector<int>();
    s->center = new std::vector<float>();
    s->mono = new std::vector<float>();
    return (PyObject *)s;
}

int Spectrum_init(SpectrumObject *s, PyObject *args, PyObject *kwds) {
    static const char *kw[] = {"bars", "sample_rate", "fft_size", "floor_db", "ceil_db", nullptr};
    int bars = 96;
    double rate = 44100.0;
    int size = 2048;
    double floor_db = -74.0;
    double ceil_db = -6.0;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|idIdd", (char **)kw, &bars, &rate, &size,
                                     &floor_db, &ceil_db))
        return -1;

    s->bars = std::max(4, std::min(bars, 512));
    s->rate = rate > 1000.0 ? rate : 44100.0;
    s->size = std::max(256, std::min(next_pow2(size), 16384));
    s->floor_db = (float)floor_db;
    s->ceil_db = (float)std::max(floor_db + 6.0, ceil_db);
    s->attack = 0.55f;
    s->release = 0.14f;
    s->tilt = 0.34f;
    s->fill = 0;

    s->fft->init(s->size);
    hann(*s->win, s->size);
    s->ring->assign((size_t)s->size, 0.0f);
    s->re->resize((size_t)s->size);
    s->im->resize((size_t)s->size);
    s->mag->resize((size_t)(s->size / 2));
    s->level->assign((size_t)s->bars, 0.0f);
    s->peak->assign((size_t)s->bars, 0.0f);
    s->fall->assign((size_t)s->bars, 0.0f);
    spectrum_edges(s);
    return 0;
}

void Spectrum_dealloc(SpectrumObject *s) {
    delete s->fft;
    delete s->win;
    delete s->ring;
    delete s->re;
    delete s->im;
    delete s->mag;
    delete s->level;
    delete s->peak;
    delete s->fall;
    delete s->lo;
    delete s->hi;
    delete s->center;
    delete s->mono;
    Py_TYPE(s)->tp_free((PyObject *)s);
}

PyObject *Spectrum_feed(SpectrumObject *s, PyObject *args) {
    PyObject *obj;
    int channels = 2;
    if (!PyArg_ParseTuple(args, "Oi", &obj, &channels)) return nullptr;
    if (channels < 1) channels = 1;

    F32View v;
    if (!v.acquire(obj)) return nullptr;

    downmix(v.data, v.count, channels, *s->mono);
    const std::vector<float> &m = *s->mono;
    const int n = s->size;
    float *ring = s->ring->data();

    if ((int)m.size() >= n) {
        std::memcpy(ring, m.data() + (m.size() - (size_t)n), (size_t)n * sizeof(float));
    } else if (!m.empty()) {
        const int k = (int)m.size();
        std::memmove(ring, ring + k, (size_t)(n - k) * sizeof(float));
        std::memcpy(ring + (n - k), m.data(), (size_t)k * sizeof(float));
    }

    Py_BEGIN_ALLOW_THREADS
    spectrum_analyse(s);
    Py_END_ALLOW_THREADS

    return spectrum_levels_list(s);
}

PyObject *Spectrum_decay(SpectrumObject *s, PyObject *args) {
    double factor = 0.82;
    if (!PyArg_ParseTuple(args, "|d", &factor)) return nullptr;
    const float f = (float)std::max(0.0, std::min(1.0, factor));
    for (int i = 0; i < s->bars; ++i) {
        (*s->level)[(size_t)i] *= f;
        float &pk = (*s->peak)[(size_t)i];
        float &vel = (*s->fall)[(size_t)i];
        vel += 0.0016f;
        pk = std::max((*s->level)[(size_t)i], pk - vel);
    }
    return spectrum_levels_list(s);
}

PyObject *Spectrum_levels(SpectrumObject *s, PyObject *) { return spectrum_levels_list(s); }

PyObject *Spectrum_peaks(SpectrumObject *s, PyObject *) {
    PyObject *out = PyList_New(s->bars);
    if (!out) return nullptr;
    for (int i = 0; i < s->bars; ++i) {
        PyObject *v = PyFloat_FromDouble((double)(*s->peak)[(size_t)i]);
        if (!v) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, i, v);
    }
    return out;
}

PyObject *Spectrum_set_sample_rate(SpectrumObject *s, PyObject *args) {
    double rate;
    if (!PyArg_ParseTuple(args, "d", &rate)) return nullptr;
    if (rate > 1000.0 && std::fabs(rate - s->rate) > 0.5) {
        s->rate = rate;
        spectrum_edges(s);
    }
    Py_RETURN_NONE;
}

PyObject *Spectrum_set_bars(SpectrumObject *s, PyObject *args) {
    int bars;
    if (!PyArg_ParseTuple(args, "i", &bars)) return nullptr;
    bars = std::max(4, std::min(bars, 512));
    if (bars != s->bars) {
        s->bars = bars;
        s->level->assign((size_t)bars, 0.0f);
        s->peak->assign((size_t)bars, 0.0f);
        s->fall->assign((size_t)bars, 0.0f);
        spectrum_edges(s);
    }
    Py_RETURN_NONE;
}

PyObject *Spectrum_set_response(SpectrumObject *s, PyObject *args, PyObject *kwds) {
    static const char *kw[] = {"attack", "release", "tilt", nullptr};
    double attack = s->attack, release = s->release, tilt = s->tilt;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|ddd", (char **)kw, &attack, &release, &tilt))
        return nullptr;
    s->attack = (float)std::max(0.01, std::min(1.0, attack));
    s->release = (float)std::max(0.01, std::min(1.0, release));
    s->tilt = (float)std::max(0.0, std::min(1.5, tilt));
    Py_RETURN_NONE;
}

PyObject *Spectrum_reset(SpectrumObject *s, PyObject *) {
    std::fill(s->ring->begin(), s->ring->end(), 0.0f);
    std::fill(s->level->begin(), s->level->end(), 0.0f);
    std::fill(s->peak->begin(), s->peak->end(), 0.0f);
    std::fill(s->fall->begin(), s->fall->end(), 0.0f);
    Py_RETURN_NONE;
}

PyMethodDef Spectrum_methods[] = {
    {"feed", (PyCFunction)Spectrum_feed, METH_VARARGS, "analyse a chunk"},
    {"decay", (PyCFunction)Spectrum_decay, METH_VARARGS, "idle fade"},
    {"levels", (PyCFunction)Spectrum_levels, METH_NOARGS, "current bars"},
    {"peaks", (PyCFunction)Spectrum_peaks, METH_NOARGS, "peak holds"},
    {"set_sample_rate", (PyCFunction)Spectrum_set_sample_rate, METH_VARARGS, "retune bands"},
    {"set_bars", (PyCFunction)Spectrum_set_bars, METH_VARARGS, "bar count"},
    {"set_response", (PyCFunction)Spectrum_set_response, METH_VARARGS | METH_KEYWORDS, "ballistics"},
    {"reset", (PyCFunction)Spectrum_reset, METH_NOARGS, "clear"},
    {nullptr, nullptr, 0, nullptr},
};

PyTypeObject SpectrumType = {
    PyVarObject_HEAD_INIT(nullptr, 0) "parch_core.Spectrum",
};

/* ---- track analyzer ---- */

struct AnalyzerObject {
    PyObject_HEAD
    Fft *fft;
    int size;
    int hop;
    int fill;
    double rate;
    std::vector<float> *win;
    std::vector<float> *buf;
    std::vector<float> *re;
    std::vector<float> *im;
    std::vector<float> *prev;
    std::vector<float> *mono;
    std::vector<float> *bass;
    std::vector<float> *mid;
    std::vector<float> *treble;
    std::vector<float> *peak;
    std::vector<float> *rms;
    std::vector<float> *flux;
    std::vector<int> *bark;
    double sq_sum;
    double abs_peak;
    long long frames;
};

void analyzer_frame(AnalyzerObject *a) {
    const int n = a->size;
    float *re = a->re->data();
    float *im = a->im->data();
    const float *w = a->win->data();
    const float *src = a->buf->data();

    float pk = 0.0f;
    double sq = 0.0;
    for (int i = 0; i < a->hop; ++i) {
        const float s = src[i];
        pk = std::max(pk, std::fabs(s));
        sq += (double)s * (double)s;
    }
    a->peak->push_back(pk);
    a->rms->push_back((float)std::sqrt(sq / (double)a->hop));

    for (int i = 0; i < n; ++i) {
        re[i] = src[i] * w[i];
        im[i] = 0.0f;
    }
    a->fft->run(re, im);

    const int half = n / 2;
    const double bin_hz = a->rate / (double)n;
    const float scale = 2.0f / (float)n;

    double banks[kBarkCount] = {0.0};
    float diff = 0.0f;
    std::vector<float> &prev = *a->prev;
    const int *bark = a->bark->data();
    for (int k = 1; k < half; ++k) {
        const float mag = std::sqrt(re[k] * re[k] + im[k] * im[k]) * scale;
        banks[bark[k]] += (double)mag;
        const float d = mag - prev[(size_t)k];
        if (d > 0.0f) diff += d;
        prev[(size_t)k] = mag;
    }
    (void)bin_hz;

    double rgb[3] = {0.0, 0.0, 0.0};
    for (int i = 0; i < kBarkCount; ++i) rgb[(i * 3) / kBarkCount] += banks[i] * banks[i];

    a->bass->push_back((float)std::sqrt(rgb[0]));
    a->mid->push_back((float)std::sqrt(rgb[1]));
    a->treble->push_back((float)std::sqrt(rgb[2]));
    a->flux->push_back(diff);
}

PyObject *Analyzer_new(PyTypeObject *type, PyObject *, PyObject *) {
    AnalyzerObject *a = (AnalyzerObject *)type->tp_alloc(type, 0);
    if (!a) return nullptr;
    a->fft = new Fft();
    a->win = new std::vector<float>();
    a->buf = new std::vector<float>();
    a->re = new std::vector<float>();
    a->im = new std::vector<float>();
    a->prev = new std::vector<float>();
    a->mono = new std::vector<float>();
    a->bass = new std::vector<float>();
    a->mid = new std::vector<float>();
    a->treble = new std::vector<float>();
    a->peak = new std::vector<float>();
    a->rms = new std::vector<float>();
    a->flux = new std::vector<float>();
    a->bark = new std::vector<int>();
    return (PyObject *)a;
}

int Analyzer_init(AnalyzerObject *a, PyObject *args, PyObject *kwds) {
    static const char *kw[] = {"sample_rate", "fft_size", nullptr};
    double rate = 44100.0;
    int size = 1024;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|di", (char **)kw, &rate, &size)) return -1;
    a->rate = rate > 1000.0 ? rate : 44100.0;
    a->size = std::max(256, std::min(next_pow2(size), 8192));
    a->hop = a->size / 2;
    a->fill = 0;
    a->sq_sum = 0.0;
    a->abs_peak = 0.0;
    a->frames = 0;
    a->fft->init(a->size);
    hann(*a->win, a->size);
    a->buf->assign((size_t)a->size, 0.0f);
    a->re->resize((size_t)a->size);
    a->im->resize((size_t)a->size);
    a->prev->assign((size_t)(a->size / 2), 0.0f);
    a->bark->resize((size_t)(a->size / 2));
    for (int k = 0; k < a->size / 2; ++k)
        (*a->bark)[(size_t)k] = bark_of(a->rate * (double)k / (double)a->size);
    return 0;
}

void Analyzer_dealloc(AnalyzerObject *a) {
    delete a->fft;
    delete a->win;
    delete a->buf;
    delete a->re;
    delete a->im;
    delete a->prev;
    delete a->mono;
    delete a->bass;
    delete a->mid;
    delete a->treble;
    delete a->peak;
    delete a->rms;
    delete a->flux;
    delete a->bark;
    Py_TYPE(a)->tp_free((PyObject *)a);
}

PyObject *Analyzer_feed(AnalyzerObject *a, PyObject *args) {
    PyObject *obj;
    int channels = 2;
    if (!PyArg_ParseTuple(args, "Oi", &obj, &channels)) return nullptr;
    if (channels < 1) channels = 1;

    F32View v;
    if (!v.acquire(obj)) return nullptr;

    downmix(v.data, v.count, channels, *a->mono);

    Py_BEGIN_ALLOW_THREADS
    const std::vector<float> &m = *a->mono;
    float *buf = a->buf->data();
    for (size_t i = 0; i < m.size(); ++i) {
        const float s = m[i];
        a->sq_sum += (double)s * (double)s;
        a->abs_peak = std::max(a->abs_peak, (double)std::fabs(s));
        buf[a->fill++] = s;
        if (a->fill == a->size) {
            analyzer_frame(a);
            std::memmove(buf, buf + a->hop, (size_t)a->hop * sizeof(float));
            a->fill = a->hop;
        }
    }
    a->frames += (long long)m.size();
    Py_END_ALLOW_THREADS

    Py_RETURN_NONE;
}

float resample_pick(const std::vector<float> &src, double t0, double t1) {
    if (src.empty()) return 0.0f;
    const double n = (double)src.size();
    int i0 = (int)std::floor(t0 * n);
    int i1 = (int)std::ceil(t1 * n);
    i0 = std::max(0, std::min(i0, (int)src.size() - 1));
    i1 = std::max(i0 + 1, std::min(i1, (int)src.size()));
    float best = 0.0f;
    for (int i = i0; i < i1; ++i) best = std::max(best, src[(size_t)i]);
    return best;
}

double estimate_bpm(const std::vector<float> &flux, double frame_rate) {
    const size_t n = flux.size();
    if (n < 64 || frame_rate <= 0.0) return 0.0;

    std::vector<double> env(n);
    double mean = 0.0;
    for (size_t i = 0; i < n; ++i) mean += flux[i];
    mean /= (double)n;
    for (size_t i = 0; i < n; ++i) env[i] = std::max(0.0, (double)flux[i] - mean);

    const int lag_min = std::max(2, (int)std::floor(frame_rate * 60.0 / 200.0));
    const int lag_max = std::min((int)n - 2, (int)std::ceil(frame_rate * 60.0 / 55.0));
    if (lag_max <= lag_min) return 0.0;

    double best_score = 0.0;
    int best_lag = 0;
    std::vector<double> score((size_t)(lag_max + 1), 0.0);
    for (int lag = lag_min; lag <= lag_max; ++lag) {
        double acc = 0.0;
        for (size_t i = (size_t)lag; i < n; ++i) acc += env[i] * env[i - (size_t)lag];
        acc /= (double)(n - (size_t)lag);
        score[(size_t)lag] = acc;
        if (acc > best_score) {
            best_score = acc;
            best_lag = lag;
        }
    }
    if (best_lag <= 0) return 0.0;

    double lag = (double)best_lag;
    if (best_lag > lag_min && best_lag < lag_max) {
        const double y0 = score[(size_t)best_lag - 1];
        const double y1 = score[(size_t)best_lag];
        const double y2 = score[(size_t)best_lag + 1];
        const double den = y0 - 2.0 * y1 + y2;
        if (std::fabs(den) > 1e-12) lag += 0.5 * (y0 - y2) / den;
    }

    double bpm = frame_rate * 60.0 / lag;
    while (bpm < 70.0) bpm *= 2.0;
    while (bpm > 190.0) bpm *= 0.5;
    return bpm;
}

PyObject *Analyzer_finish(AnalyzerObject *a, PyObject *args, PyObject *kwds) {
    static const char *kw[] = {"columns", "buckets", nullptr};
    int columns = 128;
    int buckets = 600;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|ii", (char **)kw, &columns, &buckets))
        return nullptr;
    columns = std::max(8, std::min(columns, 2048));
    buckets = std::max(8, std::min(buckets, 8192));

    const size_t nf = a->bass->size();
    PyObject *dict = PyDict_New();
    if (!dict) return nullptr;

    PyObject *mood = nullptr;
    PyObject *wave = nullptr;

    if (nf > 0) {
        contrast_stretch(*a->bass);
        contrast_stretch(*a->mid);
        contrast_stretch(*a->treble);

        std::vector<unsigned char> rgb((size_t)columns * 3, 0);
        for (int c = 0; c < columns; ++c) {
            const double t0 = (double)c / (double)columns;
            const double t1 = (double)(c + 1) / (double)columns;
            size_t i0 = (size_t)(t0 * (double)nf);
            size_t i1 = (size_t)(t1 * (double)nf);
            i0 = std::min(i0, nf - 1);
            i1 = std::max(i0 + 1, std::min(i1, nf));
            double bs = 0.0, ms = 0.0, ts = 0.0;
            for (size_t i = i0; i < i1; ++i) {
                bs += (*a->bass)[i];
                ms += (*a->mid)[i];
                ts += (*a->treble)[i];
            }
            const double cnt = (double)(i1 - i0);
            rgb[(size_t)c * 3 + 0] = (unsigned char)std::lround(std::min(1.0, bs / cnt) * 255.0);
            rgb[(size_t)c * 3 + 1] = (unsigned char)std::lround(std::min(1.0, ms / cnt) * 255.0);
            rgb[(size_t)c * 3 + 2] = (unsigned char)std::lround(std::min(1.0, ts / cnt) * 255.0);
        }
        mood = PyBytes_FromStringAndSize((const char *)rgb.data(), (Py_ssize_t)rgb.size());

        float wmax = 1e-9f;
        for (size_t i = 0; i < a->peak->size(); ++i) wmax = std::max(wmax, (*a->peak)[i]);
        wave = PyList_New(buckets);
        if (wave) {
            for (int i = 0; i < buckets; ++i) {
                const double t0 = (double)i / (double)buckets;
                const double t1 = (double)(i + 1) / (double)buckets;
                const float v = resample_pick(*a->peak, t0, t1) / wmax;
                PyObject *o = PyFloat_FromDouble((double)std::min(1.0f, v));
                if (!o) {
                    Py_CLEAR(wave);
                    break;
                }
                PyList_SET_ITEM(wave, i, o);
            }
        }
    }

    if (!mood) mood = PyBytes_FromStringAndSize("", 0);
    if (!wave) wave = PyList_New(0);

    const double frame_rate = a->rate / (double)a->hop;
    const double bpm = estimate_bpm(*a->flux, frame_rate);
    const double rms = a->frames > 0 ? std::sqrt(a->sq_sum / (double)a->frames) : 0.0;

    PyDict_SetItemString(dict, "moodbar", mood);
    PyDict_SetItemString(dict, "waveform", wave);
    Py_DECREF(mood);
    Py_DECREF(wave);
    PyObject *tmp;
    tmp = PyFloat_FromDouble(bpm);
    PyDict_SetItemString(dict, "bpm", tmp);
    Py_DECREF(tmp);
    tmp = PyFloat_FromDouble(a->abs_peak);
    PyDict_SetItemString(dict, "peak", tmp);
    Py_DECREF(tmp);
    tmp = PyFloat_FromDouble(rms);
    PyDict_SetItemString(dict, "rms", tmp);
    Py_DECREF(tmp);
    tmp = PyFloat_FromDouble(a->frames > 0 ? (double)a->frames / a->rate : 0.0);
    PyDict_SetItemString(dict, "duration", tmp);
    Py_DECREF(tmp);
    return dict;
}

PyObject *Analyzer_reset(AnalyzerObject *a, PyObject *) {
    a->fill = 0;
    a->sq_sum = 0.0;
    a->abs_peak = 0.0;
    a->frames = 0;
    std::fill(a->buf->begin(), a->buf->end(), 0.0f);
    std::fill(a->prev->begin(), a->prev->end(), 0.0f);
    a->bass->clear();
    a->mid->clear();
    a->treble->clear();
    a->peak->clear();
    a->rms->clear();
    a->flux->clear();
    Py_RETURN_NONE;
}

PyMethodDef Analyzer_methods[] = {
    {"feed", (PyCFunction)Analyzer_feed, METH_VARARGS, "accumulate pcm"},
    {"finish", (PyCFunction)Analyzer_finish, METH_VARARGS | METH_KEYWORDS, "results"},
    {"reset", (PyCFunction)Analyzer_reset, METH_NOARGS, "clear"},
    {nullptr, nullptr, 0, nullptr},
};

PyTypeObject AnalyzerType = {
    PyVarObject_HEAD_INIT(nullptr, 0) "parch_core.TrackAnalyzer",
};

/* ---- module functions ---- */

PyObject *mod_levels(PyObject *, PyObject *args) {
    PyObject *obj;
    int channels = 2;
    if (!PyArg_ParseTuple(args, "Oi", &obj, &channels)) return nullptr;
    F32View v;
    if (!v.acquire(obj)) return nullptr;
    if (channels < 1) channels = 1;

    double sq = 0.0;
    float pk = 0.0f;
    const Py_ssize_t n = v.count;
    const float *d = v.data;
    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t i = 0; i < n; ++i) {
        const float s = d[i];
        sq += (double)s * (double)s;
        const float a = std::fabs(s);
        if (a > pk) pk = a;
    }
    Py_END_ALLOW_THREADS
    const double rms = n > 0 ? std::sqrt(sq / (double)n) : 0.0;
    return Py_BuildValue("dd", (double)pk, rms);
}

PyObject *mod_stereo_balance(PyObject *, PyObject *args) {
    PyObject *obj;
    int channels = 2;
    if (!PyArg_ParseTuple(args, "Oi", &obj, &channels)) return nullptr;
    F32View v;
    if (!v.acquire(obj)) return nullptr;
    if (channels < 2) return Py_BuildValue("dd", 0.0, 0.0);

    const Py_ssize_t frames = v.count / channels;
    double l = 0.0, r = 0.0;
    for (Py_ssize_t i = 0; i < frames; ++i) {
        const float a = v.data[i * channels];
        const float b = v.data[i * channels + 1];
        l += (double)a * a;
        r += (double)b * b;
    }
    if (frames > 0) {
        l = std::sqrt(l / (double)frames);
        r = std::sqrt(r / (double)frames);
    }
    return Py_BuildValue("dd", l, r);
}

PyObject *mod_waveform(PyObject *, PyObject *args) {
    PyObject *obj;
    int channels = 2;
    int buckets = 600;
    if (!PyArg_ParseTuple(args, "Oii", &obj, &channels, &buckets)) return nullptr;
    F32View v;
    if (!v.acquire(obj)) return nullptr;
    if (channels < 1) channels = 1;
    buckets = std::max(1, std::min(buckets, 8192));

    std::vector<float> mono;
    downmix(v.data, v.count, channels, mono);
    PyObject *out = PyList_New(buckets);
    if (!out) return nullptr;
    const size_t n = mono.size();
    for (int i = 0; i < buckets; ++i) {
        size_t i0 = n ? (size_t)((double)i / buckets * (double)n) : 0;
        size_t i1 = n ? (size_t)((double)(i + 1) / buckets * (double)n) : 0;
        i1 = std::max(i0 + 1, std::min(i1, n));
        float pk = 0.0f;
        for (size_t k = i0; k < i1 && k < n; ++k) pk = std::max(pk, std::fabs(mono[k]));
        PyObject *o = PyFloat_FromDouble((double)pk);
        if (!o) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, i, o);
    }
    return out;
}

/* ---- equalizer ---- */

const int EQ_MAX_CHANNELS = 8;
const float EQ_SLEW_DB_PER_S = 140.0f;
const float EQ_SCALAR_TAU = 0.035f;
const float EQ_LIMIT_T = 0.94f;

enum EqShape { EQ_LOWSHELF, EQ_PEAKING, EQ_HIGHSHELF };

struct EqCoeffs {
    double b0, b1, b2, a1, a2;
};

struct EqState {
    float z1, z2;
};

EqCoeffs eq_design(double sample_rate, double freq, double gain_db, double q, EqShape shape) {
    const double sr = sample_rate > 8000.0 ? sample_rate : 8000.0;
    double f0 = freq;
    if (f0 < 10.0) f0 = 10.0;
    if (f0 > sr * 0.49) f0 = sr * 0.49;
    if (q < 0.05) q = 0.05;

    const double a = std::pow(10.0, gain_db / 40.0);
    const double w0 = 2.0 * M_PI * f0 / sr;
    const double cs = std::cos(w0);
    const double sn = std::sin(w0);
    const double alpha = sn / (2.0 * q);
    double b0, b1, b2, a0, a1, a2;

    if (shape == EQ_LOWSHELF) {
        const double t = 2.0 * std::sqrt(a) * alpha;
        b0 = a * ((a + 1.0) - (a - 1.0) * cs + t);
        b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cs);
        b2 = a * ((a + 1.0) - (a - 1.0) * cs - t);
        a0 = (a + 1.0) + (a - 1.0) * cs + t;
        a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cs);
        a2 = (a + 1.0) + (a - 1.0) * cs - t;
    } else if (shape == EQ_HIGHSHELF) {
        const double t = 2.0 * std::sqrt(a) * alpha;
        b0 = a * ((a + 1.0) + (a - 1.0) * cs + t);
        b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cs);
        b2 = a * ((a + 1.0) + (a - 1.0) * cs - t);
        a0 = (a + 1.0) - (a - 1.0) * cs + t;
        a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cs);
        a2 = (a + 1.0) - (a - 1.0) * cs - t;
    } else {
        b0 = 1.0 + alpha * a;
        b1 = -2.0 * cs;
        b2 = 1.0 - alpha * a;
        a0 = 1.0 + alpha / a;
        a1 = -2.0 * cs;
        a2 = 1.0 - alpha / a;
    }

    EqCoeffs c;
    c.b0 = b0 / a0;
    c.b1 = b1 / a0;
    c.b2 = b2 / a0;
    c.a1 = a1 / a0;
    c.a2 = a2 / a0;
    return c;
}

double eq_magnitude(const EqCoeffs &c, double w) {
    const double c1 = std::cos(w), s1 = std::sin(w);
    const double c2 = std::cos(2.0 * w), s2 = std::sin(2.0 * w);
    const double nr = c.b0 + c.b1 * c1 + c.b2 * c2;
    const double ni = -(c.b1 * s1 + c.b2 * s2);
    const double dr = 1.0 + c.a1 * c1 + c.a2 * c2;
    const double di = -(c.a1 * s1 + c.a2 * s2);
    const double num = std::sqrt(nr * nr + ni * ni);
    double den = std::sqrt(dr * dr + di * di);
    if (den < 1e-12) den = 1e-12;
    return num / den;
}

std::vector<double> eq_layout(int bands) {
    if (bands == 5) return {80, 250, 1000, 4000, 12000};
    if (bands == 15)
        return {25, 40, 63, 100, 160, 250, 400, 630, 1000,
                1600, 2500, 4000, 6300, 10000, 16000};
    if (bands == 31)
        return {20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200,
                250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000,
                2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000};
    return {31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
}

struct EqualizerObject {
    PyObject_HEAD
    std::vector<double> *centers;
    std::vector<float> *target;
    std::vector<float> *current;
    std::vector<EqCoeffs> *coeffs;
    std::vector<EqState> *states;
    double rate;
    double q;
    float preamp;
    float replaygain;
    float auto_lin;
    float scalar_cur;
    float scalar_target;
    float reduction;
    int auto_gain;
    int bypass;
};

EqShape eq_shape(EqualizerObject *e, size_t i) {
    if (i == 0) return EQ_LOWSHELF;
    if (i + 1 == e->centers->size()) return EQ_HIGHSHELF;
    return EQ_PEAKING;
}

void eq_redesign(EqualizerObject *e, size_t i) {
    (*e->coeffs)[i] = eq_design(e->rate, (*e->centers)[i],
                                (double)(*e->current)[i], e->q, eq_shape(e, i));
}

void eq_redesign_all(EqualizerObject *e) {
    for (size_t i = 0; i < e->centers->size(); ++i) eq_redesign(e, i);
}

double eq_combined_peak_db(EqualizerObject *e) {
    bool any = false;
    for (size_t i = 0; i < e->target->size(); ++i)
        if (std::fabs((*e->target)[i]) > 0.01f) any = true;
    if (!any) return 0.0;

    const double nyq = e->rate * 0.5;
    const double f_lo = 18.0;
    double f_hi = nyq * 0.94;
    if (f_hi < f_lo * 2.0) f_hi = f_lo * 2.0;

    std::vector<EqCoeffs> design(e->centers->size());
    for (size_t i = 0; i < e->centers->size(); ++i)
        design[i] = eq_design(e->rate, (*e->centers)[i],
                              (double)(*e->target)[i], e->q, eq_shape(e, i));

    const int steps = 220;
    double peak = 0.0;
    for (int k = 0; k <= steps; ++k) {
        const double t = (double)k / (double)steps;
        const double f = f_lo * std::pow(f_hi / f_lo, t);
        const double w = 2.0 * M_PI * f / e->rate;
        double mag = 1.0;
        for (size_t i = 0; i < design.size(); ++i) mag *= eq_magnitude(design[i], w);
        if (mag > peak) peak = mag;
    }
    return peak <= 1e-9 ? 0.0 : 20.0 * std::log10(peak);
}

void eq_recompute_auto(EqualizerObject *e) {
    if (e->auto_gain) {
        const float peak = std::pow(10.0f, (float)eq_combined_peak_db(e) / 20.0f);
        float denom = peak * e->preamp * e->replaygain;
        if (denom < 1.0f) denom = 1.0f;
        e->auto_lin = 1.0f / denom;
    } else {
        e->auto_lin = 1.0f;
    }
    e->scalar_target = e->preamp * e->replaygain * e->auto_lin;
}

void eq_resize(EqualizerObject *e, int bands) {
    std::vector<double> centers = eq_layout(bands);
    *e->centers = centers;
    e->target->assign(centers.size(), 0.0f);
    e->current->assign(centers.size(), 0.0f);
    e->coeffs->assign(centers.size(), EqCoeffs{1.0, 0.0, 0.0, 0.0, 0.0});
    e->states->assign(centers.size() * (size_t)EQ_MAX_CHANNELS, EqState{0.0f, 0.0f});
    eq_redesign_all(e);
    eq_recompute_auto(e);
}

PyObject *Eq_new(PyTypeObject *type, PyObject *, PyObject *) {
    EqualizerObject *e = (EqualizerObject *)type->tp_alloc(type, 0);
    if (!e) return nullptr;
    e->centers = new std::vector<double>();
    e->target = new std::vector<float>();
    e->current = new std::vector<float>();
    e->coeffs = new std::vector<EqCoeffs>();
    e->states = new std::vector<EqState>();
    return (PyObject *)e;
}

int Eq_init(EqualizerObject *e, PyObject *args, PyObject *kwds) {
    static const char *kw[] = {"bands", "sample_rate", nullptr};
    int bands = 10;
    double rate = 44100.0;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|id", (char **)kw, &bands, &rate))
        return -1;
    e->rate = rate > 1000.0 ? rate : 44100.0;
    e->q = 1.0;
    e->preamp = 1.0f;
    e->replaygain = 1.0f;
    e->auto_lin = 1.0f;
    e->scalar_cur = 1.0f;
    e->scalar_target = 1.0f;
    e->reduction = 0.0f;
    e->auto_gain = 1;
    e->bypass = 0;
    eq_resize(e, bands);
    return 0;
}

void Eq_dealloc(EqualizerObject *e) {
    delete e->centers;
    delete e->target;
    delete e->current;
    delete e->coeffs;
    delete e->states;
    Py_TYPE(e)->tp_free((PyObject *)e);
}

PyObject *Eq_set_gains(EqualizerObject *e, PyObject *args) {
    PyObject *seq;
    if (!PyArg_ParseTuple(args, "O", &seq)) return nullptr;
    PyObject *fast = PySequence_Fast(seq, "expected a sequence of gains");
    if (!fast) return nullptr;
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(fast);
    for (size_t i = 0; i < e->target->size(); ++i) {
        double value = 0.0;
        if ((Py_ssize_t)i < n) {
            PyObject *item = PySequence_Fast_GET_ITEM(fast, (Py_ssize_t)i);
            value = PyFloat_AsDouble(item);
            if (PyErr_Occurred()) {
                Py_DECREF(fast);
                return nullptr;
            }
        }
        if (value < -24.0) value = -24.0;
        if (value > 24.0) value = 24.0;
        (*e->target)[i] = (float)value;
    }
    Py_DECREF(fast);
    eq_recompute_auto(e);
    Py_RETURN_NONE;
}

PyObject *Eq_set_band(EqualizerObject *e, PyObject *args) {
    int index;
    double gain;
    if (!PyArg_ParseTuple(args, "id", &index, &gain)) return nullptr;
    if (index >= 0 && (size_t)index < e->target->size()) {
        if (gain < -24.0) gain = -24.0;
        if (gain > 24.0) gain = 24.0;
        (*e->target)[(size_t)index] = (float)gain;
        eq_recompute_auto(e);
    }
    Py_RETURN_NONE;
}

PyObject *Eq_gains(EqualizerObject *e, PyObject *) {
    PyObject *out = PyList_New((Py_ssize_t)e->target->size());
    if (!out) return nullptr;
    for (size_t i = 0; i < e->target->size(); ++i) {
        PyObject *v = PyFloat_FromDouble((double)(*e->target)[i]);
        if (!v) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, (Py_ssize_t)i, v);
    }
    return out;
}

PyObject *Eq_set_layout(EqualizerObject *e, PyObject *args) {
    int bands;
    if (!PyArg_ParseTuple(args, "i", &bands)) return nullptr;
    if (eq_layout(bands).size() != e->centers->size()) eq_resize(e, bands);
    Py_RETURN_NONE;
}

PyObject *Eq_set_sample_rate(EqualizerObject *e, PyObject *args) {
    double rate;
    if (!PyArg_ParseTuple(args, "d", &rate)) return nullptr;
    if (rate > 1000.0 && std::fabs(rate - e->rate) > 0.5) {
        e->rate = rate;
        eq_redesign_all(e);
        eq_recompute_auto(e);
        for (size_t i = 0; i < e->states->size(); ++i) (*e->states)[i] = EqState{0.0f, 0.0f};
    }
    Py_RETURN_NONE;
}

PyObject *Eq_set_preamp_db(EqualizerObject *e, PyObject *args) {
    double db;
    if (!PyArg_ParseTuple(args, "d", &db)) return nullptr;
    if (db < -24.0) db = -24.0;
    if (db > 24.0) db = 24.0;
    e->preamp = std::pow(10.0f, (float)db / 20.0f);
    eq_recompute_auto(e);
    Py_RETURN_NONE;
}

PyObject *Eq_set_replaygain_db(EqualizerObject *e, PyObject *args) {
    double db;
    if (!PyArg_ParseTuple(args, "d", &db)) return nullptr;
    if (db < -24.0) db = -24.0;
    if (db > 24.0) db = 24.0;
    e->replaygain = std::pow(10.0f, (float)db / 20.0f);
    eq_recompute_auto(e);
    Py_RETURN_NONE;
}

PyObject *Eq_set_auto_gain(EqualizerObject *e, PyObject *args) {
    int enabled;
    if (!PyArg_ParseTuple(args, "p", &enabled)) return nullptr;
    e->auto_gain = enabled ? 1 : 0;
    eq_recompute_auto(e);
    Py_RETURN_NONE;
}

PyObject *Eq_set_bypass(EqualizerObject *e, PyObject *args) {
    int bypass;
    if (!PyArg_ParseTuple(args, "p", &bypass)) return nullptr;
    e->bypass = bypass ? 1 : 0;
    Py_RETURN_NONE;
}

PyObject *Eq_set_q(EqualizerObject *e, PyObject *args) {
    double q;
    if (!PyArg_ParseTuple(args, "d", &q)) return nullptr;
    if (q < 0.3) q = 0.3;
    if (q > 6.0) q = 6.0;
    e->q = q;
    eq_redesign_all(e);
    eq_recompute_auto(e);
    Py_RETURN_NONE;
}

PyObject *Eq_reset(EqualizerObject *e, PyObject *) {
    for (size_t i = 0; i < e->states->size(); ++i) (*e->states)[i] = EqState{0.0f, 0.0f};
    for (size_t i = 0; i < e->current->size(); ++i) (*e->current)[i] = (*e->target)[i];
    eq_redesign_all(e);
    eq_recompute_auto(e);
    e->scalar_cur = e->scalar_target;
    e->reduction = 0.0f;
    Py_RETURN_NONE;
}

void eq_advance_gains(EqualizerObject *e, size_t frames) {
    float max_step = EQ_SLEW_DB_PER_S * (float)frames / (float)e->rate;
    if (max_step < 0.2f) max_step = 0.2f;
    for (size_t i = 0; i < e->target->size(); ++i) {
        const float diff = (*e->target)[i] - (*e->current)[i];
        if (std::fabs(diff) <= 1e-3f) continue;
        float step = diff;
        if (step > max_step) step = max_step;
        if (step < -max_step) step = -max_step;
        (*e->current)[i] += step;
        if (std::fabs((*e->target)[i] - (*e->current)[i]) < 1e-2f)
            (*e->current)[i] = (*e->target)[i];
        eq_redesign(e, i);
    }
}

PyObject *Eq_process(EqualizerObject *e, PyObject *args) {
    PyObject *obj;
    int channels;
    if (!PyArg_ParseTuple(args, "Oi", &obj, &channels)) return nullptr;

    Py_buffer view;
    if (PyObject_GetBuffer(obj, &view, PyBUF_WRITABLE | PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) != 0)
        return nullptr;
    if (view.itemsize != (Py_ssize_t)sizeof(float) ||
        (view.format && std::strcmp(view.format, "f") != 0)) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_TypeError, "expected a writable float32 buffer");
        return nullptr;
    }

    float *buf = (float *)view.buf;
    const size_t count = (size_t)(view.len / (Py_ssize_t)sizeof(float));
    int ch = channels;
    if (ch < 1) ch = 1;
    if (ch > EQ_MAX_CHANNELS) ch = EQ_MAX_CHANNELS;
    const size_t frames = count / (size_t)ch;

    if (frames == 0) {
        PyBuffer_Release(&view);
        Py_RETURN_NONE;
    }

    Py_BEGIN_ALLOW_THREADS
    if (e->bypass) {
        const float g = e->replaygain;
        if (std::fabs(g - 1.0f) > 1e-6f)
            for (size_t i = 0; i < count; ++i) buf[i] *= g;
    } else {
        eq_advance_gains(e, frames);

        float denom = (float)e->rate * EQ_SCALAR_TAU;
        if (denom < 1.0f) denom = 1.0f;
        float alpha = (float)frames / denom;
        if (alpha > 1.0f) alpha = 1.0f;
        const float start = e->scalar_cur;
        const float end = start + (e->scalar_target - start) * alpha;
        const float step = frames > 1 ? (end - start) / (float)(frames - 1) : 0.0f;
        e->scalar_cur = end;

        const size_t nbands = e->centers->size();
        const EqCoeffs *coeffs = e->coeffs->data();
        EqState *states = e->states->data();
        float worst = 0.0f;

        for (size_t f = 0; f < frames; ++f) {
            const float g = start + step * (float)f;
            const size_t base = f * (size_t)ch;
            for (int c = 0; c < ch; ++c) {
                const size_t idx = base + (size_t)c;
                float x = buf[idx] * g;
                for (size_t b = 0; b < nbands; ++b) {
                    EqState &st = states[b * (size_t)EQ_MAX_CHANNELS + (size_t)c];
                    const EqCoeffs &co = coeffs[b];
                    const float y = (float)co.b0 * x + st.z1;
                    st.z1 = (float)co.b1 * x - (float)co.a1 * y + st.z2;
                    st.z2 = (float)co.b2 * x - (float)co.a2 * y;
                    x = y;
                }
                const float a = std::fabs(x);
                if (a > EQ_LIMIT_T) {
                    const float knee = (a - EQ_LIMIT_T) / (1.0f - EQ_LIMIT_T);
                    const float shaped = EQ_LIMIT_T + (1.0f - EQ_LIMIT_T) * std::tanh(knee);
                    const float g2 = shaped / a;
                    if (worst == 0.0f || g2 < worst) worst = g2;
                    x *= g2;
                }
                buf[idx] = x;
            }
        }

        const float inst = (worst > 0.0f && worst < 1.0f) ? -20.0f * std::log10(worst) : 0.0f;
        e->reduction = inst > e->reduction ? inst : e->reduction * 0.7f;
    }
    Py_END_ALLOW_THREADS

    PyBuffer_Release(&view);
    Py_RETURN_NONE;
}

PyObject *Eq_get_bands(EqualizerObject *e, void *) {
    return PyLong_FromSsize_t((Py_ssize_t)e->centers->size());
}

PyObject *Eq_get_centers(EqualizerObject *e, void *) {
    PyObject *out = PyList_New((Py_ssize_t)e->centers->size());
    if (!out) return nullptr;
    for (size_t i = 0; i < e->centers->size(); ++i) {
        PyObject *v = PyFloat_FromDouble((*e->centers)[i]);
        if (!v) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, (Py_ssize_t)i, v);
    }
    return out;
}

PyObject *Eq_get_auto_gain(EqualizerObject *e, void *) {
    return PyBool_FromLong(e->auto_gain);
}

PyObject *Eq_get_headroom(EqualizerObject *e, void *) {
    float lin = e->auto_lin < 1e-6f ? 1e-6f : e->auto_lin;
    return PyFloat_FromDouble(20.0 * std::log10((double)lin));
}

PyObject *Eq_get_reduction(EqualizerObject *e, void *) {
    return PyFloat_FromDouble((double)e->reduction);
}

PyMethodDef Eq_methods[] = {
    {"set_gains", (PyCFunction)Eq_set_gains, METH_VARARGS, "band gains"},
    {"set_band", (PyCFunction)Eq_set_band, METH_VARARGS, "one band"},
    {"gains", (PyCFunction)Eq_gains, METH_NOARGS, "current gains"},
    {"set_layout", (PyCFunction)Eq_set_layout, METH_VARARGS, "band count"},
    {"set_sample_rate", (PyCFunction)Eq_set_sample_rate, METH_VARARGS, "retune"},
    {"set_preamp_db", (PyCFunction)Eq_set_preamp_db, METH_VARARGS, "preamp"},
    {"set_replaygain_db", (PyCFunction)Eq_set_replaygain_db, METH_VARARGS, "normalisation"},
    {"set_auto_gain", (PyCFunction)Eq_set_auto_gain, METH_VARARGS, "headroom"},
    {"set_bypass", (PyCFunction)Eq_set_bypass, METH_VARARGS, "bypass"},
    {"set_q", (PyCFunction)Eq_set_q, METH_VARARGS, "band width"},
    {"reset", (PyCFunction)Eq_reset, METH_NOARGS, "clear"},
    {"process", (PyCFunction)Eq_process, METH_VARARGS, "filter in place"},
    {nullptr, nullptr, 0, nullptr},
};

PyGetSetDef Eq_getset[] = {
    {(char *)"bands", (getter)Eq_get_bands, nullptr, (char *)"band count", nullptr},
    {(char *)"centers", (getter)Eq_get_centers, nullptr, (char *)"centres", nullptr},
    {(char *)"auto_gain", (getter)Eq_get_auto_gain, nullptr, (char *)"headroom", nullptr},
    {(char *)"headroom_db", (getter)Eq_get_headroom, nullptr, (char *)"headroom dB", nullptr},
    {(char *)"reduction_db", (getter)Eq_get_reduction, nullptr, (char *)"limiter dB", nullptr},
    {nullptr, nullptr, nullptr, nullptr, nullptr},
};

PyTypeObject EqualizerType = {
    PyVarObject_HEAD_INIT(nullptr, 0) "parch_core.Equalizer",
};

PyObject *mod_band_centers(PyObject *, PyObject *args) {
    int bands;
    if (!PyArg_ParseTuple(args, "i", &bands)) return nullptr;
    std::vector<double> centers = eq_layout(bands);
    PyObject *out = PyList_New((Py_ssize_t)centers.size());
    if (!out) return nullptr;
    for (size_t i = 0; i < centers.size(); ++i) {
        PyObject *v = PyFloat_FromDouble(centers[i]);
        if (!v) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, (Py_ssize_t)i, v);
    }
    return out;
}

PyMethodDef module_methods[] = {
    {"band_centers", mod_band_centers, METH_VARARGS, "layout"},
    {"levels", mod_levels, METH_VARARGS, "peak and rms"},
    {"stereo_balance", mod_stereo_balance, METH_VARARGS, "per side rms"},
    {"waveform", mod_waveform, METH_VARARGS, "peak envelope"},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT, "parch_core", "Parch MP analysis core", -1, module_methods,
};

}  // namespace

PyMODINIT_FUNC PyInit_parch_core(void) {
    SpectrumType.tp_basicsize = sizeof(SpectrumObject);
    SpectrumType.tp_itemsize = 0;
    SpectrumType.tp_flags = Py_TPFLAGS_DEFAULT;
    SpectrumType.tp_new = Spectrum_new;
    SpectrumType.tp_init = (initproc)Spectrum_init;
    SpectrumType.tp_dealloc = (destructor)Spectrum_dealloc;
    SpectrumType.tp_methods = Spectrum_methods;
    SpectrumType.tp_doc = "realtime spectrum";

    AnalyzerType.tp_basicsize = sizeof(AnalyzerObject);
    AnalyzerType.tp_itemsize = 0;
    AnalyzerType.tp_flags = Py_TPFLAGS_DEFAULT;
    AnalyzerType.tp_new = Analyzer_new;
    AnalyzerType.tp_init = (initproc)Analyzer_init;
    AnalyzerType.tp_dealloc = (destructor)Analyzer_dealloc;
    AnalyzerType.tp_methods = Analyzer_methods;
    AnalyzerType.tp_doc = "offline track analysis";

    EqualizerType.tp_basicsize = sizeof(EqualizerObject);
    EqualizerType.tp_itemsize = 0;
    EqualizerType.tp_flags = Py_TPFLAGS_DEFAULT;
    EqualizerType.tp_new = Eq_new;
    EqualizerType.tp_init = (initproc)Eq_init;
    EqualizerType.tp_dealloc = (destructor)Eq_dealloc;
    EqualizerType.tp_methods = Eq_methods;
    EqualizerType.tp_getset = Eq_getset;
    EqualizerType.tp_doc = "graphic equalizer";

    if (PyType_Ready(&SpectrumType) < 0) return nullptr;
    if (PyType_Ready(&AnalyzerType) < 0) return nullptr;
    if (PyType_Ready(&EqualizerType) < 0) return nullptr;

    PyObject *m = PyModule_Create(&module_def);
    if (!m) return nullptr;

    Py_INCREF(&SpectrumType);
    if (PyModule_AddObject(m, "Spectrum", (PyObject *)&SpectrumType) < 0) {
        Py_DECREF(&SpectrumType);
        Py_DECREF(m);
        return nullptr;
    }
    Py_INCREF(&AnalyzerType);
    if (PyModule_AddObject(m, "TrackAnalyzer", (PyObject *)&AnalyzerType) < 0) {
        Py_DECREF(&AnalyzerType);
        Py_DECREF(m);
        return nullptr;
    }
    Py_INCREF(&EqualizerType);
    if (PyModule_AddObject(m, "Equalizer", (PyObject *)&EqualizerType) < 0) {
        Py_DECREF(&EqualizerType);
        Py_DECREF(m);
        return nullptr;
    }
    PyModule_AddStringConstant(m, "__version__", "1.1.0");
    return m;
}
