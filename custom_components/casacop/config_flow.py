from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CasaCopApi, CasaCopApiError
from .const import CONF_API_TOKEN, DEFAULT_NAME, DEFAULT_PORT, DOMAIN


class CasaCopConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(f"{host}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            api = CasaCopApi(
                async_get_clientsession(self.hass),
                host,
                user_input[CONF_PORT],
                user_input[CONF_API_TOKEN],
            )
            try:
                channels = await api.async_health()
            except CasaCopApiError:
                errors["base"] = "cannot_connect"
            else:
                if not channels:
                    errors["base"] = "no_channels"
                else:
                    user_input[CONF_HOST] = host
                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=user_input
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): vol.All(
                    str, vol.Length(min=1)
                ),
                vol.Required(CONF_HOST): vol.All(str, vol.Length(min=1)),
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_API_TOKEN): vol.All(str, vol.Length(min=16)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
