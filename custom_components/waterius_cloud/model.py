"""Parsing of the Waterius cloud payloads.

Этот модуль сознательно не импортирует Home Assistant: он должен разбираться и
тестироваться сам по себе. Строковые значения device_class и единиц совпадают
со значениями констант Home Assistant, и это проверяется тестом.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
