import os
import shlex
import shutil
import subprocess
import sys

SERVICE_DIR = os.path.expanduser("~/.config/systemd/user")
SERVICE_NAME = "ha-tv-tray"
SERVICE_PATH = os.path.join(SERVICE_DIR, f"{SERVICE_NAME}.service")

UNIT = """\
[Unit]
Description=HA TV Tray — KDE systray remote for Home Assistant
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={binary}
Restart=on-failure
RestartSec=3
Environment=DISPLAY={display}
Environment=DBUS_SESSION_BUS_ADDRESS={dbus}
{extra_env}

[Install]
WantedBy=default.target
"""


def _detect_binary() -> str:
    """Return the absolute path to `ha-tv-tray`."""
    which = shutil.which("ha-tv-tray")
    if which:
        return which
    # fallback: assume it's in $PATH
    return "ha-tv-tray"


def _detect_env() -> dict[str, str]:
    env = {
        "display": os.environ.get("DISPLAY", ":0"),
        "dbus": os.environ.get("DBUS_SESSION_BUS_ADDRESS", ""),
    }
    extras = {}
    for var in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "XAUTHORITY",
                "QT_QPA_PLATFORM", "DESKTOP_SESSION", "XDG_CURRENT_DESKTOP",
                "LANG", "LC_ALL", "LC_CTYPE"):
        val = os.environ.get(var)
        if val:
            extras[var] = val
    env["extra_env"] = "\n".join(
        f"Environment={k}={shlex.quote(v)}" for k, v in extras.items()
    )
    return env


def install_service() -> None:
    env = _detect_env()
    env["binary"] = _detect_binary()

    os.makedirs(SERVICE_DIR, exist_ok=True)

    unit = UNIT.format(**env)
    with open(SERVICE_PATH, "w") as f:
        f.write(unit)

    print(f"Wrote {SERVICE_PATH}")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", SERVICE_NAME], check=True
    )
    subprocess.run(
        ["systemctl", "--user", "restart", SERVICE_NAME], check=True
    )
    print("Service installed, enabled, and started.")
    print("Check status: systemctl --user status ha-tv-tray")


def uninstall_service() -> None:
    subprocess.run(
        ["systemctl", "--user", "stop", SERVICE_NAME],
        capture_output=True,
    )
    subprocess.run(
        ["systemctl", "--user", "disable", SERVICE_NAME],
        capture_output=True,
    )
    if os.path.exists(SERVICE_PATH):
        os.remove(SERVICE_PATH)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print("Service stopped, disabled, and removed.")


def print_service_status() -> None:
    result = subprocess.run(
        ["systemctl", "--user", "status", SERVICE_NAME],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
