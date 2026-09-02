"""model.py не импортирует Home Assistant, поэтому строки в нём надо сверять с HA явно."""

from __future__ import annotations

import sys
from pathlib import Path

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfEnergy, UnitOfVolume

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "waterius_cloud"))

import model  # noqa: E402


def test_device_class_strings_match_home_assistant():
    assert model.DEVICE_CLASS_WATER == SensorDeviceClass.WATER
    assert model.DEVICE_CLASS_GAS == SensorDeviceClass.GAS
    assert model.DEVICE_CLASS_ENERGY == SensorDeviceClass.ENERGY


def test_unit_strings_match_home_assistant():
    assert model.UNIT_CUBIC_METERS == UnitOfVolume.CUBIC_METERS
    assert model.UNIT_KILOWATT_HOUR == UnitOfEnergy.KILO_WATT_HOUR
    assert model.UNIT_GIGACALORIE == UnitOfEnergy.GIGA_CALORIE
    assert model.UNIT_GIGAJOULE == UnitOfEnergy.GIGA_JOULE
