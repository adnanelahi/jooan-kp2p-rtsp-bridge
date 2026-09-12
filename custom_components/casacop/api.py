from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout


class CasaCopApiError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Recording:
    channel: int
    record_type: int
    begin_time: int
    end_time: int
    quality: int


class CasaCopApi:
    def __init__(
        self,
        session: ClientSession,
        host: str,
        port: int,
        token: str,
    ) -> None:
        self._session = session
        self._base_url = f"http://{host}:{port}"
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                self._base_url + path,
                headers=self._headers,
                timeout=30,
            ) as response:
                payload = await response.json(content_type=None)
                if response.status != 200:
                    raise CasaCopApiError(
                        f"Bridge returned HTTP {response.status}: {payload.get('error', 'unknown error')}"
                    )
                return payload
        except (ClientError, TimeoutError, ValueError) as exc:
            raise CasaCopApiError(f"Could not communicate with CasaCop bridge: {exc}") from exc

    async def async_health(self) -> list[int]:
        payload = await self._get_json("/health")
        return [int(channel) for channel in payload.get("channels", [])]

    async def async_recordings(
        self,
        channel: int,
        start: int,
        end: int,
        limit: int = 10_000,
    ) -> list[Recording]:
        query = urlencode(
            {
                "channel": channel,
                "start": start,
                "end": end,
                "type": 15,
                "limit": limit,
            }
        )
        payload = await self._get_json(f"/api/recordings?{query}")
        return [Recording(**item) for item in payload.get("recordings", [])]

    async def async_open_playback(
        self,
        channel: int,
        record_type: int,
        start: int,
        end: int,
        quality: int,
    ) -> ClientResponse:
        query = urlencode(
            {
                "channel": channel,
                "type": record_type,
                "start": start,
                "end": end,
                "quality": quality,
            }
        )
        try:
            response = await self._session.get(
                f"{self._base_url}/api/playback?{query}",
                headers=self._headers,
                timeout=ClientTimeout(connect=15, sock_connect=15, sock_read=30, total=None),
            )
        except (ClientError, TimeoutError) as exc:
            raise CasaCopApiError(f"Could not open CasaCop playback: {exc}") from exc
        if response.status != 200:
            detail = await response.text()
            response.release()
            raise CasaCopApiError(
                f"Playback bridge returned HTTP {response.status}: {detail}"
            )
        return response
