"""Tests for the Home-Assistant-free parsing layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "waterius_cloud"))

import model  # noqa: E402


@pytest.mark.parametrize(
    ("data_type", "device_class", "unit"),
    [
        (0, "water", "m³"),
        (1, "water", "m³"),
        (2, "energy", "kWh"),
        (3, "gas", "m³"),
        (4, "energy", "Gcal"),
        (5, "energy", "kWh"),
        (6, "energy", "kWh"),
        (7, "energy", "kWh"),
        (8, "energy", "kWh"),
        (9, "water", "m³"),
        (10, None, None),
        (11, "energy", "kWh"),
        (12, "energy", "kWh"),
        (13, "water", "m³"),
        (14, "energy", "GJ"),
        (15, "water", "m³"),
    ],
)
def test_every_data_type_maps_to_a_kind(data_type, device_class, unit):
    kind = model.DATA_TYPES[data_type]
    assert kind.device_class == device_class
    assert kind.unit == unit


def test_every_data_type_has_a_name():
    assert set(model.DATA_TYPE_NAMES) == set(model.DATA_TYPES)
    assert model.DATA_TYPE_NAMES[1] == "Горячая вода"


def test_unknown_data_type_falls_back_to_other():
    kind = model.kind_for_data_type(999)
    assert kind.device_class is None
    assert kind.unit is None
