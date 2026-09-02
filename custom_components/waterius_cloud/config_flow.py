"""Config flow for the Ватериус (Личный кабинет) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    WateriusApi,
    WateriusAuthError,
    WateriusConnectionError,
    WateriusError,
)
from .const import DEFAULT_BASE_URL, DOMAIN

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})


class WateriusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ввод токена личного кабинета."""

    VERSION = 1

    async def _async_validate_token(self, token: str) -> dict:
        """Проверить токен и вернуть данные пользователя."""
        api = WateriusApi(
            async_get_clientsession(self.hass), token, DEFAULT_BASE_URL
        )
        return await api.get_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Шаг добавления аккаунта."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                user = await self._async_validate_token(token)
            except WateriusAuthError:
                errors["base"] = "invalid_auth"
            except WateriusConnectionError:
                errors["base"] = "cannot_connect"
            except WateriusError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(user["user"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user.get("email") or f"Ватериус {user['user']}",
                    data={CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
