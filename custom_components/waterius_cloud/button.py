"""Button platform for the Waterius Cloud integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import WateriusAuthError, WateriusError, WateriusRateLimitError
from .coordinator import WateriusConfigEntry, WateriusCoordinator
from .entity import WateriusDeviceEntity, async_setup_dynamic_entities
from .model import WateriusDevice


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Waterius refresh buttons."""
    coordinator = entry.runtime_data

    def _factory(devices: dict[int, WateriusDevice]) -> dict[str, Entity]:
        return {
            f"device_{device.id}_refresh": WateriusRefreshButton(coordinator, device.id)
            for device in devices.values()
        }

    async_setup_dynamic_entities(coordinator, async_add_entities, _factory)


class WateriusRefreshButton(WateriusDeviceEntity, ButtonEntity):
    """Попросить облако обновить данные прибора.

    Недоступна, пока облако не выставит ``can_refresh``: спящий прибор Ватериус
    разбудить нельзя, и серая кнопка честнее ошибки при нажатии.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "refresh"

    def __init__(self, coordinator: WateriusCoordinator, source_id: int) -> None:
        super().__init__(coordinator, source_id)
        self._attr_unique_id = f"device_{source_id}_refresh"

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and device is not None and device.can_refresh

    async def async_press(self) -> None:
        """Дёрнуть обновление и сразу перечитать данные."""
        try:
            await self.coordinator.api.refresh_source(self._source_id)
        except WateriusAuthError as err:
            # ConfigEntryAuthFailed поднятое из сервисного вызова реаутентификацию
            # не запускает (это работает только из async_setup_entry), поэтому
            # запускаем её явно.
            self.coordinator.entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Облако Ватериус отклонило токен. Запрошена повторная авторизация."
            ) from err
        except WateriusRateLimitError as err:
            wait = f" Подождите {err.retry_after} с." if err.retry_after else ""
            raise HomeAssistantError(
                f"Облако Ватериус отклонило обновление.{wait}"
            ) from err
        except WateriusError as err:
            raise HomeAssistantError(f"Не удалось обновить прибор: {err}") from err

        await self.coordinator.async_request_refresh()
