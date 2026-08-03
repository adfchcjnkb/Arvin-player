# Parch MP

A fast, modern music player for **Linux and Windows**, built across
**three languages**: a Rust audio-processing core, a C++ analysis core,
and a PyQt6 interface. It has a real-time equalizer, an audio-reactive
visualizer, waveform and moodbar seeking, loudness normalisation, a
music library with smart search, and a 15-language, RTL-aware interface.

## Architecture

| Layer | Language | Module | Responsibility |
|---|---|---|---|
| Interface & app logic | Python (PyQt6) | `app/` | UI, playlist, library, playback control |
| Audio processing | Rust | `parch_dsp` | Equalizer, loudness (EBU R128), crossfade, resampling, fuzzy search |
| Signal analysis | C++ | `parch_core` | FFT, spectrum, moodbar, waveform, BPM |

Both native cores are optional. If a compiled core is missing, the app
falls back to the NumPy/SciPy implementation automatically and keeps
working — only slower. The active engine is shown in the tools menu and
via `ParchMP --selftest`.

### Why native cores

The equalizer runs on every decoded audio buffer, so it is the one place
where speed directly limits what the feature can do. Measured on a
5-second stereo buffer at 48 kHz:

| Bands | Rust core | Python/SciPy | Speed-up |
|---|---|---|---|
| 10 | 315x realtime | 118x realtime | 2.7x |
| 15 | 216x realtime | 84x realtime | 2.6x |
| 31 | 95x realtime | 41x realtime | 2.3x |

The headroom is what makes the 31-band layout and always-on loudness
metering practical rather than merely possible.

## Features

