"""
Arvin Player - Core Classes (ThemeManager, MetadataManager)
"""

import os
from typing import Dict, Any

# Try to import mutagen components
try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False
    print("Warning: mutagen not installed. Install with: pip install mutagen")


# ========== Theme Manager ==========
class ThemeManager:
    """Manages light and dark themes"""
    
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


# ========== Metadata Manager ==========
class MetadataManager:
    """Robust metadata extraction using mutagen"""
    
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
            
            if hasattr(audio, 'tags') and audio.tags:
                tags = audio.tags
                
                # ID3 tags
                tag_map = {
                    'TIT2': 'title', 'TPE1': 'artist', 'TALB': 'album',
                    'TCON': 'genre', 'TDRC': 'year', 'TRCK': 'track_number'
                }
                for tag_key, meta_key in tag_map.items():
                    if tag_key in tags:
                        val = str(tags[tag_key])
                        if meta_key == 'track_number':
                            try:
                                metadata[meta_key] = int(val.split('/')[0])
                            except:
                                pass
                        elif meta_key == 'year':
                            metadata[meta_key] = val[:4] if val else ''
                        else:
                            metadata[meta_key] = val
                
                # Cover art
                for key in tags.keys():
                    if key.startswith('APIC'):
                        metadata['cover_art'] = tags[key].data
                        break
                
                # Vorbis/FLAC
                vorbis_map = {
                    'title': 'title', 'artist': 'artist', 'album': 'album',
                    'genre': 'genre', 'date': 'year', 'tracknumber': 'track_number'
                }
                for tag_key, meta_key in vorbis_map.items():
                    if tag_key in tags and not metadata.get(meta_key):
                        val = tags[tag_key][0] if isinstance(tags[tag_key], list) else str(tags[tag_key])
                        if meta_key == 'track_number':
                            try:
                                metadata[meta_key] = int(val)
                            except:
                                pass
                        else:
                            metadata[meta_key] = str(val)
                
                # FLAC pictures
                if hasattr(audio, 'pictures') and audio.pictures:
                    metadata['cover_art'] = audio.pictures[0].data
                
                # MP4 covr
                if 'covr' in tags:
                    metadata['cover_art'] = bytes(tags['covr'][0])
            
            # Check for folder covers
            if not metadata['cover_art']:
                folder = os.path.dirname(filepath)
                for name in ['cover.jpg', 'folder.jpg', 'Front.jpg', 'AlbumArt.jpg', 'cover.png']:
                    candidate = os.path.join(folder, name)
                    if os.path.exists(candidate):
                        metadata['cover_path'] = candidate
                        break
        
        except Exception:
            pass
        
        return metadata