import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

from . import filterquery

log = logging.getLogger("parch_mp.library")

DB_PATH = Path.home() / ".parchmp_library.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    path         TEXT PRIMARY KEY,
    title        TEXT,
    artist       TEXT,
    album        TEXT,
    albumartist  TEXT,
    genre        TEXT,
    comment      TEXT,
    year         INTEGER DEFAULT 0,
    track_no     INTEGER DEFAULT 0,
    duration     REAL DEFAULT 0,
    sample_rate  INTEGER DEFAULT 0,
    bitrate      INTEGER DEFAULT 0,
    mtime        REAL DEFAULT 0,
    size         INTEGER DEFAULT 0,
    added        REAL DEFAULT 0,
    play_count   INTEGER DEFAULT 0,
    skip_count   INTEGER DEFAULT 0,
    last_played  REAL DEFAULT 0,
    rating       INTEGER DEFAULT 0,
    favorite     INTEGER DEFAULT 0,
    bpm          REAL DEFAULT 0,
    replaygain   REAL DEFAULT 0,
    lufs         REAL DEFAULT 0,
    peak         REAL DEFAULT 0,
    analyzed     REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album);
CREATE INDEX IF NOT EXISTS idx_tracks_played ON tracks(last_played);

CREATE TABLE IF NOT EXISTS analysis (
    path     TEXT PRIMARY KEY,
    mtime    REAL DEFAULT 0,
    moodbar  BLOB,
    waveform BLOB
);

