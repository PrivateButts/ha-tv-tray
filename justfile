# Bootstrap the development environment
setup:
    uv sync
    git config core.hooksPath .githooks

# Run the app (pass extra args after --, e.g. just run -- --debug)
run *args:
    uv run ha-tv-tray {{ args }}

# Run with debug logging
debug *args:
    uv run ha-tv-tray --debug {{ args }}

# Bootstrap config from Home Assistant
bootstrap url token dash_path="/lovelace/tv":
    uv run ha-tv-tray --config-url {{ url }} --config-token {{ token }} --config-dash-path {{ dash_path }}
