from __future__ import annotations

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

import addon_launcher  # noqa: E402
import on_demand_launcher  # noqa: E402


class OnDemandLauncherTests(unittest.TestCase):
    def test_command_for_channel_uses_enabled_camera(self) -> None:
        options = addon_launcher.default_options()
        options["cameras"] = [
            {
                "channel": 4,
                "enabled": True,
                "stream_id": 1,
                "rtsp_port": 8554,
                "rtsp_path": "driveway",
            }
        ]

        command = on_demand_launcher.command_for_channel(options, 4)

        self.assertEqual(command[command.index("--channel") + 1], "4")
        self.assertEqual(command[command.index("--rtsp-path") + 1], "driveway")

    def test_command_for_channel_rejects_disabled_camera(self) -> None:
        options = addon_launcher.default_options()
        options["cameras"] = [{"channel": 4, "enabled": False}]

        with self.assertRaisesRegex(ValueError, "not enabled"):
            on_demand_launcher.command_for_channel(options, 4)


if __name__ == "__main__":
    unittest.main()
