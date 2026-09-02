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


import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sources_payload():
    return json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))["results"]


def test_parse_sources_builds_device_index(sources_payload):
    devices = model.parse_sources(sources_payload)

    assert list(devices) == [35488]
    device = devices[35488]
    assert device.name == "Тестовый прибор"
    assert device.battery == 88
    assert device.voltage == 3.144
    assert device.period_min == 1440
    assert device.can_refresh is False
    assert device.outdated is False
    assert device.mac == "00:00:00:00:00:01"
    assert device.sw_version == "1.1.20-32"
    assert device.last_wakeup == datetime(2026, 9, 1, 15, 10, 5, 319271, tzinfo=timezone.utc)


def test_parse_sources_builds_channel_index(sources_payload):
    device = model.parse_sources(sources_payload)[35488]

    assert list(device.channels) == [69838, 69839, 69840]
    hot = device.channels[69838]
    assert hot.name == "Горячая вода"
    assert hot.last_value == 0.52
    assert hot.kind.device_class == "water"
    assert hot.kind.unit == "m³"
    assert hot.monthly_limit == 25.0
    assert hot.factor == 10
    assert hot.source_id == 35488
    assert hot.has_problem is False
    assert hot.manual_last_value is True

    cold = device.channels[69839]
    assert cold.manual_last_value is False


def test_channel_with_warnings_reports_a_problem(sources_payload):
    device = model.parse_sources(sources_payload)[35488]
    broken = device.channels[69840]

    assert broken.has_problem is True
    assert broken.warnings == ["Счётчик не передаёт импульсы"]
    assert broken.last_value is None
    assert broken.kind.device_class is None


def test_parse_survives_missing_fields():
    devices = model.parse_sources([{"id": 7}])

    device = devices[7]
    assert device.name == "Ватериус 7"
    assert device.channels == {}
    assert device.battery is None
    assert device.last_wakeup is None
    assert device.sw_version is None
    assert device.period_min == 1440


def test_device_is_online_while_the_cloud_says_so(sources_payload):
    device = model.parse_sources(sources_payload)[35488]
    now = device.last_wakeup + timedelta(days=1)

    assert model.is_offline(device, now) is False


def test_device_is_offline_after_two_and_a_half_periods(sources_payload):
    device = model.parse_sources(sources_payload)[35488]
    now = device.last_wakeup + timedelta(minutes=1440 * 2.5 + 1)

    assert model.is_offline(device, now) is True


def test_outdated_flag_alone_marks_the_device_offline(sources_payload):
    payload = sources_payload
    payload[0]["outdated"] = True
    device = model.parse_sources(payload)[35488]
    now = device.last_wakeup + timedelta(minutes=1)

    assert model.is_offline(device, now) is True


def test_device_without_last_wakeup_is_offline():
    device = model.parse_sources([{"id": 7}])[7]

    assert model.is_offline(device, datetime.now(timezone.utc)) is True


def test_last_wakeup_without_an_offset_is_treated_as_utc():
    device = model.parse_sources(
        [{"id": 7, "last_wakeup": "2026-09-01T15:10:05"}]
    )[7]

    assert device.last_wakeup == datetime(2026, 9, 1, 15, 10, 5, tzinfo=timezone.utc)
    # Раньше сравнение aware ``now`` с naive ``last_wakeup`` роняло TypeError.
    assert model.is_offline(device, datetime.now(timezone.utc)) is False
