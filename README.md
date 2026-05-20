# ha-tv-tray

KDE system tray TV remote control via Home Assistant. Shows a Plasma-style popup
with your universal-remote-card dashboard.

## Requirements

- **Arch Linux** with **KDE Plasma 6**
- **Home Assistant** instance with [universal-remote-card](https://github.com/Nerwyn/universal-remote-card) installed via HACS
- A Lovelace dashboard with the card configured

## Install

```bash
sudo pacman -S pyside6 python-yaml

git clone https://github.com/PrivateButts/ha-tv-tray.git
cd ha-tv-tray

uv tool install --no-deps . && uv tool install --reinstall pyyaml
# Or with pipx:
# pipx install . --no-deps
```

`pyside6` and `python-yaml` are system packages on Arch. The app uses
`KStatusNotifierItem` for native KDE tray integration (auto-detected at runtime).

## Quick Start

```bash
ha-tv-tray \
  --config-url http://homeassistant.local:8123 \
  --config-token eyJ... \
  --config-dash-path /lovelace/tv

ha-tv-tray
```

## Configuration

`~/.config/ha-tv-tray/config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `ha_url` | — | Home Assistant URL |
| `ha_token` | — | Long-Lived Access Token (or `HA_TOKEN` env var) |
| `dashboard_path` | `/lovelace/tv` | Dashboard path with the remote card |
| `panel_width` | `400` | Panel width in pixels |
| `panel_height` | `680` | Panel height in pixels |
| `position` | `bottom-right` | Fallback if click position unavailable |

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
just setup       # uv sync + git hooks (uses system PySide6 via --system-site-packages)
just run         # uv run ha-tv-tray
just debug       # uv run ha-tv-tray --debug
```

## How It Works

1. Uses **KStatusNotifierItem** for native KDE systray integration when available
2. On click, receives **screen-coordinate click position** from the StatusNotifier D-Bus protocol
3. Panel is positioned near the click (bottom-right or top-right of the screen)
4. Falls back to `QSystemTrayIcon` (+ `QCursor.pos()` heuristic) if `KStatusNotifierItem` is not available
5. Plasma-style popup: rounded corners, drop shadow, fade-in animation
6. Auto-closes when clicking anywhere outside the panel