CREATE TABLE IF NOT EXISTS playlists (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    kind    TEXT DEFAULT 'static',
    query   TEXT DEFAULT '',
    created REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id INTEGER NOT NULL,
    position    INTEGER NOT NULL,
    path        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_playlist ON playlist_items(playlist_id, position);

CREATE TABLE IF NOT EXISTS history (
    path    TEXT NOT NULL,
    played  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_time ON history(played);
"""

_FIELDS = (
    "title", "artist", "album", "albumartist", "genre", "comment", "year",
    "track_no", "duration", "sample_rate", "bitrate", "mtime", "size",
)


class Library:
    def __init__(self, path=None):
        self.path = str(path or DB_PATH)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.commit()

    def close(self):
        with self._lock:
            try:
                self._db.commit()
                self._db.close()
            except Exception:
                pass

    def _exec(self, sql, params=()):
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    def _query(self, sql, params=()):
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def upsert(self, path, meta=None):
        meta = meta or {}
        try:
            st = os.stat(path)
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            mtime, size = 0.0, 0

        row = {k: meta.get(k) for k in _FIELDS}
        row["mtime"] = mtime
        row["size"] = size
        for key in ("year", "track_no", "sample_rate", "bitrate"):
            try:
                row[key] = int(row.get(key) or 0)
            except (TypeError, ValueError):
                row[key] = 0
        try:
            row["duration"] = float(row.get("duration") or 0.0)
        except (TypeError, ValueError):
            row["duration"] = 0.0

        cols = ", ".join(_FIELDS)
        holes = ", ".join("?" for _ in _FIELDS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _FIELDS)
        self._exec(
            f"INSERT INTO tracks (path, added, {cols}) VALUES (?, ?, {holes}) "
            f"ON CONFLICT(path) DO UPDATE SET {updates}",
            (path, time.time()) + tuple(row[c] for c in _FIELDS),
        )

    def upsert_many(self, entries):
        with self._lock:
            now = time.time()
            for path, meta in entries:
                try:
                    st = os.stat(path)
                    mtime, size = st.st_mtime, st.st_size
                except OSError:
                    mtime, size = 0.0, 0
                meta = dict(meta or {})
                meta["mtime"] = mtime
                meta["size"] = size
                values = []
                for c in _FIELDS:
                    v = meta.get(c)
                    if c in ("year", "track_no", "sample_rate", "bitrate"):
                        try:
                            v = int(v or 0)
                        except (TypeError, ValueError):
                            v = 0
                    elif c in ("duration",):
                        try:
                            v = float(v or 0.0)
                        except (TypeError, ValueError):
                            v = 0.0
                    values.append(v)
                cols = ", ".join(_FIELDS)
                holes = ", ".join("?" for _ in _FIELDS)
                updates = ", ".join(f"{c}=excluded.{c}" for c in _FIELDS)
                self._db.execute(
                    f"INSERT INTO tracks (path, added, {cols}) VALUES (?, ?, {holes}) "
                    f"ON CONFLICT(path) DO UPDATE SET {updates}",
                    (path, now) + tuple(values),
                )
            self._db.commit()

    def get(self, path):
        rows = self._query("SELECT * FROM tracks WHERE path = ?", (path,))
        return dict(rows[0]) if rows else None

    def get_many(self, paths):
        if not paths:
            return {}
        out = {}
        chunk = 400
        with self._lock:
            for i in range(0, len(paths), chunk):
                part = paths[i:i + chunk]
                holes = ",".join("?" for _ in part)
                for row in self._db.execute(
                        f"SELECT * FROM tracks WHERE path IN ({holes})", part):
                    out[row["path"]] = dict(row)
        return out

    def forget(self, path):
        self._exec("DELETE FROM tracks WHERE path = ?", (path,))
        self._exec("DELETE FROM analysis WHERE path = ?", (path,))

    def note_play(self, path):
        now = time.time()
        self._exec(
            "UPDATE tracks SET play_count = play_count + 1, last_played = ? WHERE path = ?",
            (now, path),
        )
        self._exec("INSERT INTO history (path, played) VALUES (?, ?)", (path, now))

    def note_skip(self, path):
        self._exec("UPDATE tracks SET skip_count = skip_count + 1 WHERE path = ?", (path,))

    def set_rating(self, path, rating):
        self._exec("UPDATE tracks SET rating = ? WHERE path = ?",
                   (max(0, min(5, int(rating))), path))

    def set_favorite(self, path, favorite):
        self._exec("UPDATE tracks SET favorite = ? WHERE path = ?",
                   (1 if favorite else 0, path))

    def toggle_favorite(self, path):
        row = self.get(path)
        new = 0 if (row and row.get("favorite")) else 1
        self.set_favorite(path, new)
        return bool(new)

    def store_analysis(self, path, mtime, moodbar, waveform, bpm, lufs, replaygain, peak):
        self._exec(
            "INSERT INTO analysis (path, mtime, moodbar, waveform) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, "
            "moodbar=excluded.moodbar, waveform=excluded.waveform",
            (path, mtime, moodbar, waveform),
        )
        self._exec(
            "UPDATE tracks SET bpm = ?, lufs = ?, replaygain = ?, peak = ?, analyzed = ? "
            "WHERE path = ?",
            (bpm, lufs, replaygain, peak, time.time(), path),
        )

    def load_analysis(self, path, mtime=None):
        rows = self._query("SELECT * FROM analysis WHERE path = ?", (path,))
        if not rows:
            return None
        row = dict(rows[0])
        if mtime is not None and abs(float(row.get("mtime") or 0) - float(mtime)) > 1.0:
            return None
        return row

    def needs_analysis(self, path, mtime):
        return self.load_analysis(path, mtime) is None

    def search(self, text, limit=0, order="artist, album, track_no, title"):
        where, params = filterquery.to_sql(text)
        sql = f"SELECT * FROM tracks WHERE {where} ORDER BY {order}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self._query(sql, params)]

    def albums(self):
        rows = self._query(
            "SELECT IFNULL(NULLIF(albumartist,''), artist) AS aartist, album, "
            "COUNT(*) AS tracks, SUM(duration) AS length, MIN(path) AS sample, "
            "MAX(year) AS year "
            "FROM tracks WHERE IFNULL(album,'') <> '' "
            "GROUP BY LOWER(IFNULL(aartist,'')), LOWER(album) "
            "ORDER BY aartist, year, album"
        )
        return [dict(r) for r in rows]

    def album_tracks(self, artist, album):
        rows = self._query(
            "SELECT * FROM tracks WHERE LOWER(IFNULL(album,'')) = ? AND "
            "LOWER(IFNULL(NULLIF(albumartist,''), IFNULL(artist,''))) = ? "
            "ORDER BY track_no, title",
            ((album or "").lower(), (artist or "").lower()),
        )
        return [dict(r) for r in rows]

    def artists(self):
        rows = self._query(
            "SELECT IFNULL(NULLIF(albumartist,''), artist) AS name, COUNT(*) AS tracks "
            "FROM tracks WHERE IFNULL(name,'') <> '' GROUP BY LOWER(name) ORDER BY name"
        )
        return [dict(r) for r in rows]

    def top_tracks(self, limit=50):
        return [dict(r) for r in self._query(
            "SELECT * FROM tracks WHERE play_count > 0 "
            "ORDER BY play_count DESC, last_played DESC LIMIT ?", (limit,))]

    def top_artists(self, limit=25):
        return [dict(r) for r in self._query(
            "SELECT IFNULL(NULLIF(albumartist,''), artist) AS name, "
            "SUM(play_count) AS plays, COUNT(*) AS tracks FROM tracks "
            "WHERE IFNULL(name,'') <> '' AND play_count > 0 "
            "GROUP BY LOWER(name) ORDER BY plays DESC LIMIT ?", (limit,))]

    def recently_played(self, limit=50):
        return [dict(r) for r in self._query(
            "SELECT * FROM tracks WHERE last_played > 0 "
            "ORDER BY last_played DESC LIMIT ?", (limit,))]

    def recently_added(self, limit=50):
        return [dict(r) for r in self._query(
            "SELECT * FROM tracks ORDER BY added DESC LIMIT ?", (limit,))]

    def favorites(self):
        return [dict(r) for r in self._query(
            "SELECT * FROM tracks WHERE favorite = 1 ORDER BY artist, album, track_no")]

    def never_played(self, limit=100):
        return [dict(r) for r in self._query(
            "SELECT * FROM tracks WHERE play_count = 0 ORDER BY added DESC LIMIT ?", (limit,))]

    def listening_clock(self, days=365):
        since = time.time() - days * 86400
        counts = [0] * 24
        for row in self._query("SELECT played FROM history WHERE played >= ?", (since,)):
            counts[time.localtime(row["played"]).tm_hour] += 1
        return counts

    def stats(self):
        rows = self._query(
            "SELECT COUNT(*) AS tracks, IFNULL(SUM(duration),0) AS length, "
            "IFNULL(SUM(play_count),0) AS plays, "
            "COUNT(DISTINCT LOWER(IFNULL(album,''))) AS albums, "
            "COUNT(DISTINCT LOWER(IFNULL(NULLIF(albumartist,''), artist))) AS artists "
            "FROM tracks")
        base = dict(rows[0]) if rows else {}
        played = self._query(
            "SELECT IFNULL(SUM(duration * play_count),0) AS listened FROM tracks")
        base["listened"] = played[0]["listened"] if played else 0
        return base

    def wipe(self):
        with self._lock:
            for table in ("tracks", "analysis", "history", "playlist_items", "playlists"):
                self._db.execute(f"DELETE FROM {table}")
            self._db.commit()
            try:
                self._db.execute("VACUUM")
            except Exception:
                pass

    def create_playlist(self, name, kind="static", query=""):
        cur = self._exec(
            "INSERT INTO playlists (name, kind, query, created) VALUES (?, ?, ?, ?)",
            (name, kind, query, time.time()))
        return cur.lastrowid

    def delete_playlist(self, playlist_id):
        self._exec("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,))
        self._exec("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def playlists(self):
        return [dict(r) for r in self._query("SELECT * FROM playlists ORDER BY name")]

    def set_playlist_items(self, playlist_id, paths):
        with self._lock:
            self._db.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,))
            self._db.executemany(
                "INSERT INTO playlist_items (playlist_id, position, path) VALUES (?, ?, ?)",
                [(playlist_id, i, p) for i, p in enumerate(paths)])
            self._db.commit()

    def playlist_tracks(self, playlist_id):
        rows = self._query("SELECT * FROM playlists WHERE id = ?", (playlist_id,))
        if not rows:
            return []
        row = dict(rows[0])
        if row.get("kind") == "smart":
            return self.search(row.get("query") or "")
        items = self._query(
            "SELECT i.path AS path, t.* FROM playlist_items i "
            "LEFT JOIN tracks t ON t.path = i.path "
            "WHERE i.playlist_id = ? ORDER BY i.position", (playlist_id,))
        return [dict(r) for r in items]
