"""Data update coordinator for the Waterius Cloud integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    WateriusApi,
    WateriusAuthError,
    WateriusConnectionError,
    WateriusRateLimitError,
)
from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .model import WateriusDevice, parse_sources

_LOGGER = logging.getLogger(__name__)

type WateriusConfigEntry = ConfigEntry["WateriusCoordinator"]


class WateriusCoordinator(DataUpdateCoordinator[dict[int, WateriusDevice]]):
    """Опрашивает /api/source/ и раскладывает ответ в индекс по id прибора."""

    def __init__(self, hass: HomeAssistant, entry: WateriusConfigEntry) -> None:
        minutes = entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.entry = entry
        self.api = WateriusApi(
            async_get_clientsession(hass), entry.data[CONF_TOKEN], DEFAULT_BASE_URL
        )

    async def _async_update_data(self) -> dict[int, WateriusDevice]:
        try:
            sources = await self.api.get_sources()
        except WateriusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except WateriusRateLimitError as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except WateriusConnectionError as err:
            raise UpdateFailed(str(err)) from err

        try:
            return parse_sources(sources)
        except (KeyError, TypeError, ValueError) as err:
            raise UpdateFailed(f"Облако Ватериус вернуло некорректные данные: {err}") from err
