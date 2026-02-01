# StagePro 🎸

StagePro is a **Linux-first, cross-platform stage lyrics viewer** designed for live performance.  
It displays ChordPro songs in a clean, readable format and supports **hands-free navigation via Bluetooth foot pedals**, allowing musicians to stay focused on the performance instead of a screen.

StagePro is currently in **beta** and actively evolving.

---

## ✨ Features

- 🎵 **ChordPro support**
  - Displays lyrics with chords and structured sections
- 🦶 **Bluetooth foot-pedal navigation**
  - Page Up / Page Down
  - Left / Right arrow keys
- 📁 **Portable songs folder**
  - Drop a `songs/` folder next to the AppImage
  - Falls back to a per-user data directory automatically
- 🎨 **Theming support**
  - Custom colors and styles for sections like chorus, bridge, etc.
- 🐧 **Linux AppImage distribution**
  - No installation required
  - Works across modern Linux distributions

---

## 📦 Download & Run (Linux)

Download the latest AppImage from the **GitHub Releases** page.

```bash
chmod +x StagePro-0.1.0-beta-x86_64.AppImage
./StagePro-0.1.0-beta-x86_64.AppImage
```

---

## 📂 Songs Folder Layout

StagePro searches for songs in the following order:

1. A `songs/` folder **next to the AppImage or executable**
2. The user data directory:
   ```
   ~/.local/share/stagepro/songs
   ```

Songs should be in **ChordPro format** (`.cho`, `.chopro`, or `.pro`).

Example directory structure:

```
StagePro-0.1.0-beta-x86_64.AppImage
songs/
 ├── song1.cho
 ├── song2.cho
 └── setlists/
     └── opener.cho
```

---

## 🦶 Foot Pedal Support

StagePro works with Bluetooth foot pedals that send standard keyboard events.

Supported keys:
- **Page Up / Page Down**
- **Left / Right arrows**

Most pedals work out of the box once paired with your operating system — no additional configuration is required.

---

## 🎨 Themes

StagePro supports theming to control how different song sections are displayed (e.g., chorus, verse, bridge).

Themes are stored in the `themes/` directory and can be customized or extended.  
More documentation and shareable themes are planned for future releases.

---

## ⚠️ Beta Status

This is an **early beta release**.

- UI and theming may change
- Configuration options are still evolving
- Some edge cases may exist

Bug reports and feature requests are welcome via GitHub Issues.

---

## 🛠️ Development

StagePro is built with:

- Python
- PySide6 (Qt)
- ChordPro parsing
- Linux-first packaging via AppImage

The project prioritizes **stage usability**, **portability**, and **low-friction setup** for musicians.

---

## 📜 License

See [LICENSE.md](LICENSE.md).

---

Rock on 🤘