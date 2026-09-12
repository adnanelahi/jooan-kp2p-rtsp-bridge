from __future__ import annotations


def build_recording_identifier(
    entry_id: str,
    channel: int,
    record_type: int,
    start: int,
    end: int,
    quality: int,
    day: str,
) -> str:
    """Build a playable ID whose tail is also useful to gallery cards."""
    return (
        f"FILE|{entry_id}|{channel}|{record_type}|{quality}/"
        f"{day}/{start}-{end}"
    )


def parse_recording_identifier(identifier: str) -> tuple[str, int, int, int, int, int]:
    """Parse current path-shaped IDs and legacy pipe-only IDs."""
    path_parts = identifier.split("/")
    if len(path_parts) == 3:
        metadata, _day, timestamp_range = path_parts
        metadata_parts = metadata.split("|")
        range_parts = timestamp_range.split("-")
        if metadata_parts[0] == "FILE" and len(metadata_parts) == 5 and len(range_parts) == 2:
            _, entry_id, channel, record_type, quality = metadata_parts
            start, end = range_parts
            return entry_id, int(channel), int(record_type), int(start), int(end), int(quality)

    legacy_parts = identifier.split("|")
    if legacy_parts[0] == "FILE" and len(legacy_parts) == 7:
        _, entry_id, channel, record_type, start, end, quality = legacy_parts
        return entry_id, int(channel), int(record_type), int(start), int(end), int(quality)

    raise ValueError("not a CasaCop recording identifier")
