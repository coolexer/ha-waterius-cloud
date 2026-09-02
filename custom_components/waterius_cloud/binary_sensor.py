"""Binary sensor platform for the Waterius Cloud integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import WateriusConfigEntry, WateriusCoordinator
from .entity import WateriusDeviceEntity, async_setup_dynamic_entities, channel_display_name
from .model import WateriusChannel, WateriusDevice, is_offline


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Waterius binary sensors."""
    coordinator = entry.runtime_data

    def _factory(devices: dict[int, WateriusDevice]) -> dict[str, Entity]:
        entities: dict[str, Entity] = {}
        for device in devices.values():
            key = f"device_{device.id}_connectivity"
            entities[key] = WateriusConnectivitySensor(coordinator, device.id)
            for channel in device.channels.values():
                key = f"channel_{channel.id}_problem"
                entities[key] = WateriusChannelProblem(
                    coordinator, device.id, channel.id
                )
        return entities

    async_setup_dynamic_entities(coordinator, async_add_entities, _factory)


class WateriusChannelProblem(WateriusDeviceEntity, BinarySensorEntity):
    """Счётчик не работает или у облака есть претензии к каналу."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: WateriusCoordinator, source_id: int, channel_id: int
    ) -> None:
        super().__init__(coordinator, source_id)
        self._channel_id = channel_id
        self._attr_unique_id = f"channel_{channel_id}_problem"
        device = self.device
        channel = self.channel
        if device is not None and channel is not None:
            self._attr_name = f"{channel_display_name(channel, device)}: проблема"

    @property
    def channel(self) -> WateriusChannel | None:
        device = self.device
        if device is None:
            return None
        return device.channels.get(self._channel_id)

    @property
    def available(self) -> bool:
        return super().available and self.channel is not None

    @property
    def is_on(self) -> bool | None:
        channel = self.channel
        return channel.has_problem if channel else None

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        channel = self.channel
        if channel is None:
            return None
        return {"warnings": channel.warnings}


class WateriusConnectivitySensor(WateriusDeviceEntity, BinarySensorEntity):
    """Выходит ли прибор на связь."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connectivity"

    def __init__(self, coordinator: WateriusCoordinator, source_id: int) -> None:
        super().__init__(coordinator, source_id)
        self._attr_unique_id = f"device_{source_id}_connectivity"

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        return not is_offline(device, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        device = self.device
        if device is None:
            return None
        return {"warnings": device.warnings, "period_min": device.period_min}
