from __future__ import annotations

from http import HTTPStatus
import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .api import CasaCopApi, CasaCopApiError
from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)


@callback
def async_generate_playback_proxy_url(
    entry_id: str,
    channel: int,
    record_type: int,
    start: int,
    end: int,
    quality: int,
) -> str:
    return CasaCopPlaybackProxyView.url.format(
        entry_id=entry_id,
        channel=channel,
        record_type=record_type,
        start=start,
        end=end,
        quality=quality,
    )


class CasaCopPlaybackProxyView(HomeAssistantView):
    requires_auth = True
    url = (
        "/api/casacop/playback/{entry_id}/{channel}/{record_type}/"
        "{start}/{end}/{quality}"
    )
    name = "api:casacop_playback"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        channel: str,
        record_type: str,
        start: str,
        end: str,
        quality: str,
    ) -> web.StreamResponse:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or not isinstance(entry.runtime_data, CasaCopApi):
            return web.Response(
                text="CasaCop bridge entry is unavailable",
                status=HTTPStatus.NOT_FOUND,
            )
        try:
            upstream = await entry.runtime_data.async_open_playback(
                int(channel), int(record_type), int(start), int(end), int(quality)
            )
        except (CasaCopApiError, ValueError) as exc:
            _LOGGER.warning("Could not open CasaCop playback: %s", exc)
            return web.Response(text=str(exc), status=HTTPStatus.BAD_GATEWAY)

        response = web.StreamResponse(
            status=upstream.status,
            headers={
                "Content-Type": "video/mp4",
                "Cache-Control": "no-store",
                "Content-Disposition": "inline",
            },
        )
        await response.prepare(request)
        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                await response.write(chunk)
        except (ConnectionResetError, TimeoutError):
            _LOGGER.debug("CasaCop playback client disconnected or timed out")
        finally:
            upstream.release()
        await response.write_eof()
        return response
