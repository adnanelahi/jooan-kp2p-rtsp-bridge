from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

from archive_server import ArchiveApiServer, build_playback_ffmpeg_command  # noqa: E402


class FakeArchiveService:
    channels = [0]

    def list_recordings(
        self, channel: int, start: int, end: int, record_type: int, limit: int
    ) -> list[dict]:
        return [
            {
                "channel": channel,
                "record_type": 2,
                "begin_time": start + 10,
                "end_time": min(end, start + 40),
                "quality": 0,
            }
        ][:limit]


class ArchiveApiTests(unittest.TestCase):
    def test_playback_ffmpeg_command_transcodes_hevc_to_fragmented_mp4(self) -> None:
        command = build_playback_ffmpeg_command("H265", 59)

        self.assertEqual(command[command.index("-f") + 1], "hevc")
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertIn("frag_keyframe+empty_moov+default_base_moof", command)
        self.assertIn("59", command)

    def setUp(self) -> None:
        self.logs: list[str] = []
        self.server = ArchiveApiServer(
            ("127.0.0.1", 0), FakeArchiveService(), "test-token", self.logs.append
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def get_json(self, path: str, token: str | None = None) -> tuple[int, dict]:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        request = Request(self.base_url + path, headers=headers)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_health_lists_channels_with_credentials(self) -> None:
        status, payload = self.get_json("/health", "test-token")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok", "channels": [0]})

    def test_health_rejects_incorrect_credentials(self) -> None:
        status, payload = self.get_json("/health", "wrong-token")

        self.assertEqual(status, 401)
        self.assertEqual(payload, {"error": "unauthorized"})

    def test_recording_query_requires_bearer_token(self) -> None:
        status, payload = self.get_json("/api/recordings?channel=0&start=100&end=200")

        self.assertEqual(status, 401)
        self.assertEqual(payload, {"error": "unauthorized"})

    def test_recording_query_returns_json(self) -> None:
        status, payload = self.get_json(
            "/api/recordings?channel=0&start=100&end=200&type=15&limit=10",
            "test-token",
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["recordings"][0]["record_type"], 2)
        self.assertEqual(payload["recordings"][0]["begin_time"], 110)

    def test_recording_query_validates_required_parameters(self) -> None:
        status, payload = self.get_json(
            "/api/recordings?channel=0&start=100", "test-token"
        )

        self.assertEqual(status, 400)
        self.assertIn("end", payload["error"])


if __name__ == "__main__":
    unittest.main()
