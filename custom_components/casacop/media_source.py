from __future__ import annotations

import datetime as dt
from typing import override

from homeassistant.components.media_player import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import CasaCopApi, Recording
from .const import DOMAIN
from .media_id import (
    build_recording_identifier,
    candidate_archive_days,
    parse_recording_identifier,
)
from .views import async_generate_playback_proxy_url


LOOKBACK_DAYS = 14


async def async_get_media_source(hass: HomeAssistant) -> CasaCopMediaSource:
    return CasaCopMediaSource(hass)


class CasaCopMediaSource(MediaSource):
    name = "CasaCop SD recordings"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    def _api(self, entry_id: str) -> CasaCopApi:
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or not isinstance(entry.runtime_data, CasaCopApi):
            raise Unresolvable("CasaCop bridge entry is unavailable")
        return entry.runtime_data

    @override
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        if item.identifier is None:
            raise Unresolvable("CasaCop media item has no identifier")
        try:
            entry_id, channel, record_type, start, end, quality = parse_recording_identifier(
                item.identifier
            )
        except (ValueError, IndexError):
            raise Unresolvable(f"CasaCop media item is not playable: {item.identifier}")
        return PlayMedia(
            async_generate_playback_proxy_url(
                entry_id,
                channel,
                record_type,
                start,
                end,
                quality,
            ),
            "video/mp4",
        )

    @override
    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        if not item.identifier:
            return self._root()
        parts = item.identifier.split("|")
        item_type = parts[0]
        if item_type == "ENTRY" and len(parts) == 2:
            return await self._channels(parts[1])
        if item_type == "CHANNEL" and len(parts) == 3:
            return await self._days(parts[1], int(parts[2]))
        if item_type == "DAY" and len(parts) == 6:
            return await self._recordings(
                parts[1], int(parts[2]), dt.date(int(parts[3]), int(parts[4]), int(parts[5]))
            )
        raise Unresolvable(f"Unknown CasaCop media item: {item.identifier}")

    def _root(self) -> BrowseMediaSource:
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"ENTRY|{entry.entry_id}",
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.PLAYLIST,
                title=entry.title,
                can_play=False,
                can_expand=True,
            )
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if isinstance(entry.runtime_data, CasaCopApi)
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.PLAYLIST,
            title=self.name,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _channels(self, entry_id: str) -> BrowseMediaSource:
        channels = await self._api(entry_id).async_health()
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"CHANNEL|{entry_id}|{channel}",
                media_class=MediaClass.CHANNEL,
                media_content_type=MediaType.PLAYLIST,
                title=f"Camera {channel + 1}",
                can_play=False,
                can_expand=True,
            )
            for channel in channels
        ]
        return self._directory(f"ENTRY|{entry_id}", "Cameras", children)

    async def _days(self, entry_id: str, channel: int) -> BrowseMediaSource:
        # Browsing a Media Source has a short frontend timeout. Searching the
        # camera's whole retention window here can exceed it, so expose cheap
        # candidate folders and query only the day the user actually opens.
        days = candidate_archive_days(dt_util.now().date(), LOOKBACK_DAYS)
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=f"DAY|{entry_id}|{channel}|{day.year}|{day.month}|{day.day}",
                media_class=MediaClass.DIRECTORY,
                media_content_type=MediaType.PLAYLIST,
                title=day.isoformat(),
                can_play=False,
                can_expand=True,
            )
            for day in days
        ]
        return self._directory(f"CHANNEL|{entry_id}|{channel}", f"Camera {channel + 1}", children)

    async def _recordings(
        self, entry_id: str, channel: int, day: dt.date
    ) -> BrowseMediaSource:
        local_start = dt.datetime.combine(day, dt.time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        local_end = local_start + dt.timedelta(days=1)
        recordings = await self._api(entry_id).async_recordings(
            channel, int(local_start.timestamp()), int(local_end.timestamp())
        )
        children = [self._recording_item(entry_id, recording) for recording in recordings]
        return self._directory(
            f"DAY|{entry_id}|{channel}|{day.year}|{day.month}|{day.day}",
            day.isoformat(),
            children,
        )

    def _recording_item(
        self, entry_id: str, recording: Recording
    ) -> BrowseMediaSource:
        begin = dt_util.as_local(dt.datetime.fromtimestamp(recording.begin_time, dt.UTC))
        duration = max(0, recording.end_time - recording.begin_time)
        kind = "Motion" if recording.record_type == 2 else "Recording"
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=build_recording_identifier(
                entry_id,
                recording.channel,
                recording.record_type,
                recording.begin_time,
                recording.end_time,
                recording.quality,
                begin.date().isoformat(),
            ),
            media_class=MediaClass.VIDEO,
            media_content_type=MediaType.VIDEO,
            title=f"{begin:%H:%M:%S} {duration}s {kind}",
            can_play=True,
            can_expand=False,
        )

    @staticmethod
    def _directory(
        identifier: str,
        title: str,
        children: list[BrowseMediaSource],
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.PLAYLIST,
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
        )
