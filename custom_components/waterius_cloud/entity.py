"""Shared entity plumbing for the Waterius Cloud integration."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import WateriusCoordinator
from .model import WateriusChannel, WateriusDevice


class WateriusDeviceEntity(CoordinatorEntity[WateriusCoordinator]):
    """Общий предок: привязка к прибору и доступность."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WateriusCoordinator, source_id: int) -> None:
        super().__init__(coordinator)
        self._source_id = source_id

    @property
    def device(self) -> WateriusDevice | None:
        """Прибор из последнего ответа облака, либо None, если он пропал."""
        return self.coordinator.data.get(self._source_id)

    @property
    def available(self) -> bool:
        """Сущность недоступна, если опрос не удался или прибор исчез из аккаунта."""
        return super().available and self.device is not None

    @property
    def device_info(self) -> DeviceInfo:
        device = self.device
        info = DeviceInfo(
            identifiers={(DOMAIN, str(self._source_id))},
            manufacturer=MANUFACTURER,
            name=device.name if device else f"Ватериус {self._source_id}",
        )
        if device:
            if device.sw_version:
                info["sw_version"] = device.sw_version
            if device.mac:
                info["connections"] = {(CONNECTION_NETWORK_MAC, device.mac)}
        return info


def channel_display_name(channel: WateriusChannel, device: WateriusDevice) -> str:
    """Имя канала.

    Если на приборе несколько каналов одного ``data_type`` (например, два входа
    холодной воды), к имени добавляется номер канала — иначе они неразличимы в
    списке сущностей. Единственный канал такого типа остаётся без номера.
    """
    same_type = sum(
        1 for other in device.channels.values() if other.data_type == channel.data_type
    )
    if same_type > 1:
        return f"{channel.name} {channel.number + 1}"
    return channel.name


@callback
def async_setup_dynamic_entities(
    coordinator: WateriusCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[dict[int, WateriusDevice]], dict[str, Entity]],
) -> None:
    """Создать сущности сейчас и при появлении новых приборов или каналов.

    ``factory`` получает индекс приборов и возвращает словарь
    ``{ключ: сущность}``; ключ должен совпадать с unique_id сущности, по нему
    отсеиваются уже созданные.
    """
    known: set[str] = set()

    @callback
    def _sync() -> None:
        if not coordinator.data:
            return
        candidates = factory(coordinator.data)
        new = {key: entity for key, entity in candidates.items() if key not in known}
        if new:
            known.update(new)
            async_add_entities(new.values())

    _sync()
    coordinator.entry.async_on_unload(coordinator.async_add_listener(_sync))
