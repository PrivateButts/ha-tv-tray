import argparse
import logging
import sys

from .config import load_config, write_config
from .panel import SystrayApp
from .service import install_service, uninstall_service, print_service_status

VERSION = "0.4.1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="KDE system tray TV remote control via Home Assistant"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml (default: ~/.config/ha-tv-tray/config.yaml)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"ha-tv-tray {VERSION}",
    )

    setup = parser.add_argument_group("bootstrap")
    setup.add_argument(
        "--config-url",
        metavar="URL",
        help="Home Assistant URL (e.g. http://homeassistant.local:8123)",
    )
    setup.add_argument(
        "--config-token",
        metavar="TOKEN",
        help="Home Assistant Long-Lived Access Token",
    )
    setup.add_argument(
        "--config-dash-path",
        metavar="PATH",
        help="Lovelace dashboard path (default: /lovelace/tv)",
    )

    service = parser.add_argument_group("systemd user service")
    service.add_argument(
        "--install-service",
        action="store_true",
        help="Install and start a systemd --user service for ha-tv-tray",
    )
    service.add_argument(
        "--uninstall-service",
        action="store_true",
        help="Stop and remove the systemd --user service",
    )
    service.add_argument(
        "--service-status",
        action="store_true",
        help="Show the systemd --user service status",
    )

    return parser.parse_args(argv)


def _bootstrap(args: argparse.Namespace) -> None:
    url = args.config_url.rstrip("/")
    token = args.config_token
    dash = args.config_dash_path or "/lovelace/tv"

    path = write_config(ha_url=url, ha_token=token, dashboard_path=dash)
    print(f"Config written to {path}")
    print(f"  ha_url:          {url}")
    print(f"  dashboard_path:  {dash}")
    print()
    print("Run \033[1mha-tv-tray\033[0m to start the systray app.")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s:%(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.install_service:
        install_service()
        return

    if args.uninstall_service:
        uninstall_service()
        return

    if args.service_status:
        print_service_status()
        return

    if args.config_url or args.config_token:
        if not args.config_url:
            print("Error: --config-url is required for bootstrap", file=sys.stderr)
            sys.exit(1)
        if not args.config_token:
            print("Error: --config-token is required for bootstrap", file=sys.stderr)
            sys.exit(1)
        _bootstrap(args)
        return

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "Run \033[1mha-tv-tray --config-url ... --config-token ...\033[0m "
            "to bootstrap.",
            file=sys.stderr,
        )
        sys.exit(1)
    except (ValueError, KeyError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    app = SystrayApp(config)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
