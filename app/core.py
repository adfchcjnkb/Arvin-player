
import os
import base64
import logging
from typing import Dict, Any

log = logging.getLogger("parch_mp.core")

try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TCON, TDRC, TRCK
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False
    log.warning("mutagen not installed; metadata extraction disabled. "
                "Install with: pip install mutagen")

EDITABLE_FIELDS = ("title", "artist", "album", "genre", "year", "track_number")


class ThemeManager:
    
    DARK = {
        'name': 'dark',
        'bg_primary': '#0A0A0F',
        'bg_secondary': '#1A1A2E',
        'bg_card': '#16213E',
        'bg_surface': '#16213E',
        'bg_surface_light': '#1F2B47',
        'accent_primary': '#1DB954',
        'accent_secondary': '#FF6B6B',
        'accent_tertiary': '#4ECDC4',
        'accent_gold': '#FFD93D',
        'accent_purple': '#6C5CE7',
        'text_primary': '#FFFFFF',
        'text_secondary': '#B0B0B0',
        'text_disabled': '#666666',
        'border': '#333333',
        'shadow': 'rgba(0, 0, 0, 200)',
        'tree_alt_bg': '#16213E',
        'button_bg': '#16213E',
        'input_bg': '#16213E',
        'input_border': '#333333',
        'input_focus': '#1DB954',
        'slider_bg': '#333333',
        'playing_bg': '#1a3a2a',
        'playing_border': '#1DB954',
    }
    
    LIGHT = {
        'name': 'light',
        'bg_primary': '#F5F5F5',
        'bg_secondary': '#FFFFFF',
        'bg_card': '#FFFFFF',
        'bg_surface': '#F0F0F0',
        'bg_surface_light': '#E8E8E8',
        'accent_primary': '#1DB954',
        'accent_secondary': '#E74C3C',
        'accent_tertiary': '#3498DB',
        'accent_gold': '#F39C12',
        'accent_purple': '#8E44AD',
        'text_primary': '#2C3E50',
        'text_secondary': '#7F8C8D',
        'text_disabled': '#BDC3C7',
        'border': '#D5D8DC',
        'shadow': 'rgba(0, 0, 0, 100)',
        'tree_alt_bg': '#F8F9FA',
        'button_bg': '#E8E8E8',
        'input_bg': '#FFFFFF',
        'input_border': '#D5D8DC',
        'input_focus': '#1DB954',
        'slider_bg': '#D5D8DC',
        'playing_bg': '#e8f5e9',
        'playing_border': '#1DB954',
    }
    
    @classmethod
    def get_theme(cls, theme_name: str = 'dark') -> dict:
        return cls.DARK if theme_name == 'dark' else cls.LIGHT


