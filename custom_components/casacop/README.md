# CasaCop / Jooan SD Recordings

Development Home Assistant integration for the Jooan KP2P RTSP Bridge archive API.

It registers a `media-source://casacop` provider that browses enabled camera channels, recording days, and SD-card segments. Playable entries resolve to an authenticated Home Assistant proxy, which streams browser-compatible H.264/MP4 from the bridge without exposing its bearer token.

The matching bridge App must be version `0.6.0-casacop.1` or newer with `archive_api_enabled` set to `true`.

