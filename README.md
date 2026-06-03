# Arvin Player: Professional Music Player Platform

<p align="center">
  <img src="https://raw.githubusercontent.com/adfchcjnkb/Arvin-player/refs/heads/main/Dark.png" width="90%" alt="Arvin Player Dark Theme">
</p>

Arvin Player is an advanced professional music player platform with real-time audio visualization, vinyl animation, and comprehensive metadata support. This project serves as a high-fidelity alternative to traditional media players, offering a dynamic environment where users can interact with their music library in real-time. The platform is engineered to meet the needs of audiophiles, music enthusiasts, and professional users by providing accurate audio playback and stunning visual feedback.

---

<p align="center">
  <img src="https://img.shields.io/badge/Environment-Production-00d4ff?style=for-the-badge" alt="Production">
  <img src="https://img.shields.io/badge/Architecture-Modular_Python-ff2a6d?style=for-the-badge" alt="Architecture">
  <img src="https://img.shields.io/badge/Core_Engine-PyQt6-yellow?style=for-the-badge" alt="PyQt6">
  <img src="https://img.shields.io/badge/UI_Style-Modern_Dark/Light-06d6a0?style=for-the-badge" alt="UI">
  <img src="https://img.shields.io/badge/Backend-Local_Player-9b5de5?style=for-the-badge" alt="Backend">
</p>

---

## 📖 Comprehensive Project Documentation

The Arvin Player project is built on the principle of "Visual Excellence with Audio Fidelity." In the world of music playback, the visual experience is as important as the audio quality. This platform recreates a professional listening environment with a rotating vinyl disc animation, ensuring that every playback session feels premium. The user interface is designed using modern PyQt6 standards, where every element possesses rounded borders and interactive feedback loops.

### 🛠 Development Status & Future Roadmap

We follow a rigorous development cycle to ensure the platform evolves with modern standards.

1.  **Modular Architecture (Completed):**
    The application is split into 5 modular files for easy maintenance and development.

2.  **Bilingual Support (Planned):**
    Full support for both Persian and English languages with intelligent language detection.

3.  **Cross-Platform Performance (Completed):**
    The code is optimized for Windows, Linux, and macOS, ensuring consistent behavior across all platforms.

---

## 🔍 In-Depth Feature Analysis

### 1. Primary Interface and Playlist System
The main dashboard displays your music library in an organized tree view with columns for track number, title (with cover art), duration, and action menu.

<p align="center">
  <img src="https://raw.githubusercontent.com/adfchcjnkb/Arvin-player/refs/heads/main/Dark.png" width="90%" alt="Arvin Player Dark Theme">
</p>

### 2. Real-Time Audio Visualizer
One of the most significant technical components of this project is the real-time equalizer visualization with 100 responsive bars.

<p align="center">
  <img src="https://raw.githubusercontent.com/adfchcjnkb/Arvin-player/refs/heads/main/Light.png" width="60%" alt="Audio Visualizer and Light Theme">
</p>

### 3. Rotating Vinyl Disc Animation
The platform features a realistic rotating vinyl record that spins during playback, creating an authentic listening experience.

<p align="center">
  <img src="https://raw.githubusercontent.com/adfchcjnkb/Arvin-player/refs/heads/main/icon.ico" width="30%" alt="Vinyl Animation Icon">
</p>

### 4. Comprehensive Metadata Support
The application extracts and displays detailed metadata including title, artist, album, genre, year, bitrate, sample rate, and cover art.

### 5. Dual Theme System
Full support for both Dark and Light themes with smooth transitions.

| Theme | Primary | Secondary | Accent |
|-------|---------|-----------|--------|
| **Dark** | #0A0A0F | #1A1A2E | #1DB954 |
| **Light** | #F5F5F5 | #FFFFFF | #1DB954 |

---

## ⚙️ Modular Architecture

### **Professional Modular Structure**

```
📁 arvin_player/
├── 📄 main.py              # Entry point, QApplication setup
├── 📄 utils.py             # Constants and helper functions
├── 📄 core.py              # ThemeManager & MetadataManager
├── 📄 widgets.py           # VinylDisc, EqualizerVisualizer, TreeItemDelegate
├── 📄 player.py            # Main ArvinPlayer class (UI + Logic)
└── 📄 requirements.txt     # Python dependencies
```

### **Module Responsibilities:**

| Module | Responsibility | Lines |
|--------|---------------|-------|
| **main.py** | Application entry, font loading, icon setup | ~50 |
| **utils.py** | Resource paths, time formatting, constants | ~30 |
| **core.py** | Theme management, metadata extraction | ~200 |
| **widgets.py** | Custom UI components (vinyl, visualizer) | ~350 |
| **player.py** | Main player logic, UI layout, event handling | ~700 |

---

## 🎵 Key Features

### **Audio Playback**
- ✅ Support for MP3, FLAC, WAV, OGG, M4A, WMA
- ✅ Play/Pause/Stop/Previous/Next controls
- ✅ Volume control with percentage display
- ✅ Seek slider with real-time position updates
- ✅ Repeat modes (Off / One / All)
- ✅ Shuffle mode

