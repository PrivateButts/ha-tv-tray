# ha-tv-tray

KDE system tray TV remote control via Home Assistant. Shows a Plasma-style popup
with your universal-remote-card dashboard.

## Quick Start

```bash
# Install via pipx (everything from PyPI, no system packages needed)
pipx install .

# Bootstrap config
ha-tv-tray --config-url http://homeassistant.local:8123 --config-token eyJ...

# Run
ha-tv-tray
```

## Requirements

- **KDE Plasma 6** (Linux)
- **Home Assistant** with [universal-remote-card](https://github.com/Nerwyn/universal-remote-card) (via HACS)
- A Lovelace dashboard with the card configured

## Configuration

`~/.config/ha-tv-tray/config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `ha_url` | — | Home Assistant URL |
| `ha_token` | — | Long-Lived Access Token (or `HA_TOKEN` env var) |
| `dashboard_path` | `/lovelace/tv` | Dashboard path with the remote card |
| `panel_width` | `400` | Panel width in pixels |
| `panel_height` | `680` | Panel height in pixels |
| `position` | `bottom-right` | Fallback position (`bottom-right` / `top-right`) |

## CLI

```
ha-tv-tray [--config PATH] [--debug] [--version]

Bootstrap:
  --config-url URL         Home Assistant URL
  --config-token TOKEN     Long-Lived Access Token
  --config-dash-path PATH  Dashboard path (default: /lovelace/tv)
```

## Development

```bash
git clone <repo> && cd ha-tv-tray
just setup       # uv sync + git hooks
just run         # uv run ha-tv-tray
just debug       # uv run ha-tv-tray --debug
just bootstrap   # uv run ha-tv-tray --config-url ... --config-token ...
```

## How It Works

1. Minialist Python app using PySide6 + QtWebEngine
2. System tray icon via `QSystemTrayIcon`
3. On click, detects screen edge via `QCursor.pos()` and positions near the tray
4. Panel has Plasma-style rounded corners, drop shadow, and fade-in animation
5. Auto-closes when clicking outside the panel
6. On pure Wayland, KWin may center the window; set `QT_QPA_PLATFORM=xcb` for exact positioning
