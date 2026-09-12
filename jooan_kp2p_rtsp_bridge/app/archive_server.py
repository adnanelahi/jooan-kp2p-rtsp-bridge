from __future__ import annotations

import json
import random
import secrets
import subprocess
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterator
from urllib.parse import parse_qs, urlparse

from kp2p_ws_client import (
    PROC_FRAME_TYPE_IFRAME,
    Endpoint,
    Kp2pClient,
    Recording,
    VideoFrame,
    connect_via_uid,
)


MAX_RECORDING_RESULTS = 10_000
MAX_PLAYBACK_SECONDS = 3_600


class ArchiveRequestError(ValueError):
    pass


class ArchiveService:
    """Open short-lived, read-only KP2P sessions for archive operations."""

    def __init__(self, options: dict, channels: list[int]) -> None:
        self.options = options
        self.channels = sorted(set(channels))

    def _endpoint(self, timeout: float) -> Endpoint:
        if self.options.get("use_uid", False):
            uid = str(self.options.get("uid", ""))
            if not uid:
                raise ArchiveRequestError("uid is required when use_uid is enabled")
            return connect_via_uid(uid, timeout)
        session_id = random.randint(1, 10_000)
        return Endpoint(
            str(self.options.get("host", "192.168.1.10")),
            int(self.options.get("port", 10000)),
            session_id,
            session_id,
            0,
            "",
        )

    def list_recordings(
        self,
        channel: int,
        start: int,
        end: int,
        record_type: int = 15,
        limit: int = 1_000,
    ) -> list[dict]:
        if channel not in self.channels:
            raise ArchiveRequestError(f"channel {channel} is not enabled")
        if start >= end:
            raise ArchiveRequestError("start must be before end")
        if not 1 <= limit <= MAX_RECORDING_RESULTS:
            raise ArchiveRequestError(f"limit must be between 1 and {MAX_RECORDING_RESULTS}")
        timeout = float(self.options.get("archive_timeout", 15))
        client = Kp2pClient(self._endpoint(timeout), timeout=timeout)
        try:
            client.connect()
            client.login(
                str(self.options.get("username", "admin")),
                str(self.options.get("password", "")),
            )
            recordings = client.search_recordings(
                channel,
                start,
                end,
                record_type=record_type,
                max_results=limit,
            )
            return [asdict(recording) for recording in recordings]
        finally:
            client.close()

    def playback_frames(
        self,
        channel: int,
        start: int,
        end: int,
        record_type: int,
        quality: int,
    ) -> Iterator[VideoFrame]:
        if channel not in self.channels:
            raise ArchiveRequestError(f"channel {channel} is not enabled")
        duration = end - start
        if not 1 <= duration <= MAX_PLAYBACK_SECONDS:
            raise ArchiveRequestError(
                f"playback duration must be between 1 and {MAX_PLAYBACK_SECONDS} seconds"
            )
        timeout = float(self.options.get("archive_timeout", 15))
        client = Kp2pClient(self._endpoint(timeout), timeout=timeout)
        recording = Recording(channel, record_type, start, end, quality)
        synced = False
        try:
            client.connect()
            client.login(
                str(self.options.get("username", "admin")),
                str(self.options.get("password", "")),
            )
            client.open_recording(recording)
            while True:
                frame = client.recv_recorded_media()
                if not isinstance(frame, VideoFrame):
                    continue
                if not synced:
                    if frame.frame_type != PROC_FRAME_TYPE_IFRAME:
                        continue
                    synced = True
                yield frame
        finally:
            try:
                client.close_recording(channel)
            except Exception:
                pass
            client.close()


def build_playback_ffmpeg_command(codec: str, duration: int) -> list[str]:
    input_format = "hevc" if codec.upper() in {"H265", "HEVC"} else "h264"
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "+genpts+nobuffer",
        "-r",
        "15",
        "-f",
        input_format,
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-g",
        "15",
        "-keyint_min",
        "15",
        "-sc_threshold",
        "0",
        "-t",
        str(duration),
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-f",
        "mp4",
        "pipe:1",
    ]


class ArchiveApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: ArchiveService,
        token: str,
        logger: Callable[[str], None],
    ) -> None:
        if not token:
            raise ValueError("archive_api_token must not be empty")
        self.archive_service = service
        self.archive_token = token
        self.archive_logger = logger
        super().__init__(address, ArchiveRequestHandler)