### Playback
- **Wide format support** — MP3, FLAC, WAV, OGG/Vorbis, Opus, M4A/AAC,
  WMA, AIFF, WavPack, Monkey's Audio, Musepack, TTA, AC3/DTS, DSF and
  more (decoded by Qt's FFmpeg backend). `.m3u`/`.pls` playlists are
  expanded into their tracks.
- **Real-time equalizer** — 10, 15 or 31 bands with 18 genre presets.
  Automatic headroom compensation keeps a boosted EQ clean instead of
  clipping, gain changes are smoothed so dragging a slider never clicks,
  and a soft-knee limiter rounds transient peaks.
- **Volume normalisation** — every track is measured against the EBU
  R128 / ITU-R BS.1770 loudness standard and replay-gained to a −18 LUFS
  target, so albums do not jump in level between tracks.
- **Playback speed** — 0.5x to 2x.
- **Play queue** — queue any track to play next, independent of the
  playlist order.
- **Sleep timer** — 5 to 120 minutes.

### Seeking and visuals
- **Waveform seek bar** — the decoded peak envelope of the current
  track; click or drag anywhere to seek.
- **Moodbar** — the Bark-band spectral colour map of the whole track
  (bass to red, mids to green, treble to blue), so the shape of a song
  is visible before playing it. Press `Ctrl+M` to switch between
  waveform and moodbar.
- **Audio-reactive visualizer** driven by a live FFT of the decoded
  audio, plus a vinyl view of the current cover.

### Library
- **Music library** — an SQLite catalogue of everything played, with
  play counts, skip counts, last-played time, ratings and favourites.
- **Smart search** — a query language over the library:
  ```
  artist:radiohead album:"ok computer"
  year:>=1990 genre:rock
  rating:>=4 playcount:>10
  length:>4:30 bpm:<100
  favorite:1 -genre:live
  added:<30days OR lastplayed:<7days
  ```
  Results can be added to the playlist or saved as a smart playlist that
  re-evaluates itself.
- **Album gallery** — cover-art grid browsing, double-click to play.
- **Statistics** — top tracks, top artists, recently played, recently
  added, never played, favourites, and a listening-hours clock.
- **BPM detection** — estimated per track during analysis.
- **Synced lyrics** — `.lrc` sidecar files or embedded lyrics tags,
  scrolling in time with playback; double-click a line to seek to it.
- **Archive import** — extract a `.zip` of music and import it in one
  step.

### Interface
- **Metadata editor** — right-click a track to edit its title, artist,
  album, genre, year and track number, or replace/remove its cover art.
  Changes are written directly into the file.
- **Playlist sorting** — by title (A–Z / Z–A), file date (newest /
  oldest), or duration.
- **15-language interface** with live switching, right-to-left support
  for Arabic and Persian, per-language fonts, and light/dark themes.
- **Hand-drawn icon set** — all 59 icons are vector geometry defined in
  `app/ui/icons.py`, drawn at runtime in the current theme colour. No
  external icon assets or icon fonts.

Track analysis (waveform, moodbar, loudness, BPM) runs on a background
thread the first time a track is played and is cached in the library, so
it costs nothing on later plays.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Play / pause |
| `←` / `→` | Seek 5 seconds |
| `Ctrl+F` | Smart search |
| `Ctrl+G` | Album gallery |
| `Ctrl+Q` | Queue |
| `Ctrl+Y` | Lyrics |
| `Ctrl+I` | Statistics |
| `Ctrl+E` | Equalizer |
| `Ctrl+M` | Waveform / moodbar |
| `Ctrl+Shift+F` | Favourite current track |
| `Ctrl+T` | Toggle theme |
| `Ctrl+L` | Toggle playlist |
| `F11` | Fullscreen |
| `Delete` | Remove selected |

## Building

```
pip install -r requirements.txt
python build.py
```

`build.py` compiles the Rust crate, compiles the C++ extension, copies
both into `lib/`, then packages everything with PyInstaller into
`dist/ParchMP`.

Useful flags:

```
python build.py --natives-only   # compile the cores, skip packaging
python build.py --skip-natives   # package using the cores already in lib/
```

Verify a build:

```
./dist/ParchMP --selftest
```

which prints the version and which engine is active
(`rust+c++`, `rust+numpy`, `python+c++` or `python+numpy`).

### Build requirements

- **Python 3.10+** with `PyQt6 >= 6.8` — the real-time visualizer and
  equalizer use `QAudioBufferOutput`, and the FFmpeg media backend
  (default from Qt 6.8) provides the broad format support.
- **Rust toolchain** (`cargo`) for `parch_dsp` — install from
  <https://rustup.rs>. Optional; without it the SciPy equalizer is used.
- **A C++17 compiler** for `parch_core` (GCC, Clang or MSVC). Optional;
  without it the NumPy analysis path is used.

To run from source without packaging:

```
python build.py --natives-only
python main.py
```

## Project structure

```
parch_mp/
├── main.py                 # Entry point
├── build.py                # Builds both native cores, then packages
├── requirements.txt
├── ParchMP.spec            # PyInstaller build spec
├── lib/                    # Compiled native cores land here
├── native/
│   ├── rust/parch_dsp/     # Rust: equalizer, loudness, crossfade, search
│   │   ├── Cargo.toml
│   │   └── src/{lib,eq,biquad,loudness,extras}.rs
│   ├── cpp/parch_core.cpp  # C++: FFT, spectrum, moodbar, waveform, BPM
│   └── setup_core.py
├── assets/
│   ├── icon.svg / icon.ico # App icon
│   └── fonts/              # Per-language .ttf files
└── app/
    ├── player.py           # Main window: playlist, playback, UI glue
    ├── features.py         # Library, queue, lyrics, gallery, stats, timers
    ├── library.py          # SQLite catalogue and playlists
    ├── filterquery.py      # Smart-search query parser
    ├── analysis.py         # Background track analysis worker
    ├── lyrics.py           # .lrc and embedded lyrics
    ├── native.py           # Native core loader with fallbacks
    ├── core.py             # Themes + metadata read/write (mutagen)
    ├── i18n.py             # Languages, UI strings, help content
    ├── utils.py            # Constants, paths, settings persistence
    ├── audio/
    │   ├── eq_engine.py    # Equalizer facade: Rust core or SciPy
    │   └── sink.py         # Real-time processed-audio sink
    └── ui/
        ├── icons.py        # Hand-drawn vector icon set
        ├── widgets.py      # Vinyl, visualizer, waveform bar, delegate
        ├── help_dialog.py  # Multilingual Help & About
        └── metadata_editor.py
```

## Data locations

| File | Contents |
|---|---|
| `~/.parchmp_settings.json` | Language, theme, volume, EQ, preferences |
| `~/.parchmp_playlist.json` | Last session's playlist |
| `~/.parchmp_library.db` | Library, play counts, ratings, analysis cache |

## Fonts

Fonts live in `assets/fonts/`. If a file is missing, the app falls back
to a system font instead of failing.

| Language(s) | Font file |
|---|---|
| Persian, Arabic (also the base font) | `Vazir.ttf` |
| English, Spanish, Portuguese, French, Russian, German, Turkish, Italian, Indonesian | `NotoSans-Regular.ttf` |
| Chinese (Simplified) | `NotoSansSC-Regular.ttf` |
| Hindi | `NotoSansDevanagari-Regular.ttf` |
| Japanese | `NotoSansJP-Regular.ttf` |
| Korean | `NotoSansKR-Regular.ttf` |

All are free (SIL Open Font License): the Noto family from
fonts.google.com/noto, and Vazir from github.com/rastikerdar/vazir-font.

## Translations

Interface and help text for the 15 languages were machine-translated.
New strings fall back to English until translated. A native-speaker
proofread is recommended before a public release.

## Acknowledgements

Feature and algorithm ideas were studied from three open-source players:
[Strawberry](https://github.com/strawberrymusicplayer/strawberry) (GPL-3),
[Tauon](https://github.com/Taiko2k/Tauon) (GPL-3) and
[nuclear](https://github.com/nukeop/nuclear) (AGPL-3) — in particular
Strawberry's Bark-band moodbar mapping and its smart-playlist filter
syntax. All code here is an independent implementation; no source was
copied from those projects.
