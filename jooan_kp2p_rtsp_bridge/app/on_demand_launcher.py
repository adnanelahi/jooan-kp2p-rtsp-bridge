from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from addon_launcher import (
    OPTIONS_PATH,
    build_bridge_command,
    build_camera_configs,
    load_options,
    load_options_file,
    log_event,
)


CONFIG_PATH_ENV = "BRIDGE_CONFIG_PATH"
CONTAINER_CONFIG_PATHS = (
    Path("/config/bridge-config.json"),
    Path("/config/options.json"),
)


def load_runtime_options() -> dict:
    configured_path = os.environ.get(CONFIG_PATH_ENV)
    if configured_path:
        return load_options_file(Path(configured_path))
    for path in CONTAINER_CONFIG_PATHS:
        if path.exists():
            return load_options_file(path)
    if OPTIONS_PATH.exists():
        return load_options()
    raise FileNotFoundError("bridge configuration file was not found")


def command_for_channel(options: dict, channel: int) -> list[str]:
    for camera in build_camera_configs(options):
        if camera.channel == channel:
            return build_bridge_command(options, camera)
    raise ValueError(f"channel {channel} is not enabled")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start one camera bridge for a MediaMTX reader")
    parser.add_argument("--channel", type=int, required=True)
    args = parser.parse_args()
    try:
        command = command_for_channel(load_runtime_options(), args.channel)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log_event(f"on_demand_error=configuration channel={args.channel} reason={exc}")
        return 1

    log_event(f"on_demand_start=reader_connected channel={args.channel}")
    os.execv(command[0], command)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
