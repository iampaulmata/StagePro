# StagePro

**StagePro** is a Linux-first, cross-platform Python application for displaying **ChordPro lyrics on stage**, designed for hands-free control using a **Bluetooth foot pedal** (PgUp/PgDn or Left/Right).

It is built with **PySide6 (Qt)** and focuses on **accurate pagination, readable chord rendering, and reliable fullscreen stage use**.

StagePro is intentionally simple, local-first, and performer-focused — no cloud, no accounts, no subscriptions.

---

## Features

### 🎤 Stage Display
- True fullscreen stage display
- Screen rotation support: **0° / 90° / 180° / 270°**
- Fill or fit scaling modes
- Footer hint bar for controls and song info

### 🎼 ChordPro Support
- Parses standard **ChordPro (.cho, .chordpro)** files
- Inline chords rendered **above lyrics**
- Proper word-wrapped chord + lyric alignment
- Supports common directives:
  - `{title}`
  - `{artist}`
  - `{key}`
  - `{tempo}`
  - `{time}`
  - `{comment}`
  - `{chorus}` / `{start_of_chorus}`

### 📄 Real Pagination
- Pagination is based on **actual rendered height**
- Uses `QTextDocument` for accurate page breaks
- No guessing, no line-count hacks
- Each page fits exactly on screen

### 🎨 Theme System
- Fully JSON-based, **shareable theme files**
- Themes control:
  - Background color
  - Lyrics text
  - Chord text
  - Chorus styling
  - Directive/comments styling
  - Footer / hint bar
- Default themes included:
  - Dark
  - Light
  - Green
  - Blue

### 🎛 Hands-Free Control
- Designed for Bluetooth foot pedals
- Supported keys:
  - **Page Up / Page Down**
  - **Left / Right arrows**
- Safe exit via **long-hold key combinations**
  - Prevents accidental exits mid-song

### 📁 Local-First Workflow
- Songs load from a local `songs/` directory
- Songs directory is intentionally **gitignored**
- No database required
- No internet connection required

---

## Project Structure

```
stagepro/
├── stagepro/
│   ├── config.py        # Config + theme loading
│   ├── playlist.py     # Song discovery and ordering
│   ├── chordpro.py     # ChordPro parsing
│   ├── render.py       # QTextDocument rendering
│   ├── paginate.py     # Real pagination logic
│   ├── ui_main.py      # Main PySide6 UI
│   └── __init__.py
│
├── songs/               # Local songs directory (gitignored)
│
├── stagepro.py          # App entry point
├── stagepro_config.example.json
├── README.md
├── LICENSE
├── CONTRIBUTORS
└── .gitignore
```

---

## Configuration

StagePro uses a JSON configuration file.

A sample file is provided:

```
stagepro_config.example.json
```

Copy it to:

```
stagepro_config.json
```

### Example

```json
{
  "songs_path": "songs",
  "theme": "dark.json",
  "rotation": 0,
  "scale_mode": "fit",
  "footer_enabled": true
}
```

---

## Themes

Themes are simple JSON files and can be freely shared.

Example theme snippet:

```json
{
  "background": "#000000",
  "lyrics": "#ffffff",
  "chords": "#00ff00",
  "chorus": "#00aa88",
  "directive": "#888888",
  "footer": "#444444"
}
```

Themes live alongside the app and can be swapped without restarting development.

---

## Controls

| Action            | Keys                         |
|------------------|------------------------------|
| Next page        | PgDn / Right Arrow           |
| Previous page    | PgUp / Left Arrow            |
| Safe exit        | Long-hold key combination    |

> Safe exit is intentionally delayed to avoid accidental quits during performance.

---

## Requirements

- Python **3.10+**
- PySide6
- Linux (primary target)
- macOS / Windows supported but not yet packaged

---

## Development

### Virtual Environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
python stagepro.py
```

---

## Status

- Actively developed
- Pre-release
- Targeting **v0.1.0 packaging** (AppImage / PyInstaller)

---

## License

See `LICENSE`

---

## Contributors

See `CONTRIBUTORS`