class MetadataManager:
    
    def get_metadata(self, filepath: str) -> Dict[str, Any]:
        filename = os.path.basename(filepath)
        metadata = {
            'title': filename,
            'artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'genre': '',
            'year': '',
            'track_number': 0,
            'duration': 0,
            'bitrate': 0,
            'sample_rate': 0,
            'channels': 2,
            'cover_art': None,
            'cover_path': '',
        }
        
        if not MUTAGEN_OK:
            return metadata
        
        try:
            audio = MutagenFile(filepath)
            if audio is None:
                return metadata
            
            if hasattr(audio, 'info') and audio.info:
                info = audio.info
                metadata['duration'] = int(info.length) if hasattr(info, 'length') else 0
                metadata['bitrate'] = (getattr(info, 'bitrate', 0) or 0) // 1000
                metadata['sample_rate'] = getattr(info, 'sample_rate', 0) or 0
                metadata['channels'] = getattr(info, 'channels', 2) or 2
            
            if getattr(audio, 'tags', None):
                self._read_tags(audio, metadata)

            if not metadata['cover_art']:
                folder = os.path.dirname(filepath)
                for name in ['cover.jpg', 'folder.jpg', 'Front.jpg', 'AlbumArt.jpg', 'cover.png']:
                    candidate = os.path.join(folder, name)
                    if os.path.exists(candidate):
                        metadata['cover_path'] = candidate
                        break

        except Exception:
            log.debug("Metadata read failed for %s", filepath, exc_info=True)

        return metadata

    @staticmethod
    def _assign(metadata, key, raw):
        val = ("" if raw is None else str(raw)).strip()
        if not val:
            return
        if key == "track_number":
            try:
                metadata[key] = int(val.split("/")[0])
            except (ValueError, TypeError):
                pass
        elif key == "year":
            metadata[key] = val[:4]
        else:
            metadata[key] = val

    def _read_tags(self, audio, metadata):
        tags = audio.tags

        def first(v):
            return v[0] if isinstance(v, (list, tuple)) and v else v

        for fk, mk in (("TIT2", "title"), ("TPE1", "artist"), ("TALB", "album"),
                       ("TCON", "genre"), ("TDRC", "year"), ("TRCK", "track_number")):
            if fk in tags:
                self._assign(metadata, mk, tags[fk])
        for key in tags.keys():
            if key.startswith("APIC"):
                metadata["cover_art"] = tags[key].data
                break

        for vk, mk in (("title", "title"), ("artist", "artist"), ("album", "album"),
                       ("genre", "genre"), ("date", "year"), ("tracknumber", "track_number")):
            if vk in tags:
                self._assign(metadata, mk, first(tags[vk]))
        if not metadata["cover_art"] and "metadata_block_picture" in tags:
            for b64 in tags["metadata_block_picture"]:
                try:
                    metadata["cover_art"] = Picture(base64.b64decode(b64)).data
                    break
                except Exception:
                    pass
        if not metadata["cover_art"] and getattr(audio, "pictures", None):
            metadata["cover_art"] = audio.pictures[0].data

        for mk4, mk in (("\xa9nam", "title"), ("\xa9ART", "artist"), ("\xa9alb", "album"),
                        ("\xa9gen", "genre"), ("\xa9day", "year")):
            if mk4 in tags:
                self._assign(metadata, mk, first(tags[mk4]))
        if "trkn" in tags:
            try:
                metadata["track_number"] = int(tags["trkn"][0][0])
            except (ValueError, TypeError, IndexError):
                pass
        if not metadata["cover_art"] and "covr" in tags:
            try:
                metadata["cover_art"] = bytes(tags["covr"][0])
            except (ValueError, TypeError, IndexError):
                pass

        for ak, mk in (("Title", "title"), ("Artist", "artist"), ("Album", "album"),
                       ("Genre", "genre"), ("Year", "year"), ("Track", "track_number")):
            if ak in tags:
                self._assign(metadata, mk, str(tags[ak]))

    def write_metadata(self, filepath, fields, cover_action="keep",
                       cover_bytes=None, cover_mime=None):
        if not MUTAGEN_OK:
            return False, "mutagen-missing"
        ext = os.path.splitext(filepath)[1].lower()
        args = (filepath, fields, cover_action, cover_bytes, cover_mime)
        try:
            if ext == ".mp3":
                self._write_id3(*args, container="mp3")
            elif ext in (".wav", ".wave"):
                self._write_id3(*args, container="wav")
            elif ext in (".aif", ".aiff", ".aifc"):
                self._write_id3(*args, container="aiff")
            elif ext == ".dsf":
                self._write_id3(*args, container="dsf")
            elif ext == ".flac":
                self._write_flac(*args)
            elif ext in (".m4a", ".m4b", ".mp4", ".aac", ".alac"):
                self._write_mp4(*args)
            elif ext in (".ogg", ".oga"):
                self._write_ogg(*args, kind="vorbis")
            elif ext == ".opus":
                self._write_ogg(*args, kind="opus")
            elif ext == ".wma":
                self._write_asf(*args)
            elif ext in (".ape", ".mpc", ".mp+", ".wv", ".tta"):
                self._write_apev2(*args)
            else:
                return False, "unsupported-format"
            return True, None
        except Exception as exc:
            log.warning("Metadata write failed for %s", filepath, exc_info=True)
            return False, str(exc)

    @staticmethod
    def _set_vcomment(audio, fields):
        vmap = {"title": "TITLE", "artist": "ARTIST", "album": "ALBUM",
                "genre": "GENRE", "year": "DATE", "track_number": "TRACKNUMBER"}
        for fkey, vkey in vmap.items():
            val = fields.get(fkey)
            if val in (None, "", 0):
                audio.pop(vkey, None)
            else:
                audio[vkey] = str(val)

    @staticmethod
    def _jpeg_size(data):
        try:
            i, n = 2, len(data)
            while i + 9 < n:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return ((data[i + 7] << 8) | data[i + 8],
                            (data[i + 5] << 8) | data[i + 6])
                i += 2 + ((data[i + 2] << 8) | data[i + 3])
        except Exception:
            pass
        return 0, 0

    def _make_picture(self, cover_bytes, cover_mime):
        pic = Picture()
        pic.type = 3
        pic.mime = cover_mime or "image/jpeg"
        pic.desc = ""
        pic.data = cover_bytes
        w, h = self._jpeg_size(cover_bytes)
        if w and h:
            pic.width, pic.height, pic.depth = w, h, 24
        return pic

    def _write_id3(self, filepath, fields, cover_action, cover_bytes, cover_mime, container="mp3"):
        if container == "wav":
            from mutagen.wave import WAVE
            audio = WAVE(filepath)
        elif container == "aiff":
            from mutagen.aiff import AIFF
            audio = AIFF(filepath)
        elif container == "dsf":
            from mutagen.dsf import DSF
            audio = DSF(filepath)
        else:
            audio = MP3(filepath)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        frames = {"title": TIT2, "artist": TPE1, "album": TALB,
                  "genre": TCON, "year": TDRC, "track_number": TRCK}
        keymap = {"title": "TIT2", "artist": "TPE1", "album": "TALB",
                  "genre": "TCON", "year": "TDRC", "track_number": "TRCK"}
        for fkey, frame_cls in frames.items():
            tags.delall(keymap[fkey])
            val = fields.get(fkey)
            if val not in (None, "", 0):
                tags.add(frame_cls(encoding=3, text=[str(val)]))
        if cover_action == "remove":
            tags.delall("APIC")
        elif cover_action == "replace" and cover_bytes:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=cover_mime or "image/jpeg",
                          type=3, desc="", data=cover_bytes))
        try:
            tags.update_to_v23()
        except Exception:
            pass
        try:
            audio.save(v2_version=3)
        except TypeError:
            audio.save()

    def _write_flac(self, filepath, fields, cover_action, cover_bytes, cover_mime):
        audio = FLAC(filepath)
        self._set_vcomment(audio, fields)
        if cover_action == "remove":
            audio.clear_pictures()
        elif cover_action == "replace" and cover_bytes:
            audio.clear_pictures()
            audio.add_picture(self._make_picture(cover_bytes, cover_mime))
        audio.save()

    def _write_mp4(self, filepath, fields, cover_action, cover_bytes, cover_mime):
        audio = MP4(filepath)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        kmap = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb",
                "genre": "\xa9gen", "year": "\xa9day"}
        for fkey, key in kmap.items():
            val = fields.get(fkey)
            if val in (None, "", 0):
                tags.pop(key, None)
            else:
                tags[key] = [str(val)]
        trk = fields.get("track_number")
        if trk in (None, "", 0):
            tags.pop("trkn", None)
        else:
            try:
                tags["trkn"] = [(int(trk), 0)]
            except (ValueError, TypeError):
                pass
        if cover_action == "remove":
            tags.pop("covr", None)
        elif cover_action == "replace" and cover_bytes:
            fmt = MP4Cover.FORMAT_PNG if (cover_mime or "").endswith("png") else MP4Cover.FORMAT_JPEG
            tags["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
        audio.save()

    def _write_ogg(self, filepath, fields, cover_action, cover_bytes, cover_mime, kind="vorbis"):
        audio = OggVorbis(filepath) if kind == "vorbis" else OggOpus(filepath)
        self._set_vcomment(audio, fields)
        if cover_action == "remove":
            audio.pop("metadata_block_picture", None)
            audio.pop("coverart", None)
        elif cover_action == "replace" and cover_bytes:
            import base64
            pic = self._make_picture(cover_bytes, cover_mime)
            audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
        audio.save()

    def _write_asf(self, filepath, fields, cover_action, cover_bytes, cover_mime):
        from mutagen.asf import ASF, ASFByteArrayAttribute
        import struct
        audio = ASF(filepath)
        kmap = {"title": "Title", "artist": "Author", "album": "WM/AlbumTitle",
                "genre": "WM/Genre", "year": "WM/Year", "track_number": "WM/TrackNumber"}
        for fkey, key in kmap.items():
            val = fields.get(fkey)
            if val in (None, "", 0):
                audio.tags.pop(key, None)
            else:
                audio.tags[key] = [str(val)]
        if cover_action == "remove":
            audio.tags.pop("WM/Picture", None)
        elif cover_action == "replace" and cover_bytes:
            mime = (cover_mime or "image/jpeg").encode("utf-16-le") + b"\x00\x00"
            desc = b"\x00\x00"
            blob = struct.pack("<bi", 3, len(cover_bytes)) + mime + desc + cover_bytes
            audio.tags["WM/Picture"] = [ASFByteArrayAttribute(blob)]
        audio.save()

    def _write_apev2(self, filepath, fields, cover_action, cover_bytes, cover_mime):
        from mutagen.apev2 import APEv2, APENoHeaderError, APEValue, BINARY
        try:
            audio = APEv2(filepath)
        except APENoHeaderError:
            audio = APEv2()
        amap = {"title": "Title", "artist": "Artist", "album": "Album",
                "genre": "Genre", "year": "Year", "track_number": "Track"}
        for fkey, key in amap.items():
            val = fields.get(fkey)
            if val in (None, "", 0):
                audio.pop(key, None)
            else:
                audio[key] = str(val)
        if cover_action == "remove":
            for key in [k for k in audio if k.lower().startswith("cover art")]:
                del audio[key]
        elif cover_action == "replace" and cover_bytes:
            ext = b"png" if (cover_mime or "").endswith("png") else b"jpg"
            audio["Cover Art (Front)"] = APEValue(b"cover." + ext + b"\x00" + cover_bytes, BINARY)
        audio.save(filepath)