### **Playlist Management**
- ✅ Add single files or entire folders
- ✅ Save/Load playlists (JSON format)
- ✅ Search/filter tracks in real-time
- ✅ Right-click context menu
- ✅ Delete tracks individually or multiple
- ✅ Track count display

### **Visual Features**
- ✅ Rotating vinyl disc with cover art
- ✅ Real-time equalizer with 100 bars
- ✅ Dark/Light theme toggle (Ctrl+T)
- ✅ Fullscreen mode (F11)
- ✅ System tray integration

### **Metadata Display**
- ✅ Title, Artist, Album, Genre
- ✅ Track duration, bitrate, sample rate
- ✅ Album cover art (embedded or folder)
- ✅ Current time and total time

### **Keyboard Shortcuts**

| Shortcut | Action |
|----------|--------|
| **Space** | Play/Pause |
| **Left/Right** | Seek -5/+5 seconds |
| **F11** | Fullscreen mode |
| **Ctrl+T** | Toggle theme |
| **Delete** | Remove selected track |
| **Ctrl+L** | Toggle playlist panel |

---

## 💻 Technical Stack

### **Frontend Technologies**
- **PyQt6** - Professional GUI framework
- **Qt6 Multimedia** - Audio playback engine
- **Qt6 Widgets** - Custom UI components
- **QSS** - Dynamic theming system

### **Backend Technologies**
- **Python 3.11+** - Core programming language
- **Mutagen** - Metadata extraction
- **JSON** - Playlist storage format

### **Visual Components**
- **Custom Paint Events** - Vinyl disc rendering
- **Real-time Animations** - Property animations
- **Audio Visualizer** - Simulated audio spectrum

---

## 🚀 Quick Start Guide

### **Option 1: Direct Python Execution**
```bash
# Clone the repository
git clone https://github.com/adfchcjnkb/Arvin-player.git

# Navigate to project
cd Arvin-player

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### **Option 2: Standalone Executable (PyInstaller)**
```bash
# Install PyInstaller
pip install pyinstaller

# Create single executable
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --add-data "Dark.png;." --add-data "Light.png;." --name "ArvinPlayer" main.py
```

### **System Requirements:**
- **OS:** Windows 10/11, Linux, macOS
- **Python:** 3.11 or higher
- **RAM:** 512MB minimum
- **Storage:** 50MB for application

---

## 📦 Dependencies

```txt
PyQt6>=6.5.0
PyQt6-Qt6>=6.5.0
PyQt6-multimedia>=6.5.0
mutagen>=1.46.0
```

### **Installation Command:**
```bash
pip install -r requirements.txt
```

---

## 📊 Performance Benchmarks

| Metric | Value |
|--------|-------|
| **Startup Time** | < 2 seconds |
| **Memory Usage** | < 150 MB |
| **CPU Usage (idle)** | < 1% |
| **CPU Usage (playing)** | < 5% |
| **File Loading** | < 100ms |

---

## 🔧 Development & Contribution

### **Setting Up Development Environment:**
```bash
# 1. Clone repository
git clone https://github.com/adfchcjnkb/Arvin-player.git

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run in development mode
python main.py
```

### **Project Structure for Development:**
```
📁 arvin_player/
├── 📄 main.py          # Entry point
├── 📄 utils.py         # Utilities
├── 📄 core.py          # Core classes
├── 📄 widgets.py       # Custom widgets
├── 📄 player.py        # Main player
├── 📄 icon.ico         # Application icon
├── 📄 Dark.png         # Dark theme preview
├── 📄 Light.png        # Light theme preview
└── 📄 requirements.txt # Dependencies
```

### **Contributing Guidelines:**
1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to branch
5. Open a Pull Request

### **Code Style:**
- Follow PEP 8 guidelines
- Use type hints where possible
- Document complex functions
- Test before committing

---

## 🐛 Known Issues & Solutions

| Issue | Solution |
|-------|----------|
| PyQt6 Multimedia not found | `pip install PyQt6-multimedia` |
| Mutagen import error | `pip install mutagen` |
| No audio output | Check system volume and audio device |
| Cover art not showing | Ensure file has embedded art or folder.jpg exists |

---

## 📞 Support & Contact

For technical support, feature requests, or collaboration inquiries:

- **Email:** arvinkheradmand28@gmail.com
- **GitHub:** [@adfchcjnkb](https://github.com/adfchcjnkb)

---

## 📄 License & Copyright

©2026 Arvin Player Project Group. All rights reserved.

- **Code License:** MIT License
- **Assets:** All rights reserved
- **Documentation:** CC BY-SA 4.0

---

## 🙏 Acknowledgments

- **PyQt6 Team** - For the excellent GUI framework
- **Mutagen Team** - For metadata extraction library
- **Qt Company** - For the underlying Qt framework

---

<p align="center">
  <img src="https://img.shields.io/badge/🚀-Ready_for_Production-success" alt="Production Ready">
  <img src="https://img.shields.io/badge/⚡-Ultra_Fast-blue" alt="Fast">
  <img src="https://img.shields.io/badge/🎵-High_Fidelity_Audio-green" alt="Audio">
  <img src="https://img.shields.io/badge/🎨-Modern_UI-purple" alt="Modern UI">
</p>

<p align="center">
  Made with ❤️ by Arvin Kheradmand
</p>
