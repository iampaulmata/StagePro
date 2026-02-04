# StagePro 🎸

**StagePro** is a **Linux-first, cross-platform stage lyrics and chart viewer** designed for live performance.  
It renders **ChordPro** songs in a clean, readable, stage-friendly layout and supports **hands-free control via Bluetooth or USB foot pedals**.

StagePro is built for musicians who want:
- Zero distractions on stage
- Reliable setlists
- Fast navigation
- Clear, customizable visuals

StagePro is currently in **beta**, but is already gig-ready.

---

## 🌍 Cross-Platform Vision

StagePro is designed from the start to be **cross-platform**.

### Current Status
- ✅ **Linux** (primary platform, AppImage distribution)
- 🧪 **Windows & macOS** (planned and actively being prepared)
- 🚧 **Android** (coming soon)

The long-term goal is for StagePro to run on:
- Laptops
- Mini PCs
- Tablets
- Dedicated stage devices

…with the same playlists, songs, and themes across all platforms.

---

## ✨ Core Features

### 🎵 ChordPro Song Support
- Supports `.cho`, `.chopro`, and `.pro` files and `.txt` files that have ChordPro tags
- Parses:
  - Lyrics and chords
  - Sections (`{verse}`, `{chorus}`, `{bridge}`, `{comment}`, etc.)
- Displays long songs cleanly in a scrollable, paged format optimized for stage use

---

### 📋 Playlists & Setlists
- Create and manage playlists (setlists) inside StagePro
- Playlists reference song filenames (non-destructive)
- Reorder songs for live performance
- Quickly switch between playlists during rehearsal or shows

**Robust handling of missing files**
- If a song file is deleted or moved outside StagePro:
  - The app does **not crash**
  - The missing entry is detected
  - The user is warned
  - The stale playlist entry is automatically removed

---

### 🛠️ Maintenance Mode vs On-Stage Mode

StagePro has two distinct modes:

#### Maintenance Mode
Used for preparation and setup:
- Browse library and playlists
- Preview songs
- Edit order
- Verify formatting and themes

Selecting a song in Maintenance Mode:
- Updates the preview **and**
- Sets the song as the **active on-stage selection**

This guarantees that when you switch to On-Stage Mode, the correct song is shown.

#### On-Stage Mode
Designed for live performance:
- Clean, distraction-free display
- Optimized contrast and spacing
- Controlled entirely by keyboard or foot pedal
- No accidental song changes

You can switch modes instantly.

---

### 🦶 Foot Pedal & Keyboard Control

StagePro works with any foot pedal that sends standard keyboard events.

#### Supported Controls
- **Page Up / Page Down** — Scroll lyrics
- **Left / Right Arrow** — Navigate between songs
- **Ctrl + F** (or configured pedal combo) — Toggle Maintenance / On-Stage mode

Most Bluetooth and USB pedals work out of the box once paired with the OS.

---

### 🎨 Theme System

StagePro supports **fully customizable themes** that control how songs are rendered.

Themes allow you to define colors and styles for:
- Verse
- Chorus
- Bridge
- Comment
- Titles and metadata

#### Theme Highlights
- Themes are defined as **shareable files**
- Designed for high-contrast stage visibility
- Multiple themes can coexist
- Future releases will expand theme options and presets

Themes are loaded automatically at startup.

---

### 📁 Flexible Songs Folder Handling

StagePro looks for songs in the following order:

1. A `songs/` folder **next to the executable or AppImage**
2. The user data directory:
