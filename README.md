# ha-tv-tray

KDE system tray TV remote control via Home Assistant. Shows a slide-out panel with your universal-remote-card dashboard.

## Requirements

- **Arch Linux** with **KDE Plasma 6**
- **Home Assistant** instance with [universal-remote-card](https://github.com/Nerwyn/universal-remote-card) installed via HACS
- A Lovelace dashboard with the card configured

## Install

Dependencies are managed by UV/pip — no system packages required.

```bash
# Install from local checkout with uv
uv tool install .

# Or via pipx
pipx install .

# Or from git
pipx install git+https://github.com/PrivateButts/ha-tv-tray.git
```

> **Optional:** Pre-installing PySide6 via pacman avoids pulling it from PyPI:
> ```
> sudo pacman -S pyside6 python-yaml
> ```

## Quick Start

Bootstrap config in one command:

```bash
ha-tv-tray \
  --config-url http://homeassistant.local:8123 \
  --config-token eyJ... \
  --config-dash-path /lovelace/tv
```

Then run:

```bash
ha-tv-tray
```

## Manual Setup

1. **Create a TV remote dashboard** in Home Assistant with universal-remote-card.

2. **Generate a Long-Lived Access Token**:
   - HA Profile → Security → Long-Lived Access Tokens → Create Token

3. **Create config** at `~/.config/ha-tv-tray/config.yaml`:

```yaml
ha_url: "http://homeassistant.local:8123"
ha_token: "eyJ..."
dashboard_path: "/lovelace/tv"
```

4. **Run**: `ha-tv-tray`

## Usage

- **Left-click** tray icon → toggle slide-out panel
- **Right-click** tray icon → menu (Show/Hide, Quit)
- Panel slides up from bottom-right (or down from top-right)

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `ha_url` | — | Home Assistant URL |
| `ha_token` | — | Long-Lived Access Token (or `HA_TOKEN` env var) |
| `dashboard_path` | `/lovelace/tv` | Dashboard path with the remote card |
| `panel_width` | `400` | Panel width in pixels |
| `panel_height` | `680` | Panel height in pixels |
| `slide_duration_ms` | `400` | Slide animation duration |
| `position` | `bottom-right` | `bottom-right` or `top-right` |

## CLI

```
ha-tv-tray [--config PATH] [--version]

Bootstrap:
  --config-url URL         Home Assistant URL
  --config-token TOKEN     Long-Lived Access Token
  --config-dash-path PATH  Dashboard path (default: /lovelace/tv)
```

## Development

```bash
git clone <repo>
cd ha-tv-tray

# Create venv and install
uv sync

# Run
uv run ha-tv-tray

# Bootstrap
uv run ha-tv-tray --config-url http://localhost:8123 --config-token eyJ...
```

## How It Works

1. App starts → loads config → creates system tray icon
2. On click, a frameless panel slides out from the screen edge
3. The panel embeds a QtWebEngine view pointing to your HA dashboard
4. Auth is injected automatically (bearer token via request interceptor + localStorage)
5. The universal-remote-card renders inside HA's frontend as designed
