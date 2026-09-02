"""Config flow for the Ватериус (Личный кабинет) integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    WateriusApi,
    WateriusAuthError,
    WateriusConnectionError,
    WateriusError,
)
from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
)

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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Токен перестал работать — попросить новый."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ввод нового токена для уже добавленного аккаунта."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

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
                if str(user["user"]) != entry.unique_id:
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> WateriusOptionsFlow:
        """Вернуть обработчик настроек."""
        return WateriusOptionsFlow()


class WateriusOptionsFlow(OptionsFlow):
    """Настройка интервала опроса."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Единственный шаг настроек."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES, default=current
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=1440))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
