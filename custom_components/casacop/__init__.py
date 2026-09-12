from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CasaCopApi
from .const import CONF_API_TOKEN
from .views import CasaCopPlaybackProxyView


type CasaCopConfigEntry = ConfigEntry[CasaCopApi]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.http.register_view(CasaCopPlaybackProxyView(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CasaCopConfigEntry) -> bool:
    api = CasaCopApi(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_API_TOKEN],
    )
    entry.runtime_data = api
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CasaCopConfigEntry) -> bool:
    return True
