"""Parsing of the Waterius cloud payloads.

Этот модуль сознательно не импортирует Home Assistant: он должен разбираться и
тестироваться сам по себе. Строковые значения device_class и единиц совпадают
со значениями констант Home Assistant, и это проверяется тестом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

DEVICE_CLASS_WATER = "water"
DEVICE_CLASS_GAS = "gas"
DEVICE_CLASS_ENERGY = "energy"

UNIT_CUBIC_METERS = "m³"
UNIT_KILOWATT_HOUR = "kWh"
UNIT_GIGACALORIE = "Gcal"
UNIT_GIGAJOULE = "GJ"


@dataclass(frozen=True, slots=True)
class ChannelKind:
    """Как показания канала выглядят для Home Assistant."""

    device_class: str | None
    unit: str | None


_WATER = ChannelKind(DEVICE_CLASS_WATER, UNIT_CUBIC_METERS)
_GAS = ChannelKind(DEVICE_CLASS_GAS, UNIT_CUBIC_METERS)
_ELECTRICITY = ChannelKind(DEVICE_CLASS_ENERGY, UNIT_KILOWATT_HOUR)
_HEAT_GCAL = ChannelKind(DEVICE_CLASS_ENERGY, UNIT_GIGACALORIE)
_HEAT_GJ = ChannelKind(DEVICE_CLASS_ENERGY, UNIT_GIGAJOULE)

# Тип 10 «Другой» остаётся без device_class и единицы: что в нём считают —
# неизвестно, а неверная единица испортит долгосрочную статистику.
_OTHER = ChannelKind(None, None)

DATA_TYPES: dict[int, ChannelKind] = {
    0: _WATER,
    1: _WATER,
    2: _ELECTRICITY,
    3: _GAS,
    4: _HEAT_GCAL,
    5: _ELECTRICITY,
    6: _ELECTRICITY,
    7: _ELECTRICITY,
    8: _ELECTRICITY,
    9: _WATER,
    10: _OTHER,
    11: _ELECTRICITY,
    12: _ELECTRICITY,
    13: _WATER,
    14: _HEAT_GJ,
    15: _WATER,
}

# Из GET /api/catalog/datatypes/, снято 2026-09-02. Справочник статический,
# запрашивать его на каждом цикле опроса незачем.
DATA_TYPE_NAMES: dict[int, str] = {
    0: "Холодная вода",
    1: "Горячая вода",
    2: "Электричество",
    3: "Газ",
    4: "Отопление (ГКал)",
    5: "Электричество (День)",
    6: "Электричество (Ночь)",
    7: "Электричество (Пик)",
    8: "Электричество (Полупик)",
    9: "Питьевая вода",
    10: "Другой",
    11: "Электричество (всего)",
    12: "Отопление (КВт)",
    13: "Водоотведение",
    14: "Отопление (ГДж)",
    15: "Горячая вода (недогретая)",
}


def kind_for_data_type(data_type: int) -> ChannelKind:
    """Вернуть вид канала; незнакомый тип трактуется как «Другой»."""
    return DATA_TYPES.get(data_type, _OTHER)


def name_for_data_type(data_type: int) -> str:
    """Вернуть человекочитаемое имя типа."""
    return DATA_TYPE_NAMES.get(data_type, f"Канал {data_type}")


DEFAULT_PERIOD_MIN = 1440

# Прибор просыпается раз в ``period_min``. Дублируется в const.py как
# OFFLINE_PERIOD_FACTOR; здесь своя копия, чтобы модуль не зависел от const.py,
# который тянет доменные настройки.
_OFFLINE_PERIOD_FACTOR = 2.5


@dataclass(frozen=True, slots=True)
class WateriusChannel:
    """Один вход прибора — счётчик."""

    id: int
    source_id: int
    data_type: int
    number: int
    last_value: float | None
    is_work: bool
    warnings: list[str] = field(default_factory=list)
    monthly_diff: float | None = None
    monthly_limit: float | None = None
    consumption_since_reset: float | None = None
    factor: int | None = None
    serial: str = ""
    counter_id: str = ""
    service_date: str | None = None
    info: str = ""

    @property
    def name(self) -> str:
        return name_for_data_type(self.data_type)

    @property
    def kind(self) -> ChannelKind:
        return kind_for_data_type(self.data_type)

    @property
    def has_problem(self) -> bool:
        return not self.is_work or bool(self.warnings)


@dataclass(frozen=True, slots=True)
class WateriusDevice:
    """Прибор Ватериус (в терминах API — source)."""

    id: int
    name: str
    place: str = ""
    last_wakeup: datetime | None = None
    period_min: int = DEFAULT_PERIOD_MIN
    outdated: bool = False
    can_refresh: bool = False
    battery: int | None = None
    voltage: float | None = None
    version_esp: str = ""
    version: int | None = None
    mac: str = ""
    warnings: list[str] = field(default_factory=list)
    channels: dict[int, WateriusChannel] = field(default_factory=dict)

    @property
    def sw_version(self) -> str | None:
        if not self.version_esp:
            return None
        if self.version is None:
            return self.version_esp
        return f"{self.version_esp}-{self.version}"


def _parse_timestamp(raw: str | None) -> datetime | None:
    """Разобрать метку времени API. Хвост ``Z`` datetime.fromisoformat до 3.11 не понимал."""
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Метка без смещения — считаем её UTC, иначе сравнение с aware-datetime
        # в is_offline() и сенсор TIMESTAMP падают с исключением.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_channel(raw: dict, source_id: int) -> WateriusChannel:
    return WateriusChannel(
        id=int(raw["id"]),
        source_id=source_id,
        data_type=int(raw.get("data_type") or 0),
        number=int(raw.get("number") or 0),
        last_value=raw.get("last_value"),
        is_work=bool(raw.get("is_work", True)),
        warnings=list(raw.get("warnings") or []),
        monthly_diff=raw.get("monthly_diff"),
        monthly_limit=raw.get("monthly_limit"),
        consumption_since_reset=raw.get("consumption_since_reset"),
        factor=raw.get("factor"),
        serial=raw.get("serial") or "",
        counter_id=raw.get("counter_id") or "",
        service_date=raw.get("service_date"),
        info=raw.get("info") or "",
    )


def _parse_device(raw: dict) -> WateriusDevice:
    source_id = int(raw["id"])
    channels = [_parse_channel(item, source_id) for item in raw.get("channels") or []]
    return WateriusDevice(
        id=source_id,
        name=raw.get("name") or raw.get("place") or f"Ватериус {source_id}",
        place=raw.get("place") or "",
        last_wakeup=_parse_timestamp(raw.get("last_wakeup")),
        period_min=int(raw.get("period_min") or DEFAULT_PERIOD_MIN),
        outdated=bool(raw.get("outdated", False)),
        can_refresh=bool(raw.get("can_refresh", False)),
        battery=raw.get("battery"),
        voltage=raw.get("voltage"),
        version_esp=raw.get("version_esp") or "",
        version=raw.get("version"),
        mac=raw.get("mac") or "",
        warnings=list(raw.get("warnings") or []),
        channels={channel.id: channel for channel in channels},
    )


def parse_sources(payload: list[dict]) -> dict[int, WateriusDevice]:
    """Разобрать список ``results`` из GET /api/source/ в индекс по id прибора."""
    devices = [_parse_device(raw) for raw in payload]
    return {device.id: device for device in devices}


def is_offline(device: WateriusDevice, now: datetime) -> bool:
    """Считается ли прибор потерявшим связь.

    Основной источник истины — флаг ``outdated`` облака. Собственный расчёт по
    ``last_wakeup`` нужен на случай, если облако флаг не выставит.
    """
    if device.outdated:
        return True
    if device.last_wakeup is None:
        return True
    deadline = device.last_wakeup + timedelta(
        minutes=device.period_min * _OFFLINE_PERIOD_FACTOR
    )
    return now > deadline