class ArchiveRequestHandler(BaseHTTPRequestHandler):
    server: ArchiveApiServer

    def log_message(self, format: str, *args: object) -> None:
        self.server.archive_logger(f"archive_http={format % args}")

    def _json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.archive_token}"
        supplied = self.headers.get("Authorization", "")
        return secrets.compare_digest(supplied, expected)

    @staticmethod
    def _one(params: dict[str, list[str]], name: str, default: str | None = None) -> str:
        values = params.get(name)
        if not values:
            if default is not None:
                return default
            raise ArchiveRequestError(f"missing query parameter: {name}")
        return values[0]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if parsed.path == "/health":
            self._json(
                HTTPStatus.OK,
                {"status": "ok", "channels": self.server.archive_service.channels},
            )
            return
        if parsed.path == "/api/playback":
            self._serve_playback(parse_qs(parsed.query))
            return
        if parsed.path != "/api/recordings":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            params = parse_qs(parsed.query)
            channel = int(self._one(params, "channel"))
            start = int(self._one(params, "start"))
            end = int(self._one(params, "end"))
            record_type = int(self._one(params, "type", "15"))
            limit = int(self._one(params, "limit", "1000"))
            recordings = self.server.archive_service.list_recordings(
                channel, start, end, record_type, limit
            )
            self._json(
                HTTPStatus.OK,
                {
                    "channel": channel,
                    "start": start,
                    "end": end,
                    "count": len(recordings),
                    "recordings": recordings,
                },
            )
        except (ArchiveRequestError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # keep protocol details in the App log
            self.server.archive_logger(
                f"archive_query_error={type(exc).__name__}: {exc}"
            )
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "camera_query_failed"})

    def _serve_playback(self, params: dict[str, list[str]]) -> None:
        frames: Iterator[VideoFrame] | None = None
        process: subprocess.Popen[bytes] | None = None
        stop_feeder = threading.Event()
        response_started = False
        try:
            channel = int(self._one(params, "channel"))
            start = int(self._one(params, "start"))
            end = int(self._one(params, "end"))
            record_type = int(self._one(params, "type", "15"))
            quality = int(self._one(params, "quality", "0"))
            frames = self.server.archive_service.playback_frames(
                channel, start, end, record_type, quality
            )
            first_frame = next(frames)
            process = subprocess.Popen(
                build_playback_ffmpeg_command(first_frame.codec, end - start),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )

            def feed() -> None:
                assert process is not None and process.stdin is not None and frames is not None
                try:
                    process.stdin.write(first_frame.payload)
                    for frame in frames:
                        if stop_feeder.is_set():
                            break
                        process.stdin.write(frame.payload)
                except (BrokenPipeError, OSError):
                    pass
                except Exception as exc:
                    self.server.archive_logger(
                        f"archive_playback_source_error={type(exc).__name__}: {exc}"
                    )
                finally:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass

            feeder = threading.Thread(target=feed, name="archive-playback-feed", daemon=True)
            feeder.start()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Connection", "close")
            self.end_headers()
            response_started = True
            assert process.stdout is not None
            while chunk := process.stdout.read(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (ArchiveRequestError, ValueError, StopIteration) as exc:
            if not response_started and not self.wfile.closed:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc) or "no_playback_frames"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.server.archive_logger(
                f"archive_playback_error={type(exc).__name__}: {exc}"
            )
            if not response_started:
                try:
                    self._json(HTTPStatus.BAD_GATEWAY, {"error": "playback_failed"})
                except (BrokenPipeError, ConnectionResetError):
                    pass
        finally:
            stop_feeder.set()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            if frames is not None:
                close_frames = getattr(frames, "close", None)
                if close_frames is not None:
                    close_frames()


def start_archive_api(
    options: dict,
    channels: list[int],
    logger: Callable[[str], None],
) -> tuple[ArchiveApiServer, threading.Thread]:
    port = int(options.get("archive_api_port", 8099))
    service = ArchiveService(options, channels)
    server = ArchiveApiServer(
        ("0.0.0.0", port),
        service,
        str(options.get("archive_api_token", "")),
        logger,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="archive-api",
        daemon=True,
    )
    thread.start()
    logger(f"archive_api=started url=http://<HA_HOST_IP>:{port}")
    return server, thread
