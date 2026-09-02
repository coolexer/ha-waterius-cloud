"""The Ватериус (Личный кабинет) integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import WateriusConfigEntry, WateriusCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> bool:
    """Set up Ватериус from a config entry."""
    coordinator = WateriusCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Перезагрузка при смене интервала опроса выполняется самим
    # WateriusOptionsFlow (OptionsFlowWithReload в config_flow.py), а не
    # обработчиком обновлений здесь: зарегистрированный тут update listener
    # заставлял async_update_reload_and_abort в реаутентификации перезагружать
    # запись дважды и печатать депрекейшн HA о конфликте с update listener.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
