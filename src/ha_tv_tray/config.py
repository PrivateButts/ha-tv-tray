import os
import yaml
from dataclasses import dataclass, asdict

CONFIG_DIR = os.path.expanduser("~/.config/ha-tv-tray")
CONFIG_FILE_NAME = "config.yaml"


@dataclass
class Config:
    ha_url: str
    ha_token: str
    dashboard_path: str = "/lovelace/tv"
    panel_width: int = 400
    panel_height: int = 680
    slide_duration_ms: int = 400
    position: str = "bottom-right"


def _search_paths(custom_path: str | None) -> list[str]:
    paths = []
    if custom_path:
        paths.append(custom_path)
    paths.extend([
        os.path.join(CONFIG_DIR, CONFIG_FILE_NAME),
        os.path.expanduser("~/.ha-tv-tray.yaml"),
        "config.yaml",
    ])
    return paths


def load_config(custom_path: str | None = None) -> Config:
    for path in _search_paths(custom_path):
        if not os.path.exists(path):
            continue

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        ha_url = (raw.get("ha_url") or "").rstrip("/")
        ha_token = raw.get("ha_token") or os.environ.get("HA_TOKEN")

        if not ha_url:
            raise ValueError(f"{path}: ha_url is required")
        if not ha_token:
            raise ValueError(
                f"{path}: ha_token is required (or set HA_TOKEN env var)"
            )

        return Config(
            ha_url=ha_url,
            ha_token=ha_token,
            dashboard_path=raw.get("dashboard_path", "/lovelace/tv"),
            panel_width=int(raw.get("panel_width", 400)),
            panel_height=int(raw.get("panel_height", 680)),
            slide_duration_ms=int(raw.get("slide_duration_ms", 400)),
            position=raw.get("position", "bottom-right"),
        )

    searched = ", ".join(_search_paths(custom_path))
    raise FileNotFoundError(
        f"No config found. Create {CONFIG_DIR}/{CONFIG_FILE_NAME} "
        f"with ha_url and ha_token\nSearched: {searched}"
    )


def write_config(
    ha_url: str,
    ha_token: str,
    dashboard_path: str = "/lovelace/tv",
) -> str:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = os.path.join(CONFIG_DIR, CONFIG_FILE_NAME)

    data = {
        "ha_url": ha_url.rstrip("/"),
        "ha_token": ha_token,
        "dashboard_path": dashboard_path,
    }

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

    return path
