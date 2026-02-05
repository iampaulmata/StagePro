# 🎤 StagePro

[StagePro Logo](assets/stagepro.png)

**StagePro** is a cross-platform, musician-focused lyrics and chord prompter designed for **live performance**.  
It is built around **ChordPro** song files, supports **foot-switch control**, and cleanly separates **on-stage use** from **setlist and library management**.

StagePro is designed to run reliably on laptops, mini PCs, and stage wedges — even **offline at a gig**.

---

## 📸 Screenshots

[StagePro Performance View](assets/stagepro_performance_mode.png)
[StagePro Maintenance View](assets/stagepro_maintenance_mode.png)
[StagePro Preferences Window](assets/sstagepro_preferences.png)


---

## ✨ Key Features

### 🎶 Performance-First Design
- Dedicated **On-Stage Mode** (fullscreen, distraction-free)
- **Maintenance Mode** for managing songs, playlists, and metadata
- Optimized for **portrait or landscape** stage displays
- Works fully **offline**

### 📄 ChordPro Native
- Uses standard `.cho` / ChordPro song files
- Automatic parsing of lyrics, chords, sections, and directives
- Graceful handling of minimally formatted or malformed files

### 🎛️ Configurable Display
- Customizable **font family**
- Adjustable **font size**
- Theme-based color system (JSON theme files)
- Screen **rotation support** (90° / 180° / 270°)
- Portrait & landscape orientation support

### 🎨 Theme System
- Theme files stored as JSON
- Per-element color control (lyrics, chords, chorus, headers, etc.)
- User-selectable themes via **Preferences UI**
- No restart required — updates apply immediately

### 📚 Library & Playlist Management
- Central song library
- Multiple playlists (setlists)
- Add/remove/reorder songs without duplicating files
- Safe handling of missing or moved files

### 🦶 Footswitch & Keyboard Control
- Page navigation
- Song navigation
- Mode switching (Maintenance ↔ On-Stage)
- Designed for USB foot pedals and keyboard shortcuts

### 🧠 Smart Metadata
- Optional **MusicBrainz** integration for metadata autofill
- Non-destructive updates to song files

---

## 🛠️ Preferences UI

StagePro includes a built-in **Preferences** window so you never have to edit JSON by hand.

From **Tools → Preferences…**, you can configure:

- Font family
- Font size
- Active theme
- Orientation (portrait / landscape)
- Rotation (90° / 180° / 270°)

Changes apply **immediately**.

---

## 💻 Supported Platforms

StagePro is built and tested on:

- 🐧 **Linux** (AppImage)
- 🪟 **Windows**
- 🍎 **macOS**

> 📱 **Android support is planned** (touch-friendly on-stage mode).

---

## 📦 Installation

### Linux (Recommended)
Download the `.AppImage`, make it executable, and run:
```bash
chmod +x StagePro-*.AppImage
./StagePro-*.AppImage
