"""Sensor platform for the Waterius Cloud integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import WateriusConfigEntry, WateriusCoordinator
from .entity import WateriusDeviceEntity, async_setup_dynamic_entities
from .model import WateriusChannel, WateriusDevice


@dataclass(frozen=True, kw_only=True)
class WateriusDiagnosticDescription(SensorEntityDescription):
    """Описание диагностического сенсора прибора."""

    value_fn: Callable[[WateriusDevice], float | int | datetime | None]


DIAGNOSTIC_SENSORS: tuple[WateriusDiagnosticDescription, ...] = (
    WateriusDiagnosticDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.battery,
    ),
    WateriusDiagnosticDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.voltage,
    ),
    WateriusDiagnosticDescription(
        key="last_wakeup",
        translation_key="last_wakeup",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.last_wakeup,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WateriusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Waterius sensors."""
    coordinator = entry.runtime_data

    def _factory(devices: dict[int, WateriusDevice]) -> dict[str, Entity]:
        entities: dict[str, Entity] = {}
        for device in devices.values():
            for description in DIAGNOSTIC_SENSORS:
                key = f"device_{device.id}_{description.key}"
                entities[key] = WateriusDiagnosticSensor(
                    coordinator, device.id, description
                )
            for channel in device.channels.values():
                key = f"channel_{channel.id}"
                entities[key] = WateriusChannelSensor(coordinator, device.id, channel.id)
        return entities

    async_setup_dynamic_entities(coordinator, async_add_entities, _factory)


class WateriusChannelSensor(WateriusDeviceEntity, SensorEntity):
    """Показание одного счётчика."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, coordinator: WateriusCoordinator, source_id: int, channel_id: int
    ) -> None:
        super().__init__(coordinator, source_id)
        self._channel_id = channel_id
        self._attr_unique_id = f"channel_{channel_id}"
        channel = self.channel
        if channel is not None:
            self._attr_name = channel.name
            self._attr_device_class = channel.kind.device_class
            self._attr_native_unit_of_measurement = channel.kind.unit

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
    def native_value(self) -> float | None:
        channel = self.channel
        return channel.last_value if channel else None

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        channel = self.channel
        if channel is None:
            return None
        return {
            "monthly_diff": channel.monthly_diff,
            "monthly_limit": channel.monthly_limit,
            "consumption_since_reset": channel.consumption_since_reset,
            "factor": channel.factor,
            "serial": channel.serial,
            "counter_id": channel.counter_id,
            "number": channel.number,
            "service_date": channel.service_date,
            "info": channel.info,
        }


class WateriusDiagnosticSensor(WateriusDeviceEntity, SensorEntity):
    """Диагностический показатель прибора."""

    entity_description: WateriusDiagnosticDescription

    def __init__(
        self,
        coordinator: WateriusCoordinator,
        source_id: int,
        description: WateriusDiagnosticDescription,
    ) -> None:
        super().__init__(coordinator, source_id)
        self.entity_description = description
        self._attr_unique_id = f"device_{source_id}_{description.key}"

    @property
    def native_value(self) -> float | int | datetime | None:
        device = self.device
        if device is None:
            return None
        return self.entity_description.value_fn(device)
