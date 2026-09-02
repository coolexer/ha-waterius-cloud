# Waterius Cloud Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HACS-интеграция `waterius_cloud`, которая по API личного кабинета `account.waterius.ru` читает показания счётчиков и публикует их сущностями Home Assistant.

**Architecture:** Один config entry = один аккаунт Waterius. Единственный `DataUpdateCoordinator` раз в час дёргает `GET /api/source/` (с пагинацией) и раскладывает ответ в индекс `{source_id: WateriusDevice}` с вложенными каналами. Каждый `source` — устройство HA, каждый `channel` — сенсор показания и binary_sensor проблемы. Слой разбора JSON (`model.py`) не импортирует Home Assistant и тестируется в отрыве от него.

**Tech Stack:** Python 3.12+, Home Assistant 2025.3+, `aiohttp`, `pytest`, `pytest-homeassistant-custom-component`, `aioresponses`.

**Спека:** `docs/superpowers/specs/2026-09-02-waterius-cloud-design.md`

---

## Структура файлов

Корень: рабочий каталог репозитория. Все пути ниже — относительно него.

| Файл | Ответственность |
|---|---|
| `custom_components/waterius_cloud/const.py` | Константы конфигурации: домен, базовый URL, интервалы, таймаут |
| `custom_components/waterius_cloud/model.py` | Датаклассы `WateriusDevice`/`WateriusChannel`, таблица `data_type`, `parse_sources()`, `is_offline()`. Без импортов Home Assistant |
| `custom_components/waterius_cloud/api.py` | HTTP-клиент и исключения. Без импортов Home Assistant |
| `custom_components/waterius_cloud/coordinator.py` | `WateriusCoordinator`, тип `WateriusConfigEntry` |
| `custom_components/waterius_cloud/entity.py` | База `WateriusDeviceEntity` (device_info, доступность) и хелпер динамического добавления сущностей |
| `custom_components/waterius_cloud/config_flow.py` | Шаги `user`, `reauth`, options flow |
| `custom_components/waterius_cloud/__init__.py` | `async_setup_entry` / `async_unload_entry` |
| `custom_components/waterius_cloud/sensor.py` | Сенсор показания канала + три диагностических сенсора прибора |
| `custom_components/waterius_cloud/binary_sensor.py` | `problem` на канал, `connectivity` на прибор |
| `custom_components/waterius_cloud/button.py` | Кнопка «Обновить сейчас» |
| `custom_components/waterius_cloud/strings.json`, `translations/{en,ru}.json` | Тексты config flow и имена сущностей |
| `custom_components/waterius_cloud/manifest.json`, `hacs.json` | Метаданные интеграции и HACS |
| `tests/fixtures/sources.json` | Обезличенный реальный ответ `/api/source/` + синтетические каналы всех 16 типов |
| `tests/test_model.py`, `tests/test_api.py`, `tests/test_ha_constants.py` | Тесты слоёв, не зависящих от Home Assistant |

## Решение по тестам, принятое при исполнении (2026-09-02)

`pytest-homeassistant-custom-component` не работает на Windows: он автоматически подгружается
в любой запуск pytest и импортирует `homeassistant.runner`, который делает `import fcntl` —
модуль, которого на Windows нет. WSL на машине есть, но без `pip` и `python3-venv`, а `sudo`
требует пароль.

Владелец проекта решил не заводить тестовое окружение с Home Assistant. Следствия:

- Тестами покрыты `model.py` и `api.py` — то есть весь разбор данных и весь HTTP.
- Config flow и платформы сущностей тестами **не** покрыты. Их корректность проверяется
  вручную на живом Home Assistant в Task 16, и поэтому Task 16 обязательна, а не факультативна.
- `pytest-homeassistant-custom-component` из `requirements_test.txt` убирается — без него
  `pytest` работает на Windows без дополнительных флагов.
- `homeassistant` в зависимостях остаётся: он нужен `tests/test_ha_constants.py`, который
  сверяет строковые литералы из `model.py` с константами Home Assistant.

`entity.py` в спеке отдельно не назван — он появляется здесь, потому что device_info, проверка доступности и логика динамического добавления одинаковы для трёх платформ, и дублировать их трижды было бы хуже.

---

### Task 1: Каркас репозитория

**Files:**
- Create: `.gitignore`, `LICENSE`, `hacs.json`, `requirements_test.txt`, `pytest.ini`
- Create: `custom_components/waterius_cloud/manifest.json`, `custom_components/waterius_cloud/const.py`

- [ ] **Step 1: Инициализировать git**

```bash
cd <корень репозитория>
git init -b main
```

- [ ] **Step 2: Создать `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.coverage
htmlcov/
```

- [ ] **Step 3: Создать `LICENSE`**

Взять текст лицензии MIT из соседнего проекта — он уже оформлен на того же владельца:

```bash
cp ../ha-razliv-snt/LICENSE ./LICENSE
```

- [ ] **Step 4: Создать `hacs.json`**

```json
{
  "name": "Ватериус (Личный кабинет)",
  "render_readme": true,
  "homeassistant": "2025.3.0"
}
```

- [ ] **Step 5: Создать `custom_components/waterius_cloud/manifest.json`**

Требований нет намеренно: клиент написан на `aiohttp`, который уже есть в Home Assistant.

```json
{
  "domain": "waterius_cloud",
  "name": "Ватериус (Личный кабинет)",
  "codeowners": ["@coolexer"],
  "config_flow": true,
  "documentation": "https://github.com/coolexer/ha-waterius-cloud",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/coolexer/ha-waterius-cloud/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 6: Создать `custom_components/waterius_cloud/const.py`**

```python
"""Constants for the Waterius Cloud integration."""

from __future__ import annotations

DOMAIN = "waterius_cloud"

DEFAULT_BASE_URL = "https://account.waterius.ru"

CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
DEFAULT_SCAN_INTERVAL_MINUTES = 60
MIN_SCAN_INTERVAL_MINUTES = 15

MANUFACTURER = "Waterius"

# Таймаут запроса живёт в api.py, а порог «прибор офлайн» — в model.py:
# оба модуля не импортируют Home Assistant и не должны зависеть от этого файла.
```

- [ ] **Step 7: Создать `requirements_test.txt`**

```
pytest>=8.0
pytest-asyncio>=0.24
pytest-homeassistant-custom-component>=0.13.190
aioresponses>=0.7.6
homeassistant>=2025.3.0
```

- [ ] **Step 8: Создать `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 9: Установить зависимости**

Run: `pip install -r requirements_test.txt`
Expected: установка завершается без ошибок.

- [ ] **Step 10: Commit**

```bash
git add .gitignore LICENSE hacs.json pytest.ini requirements_test.txt custom_components/waterius_cloud/manifest.json custom_components/waterius_cloud/const.py docs
git commit -m "chore: scaffold waterius_cloud integration"
```

---

### Task 2: Таблица типов ресурсов

**Files:**
- Create: `custom_components/waterius_cloud/model.py`
- Test: `tests/test_model.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/test_model.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'model'`

- [ ] **Step 3: Создать `custom_components/waterius_cloud/model.py`**

Модуль намеренно не импортирует Home Assistant: строки device_class и единиц совпадают со
значениями констант HA, а совпадение проверяется отдельным тестом в Task 4.

```python
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
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_model.py -v`
Expected: PASS, 18 тестов

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/model.py tests/test_model.py
git commit -m "feat: map Waterius data_type values to device classes and units"
```

---

### Task 3: Разбор ответа `/api/source/`

**Files:**
- Modify: `custom_components/waterius_cloud/model.py`
- Create: `tests/fixtures/sources.json`
- Modify: `tests/test_model.py`

- [ ] **Step 1: Создать фикстуру `tests/fixtures/sources.json`**

Это реальный ответ аккаунта, снятый 2026-09-02, с обезличенными `mac`, `local_ip`, `esp_id`,
`key`, `place`. К нему добавлен третий канал типа 10 («Другой») с `is_work: false` и
предупреждением — чтобы в тестах был случай проблемного канала и канала без единицы.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 35488,
      "name": "Тестовый прибор",
      "source_type": 1,
      "key": "0000",
      "last_wakeup": "2026-09-01T15:10:05.319271Z",
      "version": 32,
      "version_esp": "1.1.20",
      "mac": "00:00:00:00:00:01",
      "voltage": 3.144,
      "voltage_low": false,
      "voltage_diff": 0.008,
      "battery": 88,
      "local_ip": "192.168.0.2",
      "esp_id": 1,
      "freemem": 39800,
      "place": "Тест",
      "model": 0,
      "period_min": 1440,
      "outdated": false,
      "warnings": [],
      "can_refresh": false,
      "channels": [
        {
          "id": 69838,
          "data_type": 1,
          "serial": "",
          "number": 0,
          "source": 35488,
          "service_date": "2024-06-01",
          "monthly_diff": 0.0,
          "last_value": 0.52,
          "is_work": true,
          "warnings": [],
          "info": "0.52 м³",
          "manual_last_value": false,
          "monthly_limit": 25.0,
          "factor": 10,
          "counter_id": "",
          "consumption_since_reset": 0.52
        },
        {
          "id": 69839,
          "data_type": 0,
          "serial": "",
          "number": 1,
          "source": 35488,
          "service_date": "2024-06-01",
          "monthly_diff": 0.0,
          "last_value": 0.66,
          "is_work": true,
          "warnings": [],
          "info": "0.66 м³",
          "manual_last_value": false,
          "monthly_limit": 50.0,
          "factor": 10,
          "counter_id": "",
          "consumption_since_reset": 0.66
        },
        {
          "id": 69840,
          "data_type": 10,
          "serial": "",
          "number": 2,
          "source": 35488,
          "service_date": null,
          "monthly_diff": null,
          "last_value": null,
          "is_work": false,
          "warnings": ["Счётчик не передаёт импульсы"],
          "info": "",
          "manual_last_value": false,
          "monthly_limit": null,
          "factor": null,
          "counter_id": "",
          "consumption_since_reset": null
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Написать падающие тесты**

Дописать в конец `tests/test_model.py`:

```python
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
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `pytest tests/test_model.py -v`
Expected: FAIL — `AttributeError: module 'model' has no attribute 'parse_sources'`

- [ ] **Step 4: Дописать разбор в `model.py`**

Добавить в конец файла:

```python
from datetime import datetime, timedelta  # noqa: E402  (в начало файла при оформлении)

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
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


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
```

При оформлении файла перенести `from datetime import datetime, timedelta` к остальным импортам
наверх, а не оставлять посреди модуля.

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `pytest tests/test_model.py -v`
Expected: PASS, все тесты

- [ ] **Step 6: Commit**

```bash
git add custom_components/waterius_cloud/model.py tests/test_model.py tests/fixtures/sources.json
git commit -m "feat: parse /api/source/ payloads into device and channel models"
```

---

### Task 4: Сверка строковых констант с Home Assistant

Задача ловит расхождение между литералами в `model.py` и константами Home Assistant —
единственную цену того, что `model.py` не импортирует HA.

**Files:**
- Create: `tests/test_ha_constants.py`

- [ ] **Step 1: Написать тест**

```python
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
```

- [ ] **Step 2: Запустить тест**

Run: `pytest tests/test_ha_constants.py -v`
Expected: PASS. Если падает на `UnitOfEnergy.GIGA_CALORIE` или `GIGA_JOULE` —
установленная версия Home Assistant старше, чем нужно; поднять `homeassistant` в
`requirements_test.txt` и `homeassistant` в `hacs.json` до версии, где эти единицы есть,
и записать это в README.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ha_constants.py
git commit -m "test: pin model string constants to Home Assistant values"
```

---

### Task 5: HTTP-клиент — чтение

**Files:**
- Create: `custom_components/waterius_cloud/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Написать падающие тесты**

```python
"""Tests for the Waterius cloud HTTP client."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import aiohttp
import pytest
from aioresponses import aioresponses

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "waterius_cloud"))

import api  # noqa: E402

BASE = "https://account.waterius.ru"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client:
        yield client


async def test_get_user_returns_payload(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", payload={"user": 13382, "email": "a@b.ru"})
        client = api.WateriusApi(session, "tok")

        assert await client.get_user() == {"user": 13382, "email": "a@b.ru"}


async def test_get_user_sends_the_token(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", payload={"user": 1})
        client = api.WateriusApi(session, "tok")
        await client.get_user()

        request = next(iter(mocked.requests.values()))[0]
        assert request.kwargs["headers"]["Authorization"] == "Token tok"


async def test_get_sources_follows_pagination(session):
    with aioresponses() as mocked:
        mocked.get(
            f"{BASE}/api/source/?page=1",
            payload={"next": f"{BASE}/api/source/?page=2", "results": [{"id": 1}]},
        )
        mocked.get(
            f"{BASE}/api/source/?page=2",
            payload={"next": None, "results": [{"id": 2}]},
        )
        client = api.WateriusApi(session, "tok")

        assert await client.get_sources() == [{"id": 1}, {"id": 2}]


async def test_real_payload_round_trips(session):
    body = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/source/?page=1", payload=body)
        client = api.WateriusApi(session, "tok")

        sources = await client.get_sources()

        assert len(sources) == 1
        assert sources[0]["id"] == 35488


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors_raise_auth_error(session, status):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", status=status, payload={"detail": "нет"})
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusAuthError):
            await client.get_user()


async def test_server_error_raises_connection_error(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", status=500)
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusConnectionError):
            await client.get_user()


async def test_network_failure_raises_connection_error(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/user/", exception=aiohttp.ClientError("boom"))
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusConnectionError):
            await client.get_user()
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Создать `custom_components/waterius_cloud/api.py`**

```python
"""HTTP client for the Waterius personal cabinet API.

Модуль не импортирует Home Assistant: он получает готовую ``aiohttp.ClientSession``
и поднимает собственные исключения, которые координатор переводит в исключения HA.

Авторизация — постоянный токен DRF (``Authorization: Token <key>``). Логин по
паролю здесь не реализован намеренно: ``POST /dj-rest-auth/login/`` защищён
Google reCAPTCHA, пройти её из кода нельзя. Токен добывается пользователем
вручную один раз, см. README.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://account.waterius.ru"
REQUEST_TIMEOUT = 30


class WateriusError(Exception):
    """Базовая ошибка обращения к облаку Ватериус."""


class WateriusAuthError(WateriusError):
    """Токен не принят."""


class WateriusConnectionError(WateriusError):
    """Облако недоступно или ответило ошибкой сервера."""


class WateriusRateLimitError(WateriusError):
    """Слишком частые запросы (HTTP 429)."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class WateriusApi:
    """Тонкий клиент над API личного кабинета."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._session = session
        self._token = token
        self._base_url = base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self._token}",
            "Accept": "application/json",
        }

    async def _request(self, method: str, url: str) -> Any:
        try:
            # ``async with`` освобождает соединение и на ветках с ошибкой, а
            # таймаут должен покрывать и чтение тела, не только заголовки.
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.request(method, url, headers=self._headers) as response,
            ):
                if response.status in (401, 403):
                    raise WateriusAuthError("Токен не принят личным кабинетом")
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise WateriusRateLimitError(
                        "Слишком частые запросы к облаку Ватериус",
                        int(retry_after) if retry_after and retry_after.isdigit() else None,
                    )
                if response.status >= 400:
                    raise WateriusConnectionError(
                        f"Облако Ватериус вернуло HTTP {response.status}"
                    )
                if response.status == 204 or not response.content_length:
                    text = await response.text()
                    if not text:
                        return None
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WateriusConnectionError(f"Ошибка соединения с облаком: {err}") from err

    async def get_user(self) -> dict:
        """Данные текущего пользователя. Используется как проверка токена."""
        return await self._request("GET", f"{self._base_url}/api/user/")

    async def get_sources(self) -> list[dict]:
        """Все приборы аккаунта вместе с вложенными каналами."""
        url = f"{self._base_url}/api/source/?page=1"
        sources: list[dict] = []
        while url:
            payload = await self._request("GET", url)
            sources.extend(payload.get("results") or [])
            url = payload.get("next")
        return sources
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/api.py tests/test_api.py
git commit -m "feat: add Waterius cloud HTTP client with token auth and pagination"
```

---

### Task 6: HTTP-клиент — принудительное обновление

**Files:**
- Modify: `custom_components/waterius_cloud/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/test_api.py`:

```python
async def test_refresh_source_posts_to_the_update_endpoint(session):
    with aioresponses() as mocked:
        mocked.get(f"{BASE}/api/source/35488/update", payload={})
        client = api.WateriusApi(session, "tok")

        await client.refresh_source(35488)


async def test_refresh_source_reports_the_cooldown(session):
    with aioresponses() as mocked:
        mocked.get(
            f"{BASE}/api/source/35488/update",
            status=429,
            headers={"Retry-After": "45"},
            payload={"message": "Подождите"},
        )
        client = api.WateriusApi(session, "tok")

        with pytest.raises(api.WateriusRateLimitError) as excinfo:
            await client.refresh_source(35488)

        assert excinfo.value.retry_after == 45
```

Метод в SPA вызывается как `GET .../update` (`refreshSource` в бандле кабинета), поэтому
и здесь GET, а не POST.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `pytest tests/test_api.py -k refresh -v`
Expected: FAIL — `AttributeError: 'WateriusApi' object has no attribute 'refresh_source'`

- [ ] **Step 3: Дописать метод в `api.py`**

```python
    async def refresh_source(self, source_id: int) -> None:
        """Попросить облако обновить данные прибора.

        Кабинет дёргает этот эндпоинт методом GET и ограничивает частоту:
        повторный вызов раньше кулдауна возвращает 429.
        """
        await self._request("GET", f"{self._base_url}/api/source/{source_id}/update")
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/api.py tests/test_api.py
git commit -m "feat: add source refresh request with rate-limit handling"
```

---

### Task 7: Координатор и точка входа

**Files:**
- Create: `custom_components/waterius_cloud/coordinator.py`
- Create: `custom_components/waterius_cloud/__init__.py`

- [ ] **Step 1: Создать `coordinator.py`**

```python
"""Data update coordinator for the Waterius Cloud integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    WateriusApi,
    WateriusAuthError,
    WateriusConnectionError,
    WateriusRateLimitError,
)
from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .model import WateriusDevice, parse_sources

_LOGGER = logging.getLogger(__name__)

type WateriusConfigEntry = ConfigEntry["WateriusCoordinator"]


class WateriusCoordinator(DataUpdateCoordinator[dict[int, WateriusDevice]]):
    """Опрашивает /api/source/ и раскладывает ответ в индекс по id прибора."""

    def __init__(self, hass: HomeAssistant, entry: WateriusConfigEntry) -> None:
        minutes = entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.entry = entry
        self.api = WateriusApi(
            async_get_clientsession(hass), entry.data[CONF_TOKEN], DEFAULT_BASE_URL
        )

    async def _async_update_data(self) -> dict[int, WateriusDevice]:
        try:
            sources = await self.api.get_sources()
        except WateriusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (WateriusRateLimitError, WateriusConnectionError) as err:
            raise UpdateFailed(str(err)) from err

        return parse_sources(sources)
```

- [ ] **Step 2: Создать `__init__.py`**

```python
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
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: WateriusConfigEntry) -> None:
    """Reload the entry when the scan interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 3: Проверить, что модули импортируются**

Run: `python -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('custom_components/waterius_cloud').glob('*.py')]"`
Expected: без вывода и без ошибок (синтаксис в порядке; полноценная проверка — в Task 9).

- [ ] **Step 4: Commit**

```bash
git add custom_components/waterius_cloud/coordinator.py custom_components/waterius_cloud/__init__.py
git commit -m "feat: add update coordinator and entry setup"
```

---

### Task 8: Config flow — добавление аккаунта

> **Отменено при исполнении:** Steps 1–3 и Step 5 (создание `tests/conftest.py`,
> `tests/test_config_flow.py` и их прогон) не выполняются — см. «Решение по тестам».
> Выполняются только Step 4 (создать `config_flow.py`) и Step 6 (коммит).
> Тестовый код в Steps 1–2 оставлен в документе как описание ожидаемого поведения:
> из него видно, какие `unique_id`, заголовок записи и коды ошибок должен давать flow.

**Files:**
- Create: `custom_components/waterius_cloud/config_flow.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Создать `tests/conftest.py`**

```python
"""Test bootstrap for the Home-Assistant-dependent tests."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Разрешить Home Assistant загружать custom_components из этого репозитория."""
    yield
```

- [ ] **Step 2: Написать падающие тесты**

Создать `tests/test_config_flow.py`:

```python
"""Tests for the Waterius Cloud config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterius_cloud.api import (
    WateriusAuthError,
    WateriusConnectionError,
)
from custom_components.waterius_cloud.const import DOMAIN

USER_PAYLOAD = {"user": 13382, "email": "user@example.com"}


def _patch_get_user(**kwargs):
    return patch(
        "custom_components.waterius_cloud.config_flow.WateriusApi.get_user", **kwargs
    )


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with (
        _patch_get_user(return_value=USER_PAYLOAD),
        patch("custom_components.waterius_cloud.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "good-token"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "user@example.com"
    assert result["data"] == {CONF_TOKEN: "good-token"}
    assert result["result"].unique_id == "13382"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (WateriusAuthError("нет"), "invalid_auth"),
        (WateriusConnectionError("нет"), "cannot_connect"),
    ],
)
async def test_user_flow_reports_errors(hass: HomeAssistant, error, reason) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with _patch_get_user(side_effect=error):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "bad-token"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}


async def test_user_flow_recovers_after_an_error(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with _patch_get_user(side_effect=WateriusAuthError("нет")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "bad-token"}
        )

    with (
        _patch_get_user(return_value=USER_PAYLOAD),
        patch("custom_components.waterius_cloud.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "good-token"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_same_account_cannot_be_added_twice(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "old"}
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with _patch_get_user(return_value=USER_PAYLOAD):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "new"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.waterius_cloud.config_flow'`

- [ ] **Step 4: Создать `config_flow.py`**

```python
"""Config flow for the Ватериус (Личный кабинет) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    WateriusApi,
    WateriusAuthError,
    WateriusConnectionError,
    WateriusError,
)
from .const import DEFAULT_BASE_URL, DOMAIN

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})


class WateriusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ввод токена личного кабинета."""

    VERSION = 1

    async def _async_validate_token(self, token: str) -> dict:
        """Проверить токен и вернуть данные пользователя."""
        api = WateriusApi(
            async_get_clientsession(self.hass), token, DEFAULT_BASE_URL
        )
        return await api.get_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Шаг добавления аккаунта."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                user = await self._async_validate_token(token)
            except WateriusAuthError:
                errors["base"] = "invalid_auth"
            except WateriusConnectionError:
                errors["base"] = "cannot_connect"
            except WateriusError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(user["user"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user.get("email") or f"Ватериус {user['user']}",
                    data={CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
```

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/waterius_cloud/config_flow.py tests/conftest.py tests/test_config_flow.py
git commit -m "feat: add config flow for entering the cabinet token"
```

---

### Task 9: Config flow — reauth и настройки

> **Отменено при исполнении:** Steps 1, 2 и 4 (тесты и их прогон) не выполняются.
> Выполняются Step 3 (дописать `config_flow.py`) и Step 5 (коммит).
> Тестовый код оставлен как описание ожидаемого поведения.

**Files:**
- Modify: `custom_components/waterius_cloud/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/test_config_flow.py`:

```python
from homeassistant.helpers import config_validation  # noqa: F401  (гарантирует загрузку helpers)

from custom_components.waterius_cloud.const import (  # noqa: E402
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)


async def test_reauth_updates_the_token(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "expired"}
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with (
        _patch_get_user(return_value=USER_PAYLOAD),
        patch("custom_components.waterius_cloud.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "fresh"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "fresh"


async def test_reauth_rejects_a_token_from_another_account(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "expired"}
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with _patch_get_user(return_value={"user": 999, "email": "other@example.com"}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "someone-elses"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_TOKEN] == "expired"


async def test_options_flow_sets_the_scan_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "tok"}
    )
    entry.add_to_hass(hass)

    with patch("custom_components.waterius_cloud.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL_MINUTES: 180}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL_MINUTES] == 180


async def test_options_flow_rejects_too_short_an_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "tok"}
    )
    entry.add_to_hass(hass)

    with patch("custom_components.waterius_cloud.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)

        with pytest.raises(Exception):
            await hass.config_entries.options.async_configure(
                result["flow_id"], {CONF_SCAN_INTERVAL_MINUTES: 1}
            )

    assert entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES) == (
        DEFAULT_SCAN_INTERVAL_MINUTES
    )
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `pytest tests/test_config_flow.py -k "reauth or options" -v`
Expected: FAIL — reauth-шаг и options flow не реализованы.

- [ ] **Step 3: Дописать `config_flow.py`**

Добавить импорты и код:

```python
from collections.abc import Mapping

from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)
```

Внутри `WateriusConfigFlow` добавить:

```python
    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Токен перестал работать — попросить новый."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ввод нового токена для уже добавленного аккаунта."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                user = await self._async_validate_token(token)
            except WateriusAuthError:
                errors["base"] = "invalid_auth"
            except WateriusConnectionError:
                errors["base"] = "cannot_connect"
            except WateriusError:
                errors["base"] = "unknown"
            else:
                if str(user["user"]) != entry.unique_id:
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> WateriusOptionsFlow:
        """Вернуть обработчик настроек."""
        return WateriusOptionsFlow()
```

И добавить класс настроек в конец файла:

```python
class WateriusOptionsFlow(OptionsFlow):
    """Настройка интервала опроса."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Единственный шаг настроек."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES, default=current
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=1440))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/config_flow.py tests/test_config_flow.py
git commit -m "feat: add reauth step and scan interval options"
```

---

### Task 10: База сущностей и динамическое добавление

**Files:**
- Create: `custom_components/waterius_cloud/entity.py`

- [ ] **Step 1: Создать `entity.py`**

```python
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
from .model import WateriusDevice


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
```

- [ ] **Step 2: Проверить синтаксис**

Run: `python -c "import ast; ast.parse(open('custom_components/waterius_cloud/entity.py', encoding='utf-8').read())"`
Expected: без вывода и без ошибок

- [ ] **Step 3: Commit**

```bash
git add custom_components/waterius_cloud/entity.py
git commit -m "feat: add entity base class and dynamic entity setup helper"
```

---

### Task 11: Сенсоры показаний и диагностики

> **Отменено при исполнении:** Steps 1, 2 и 4 (создание `tests/test_entities.py` и прогон)
> не выполняются. Выполняются Step 3 (создать `sensor.py`) и Step 5 (коммит).
> Ожидания из тестового кода переносятся в ручную проверку Task 16.

**Files:**
- Create: `custom_components/waterius_cloud/sensor.py`
- Create: `tests/test_entities.py`

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_entities.py`:

```python
"""End-to-end tests over a mocked cloud response."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.waterius_cloud.const import DOMAIN

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sources():
    return json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))["results"]


@pytest.fixture
async def setup_integration(hass: HomeAssistant, sources):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "tok"}, title="user@example.com"
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.waterius_cloud.coordinator.WateriusApi.get_sources",
        return_value=sources,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_channel_sensor_reports_the_reading(hass, setup_integration):
    state = hass.states.get("sensor.testovyi_pribor_goriachaia_voda")
    assert state is not None
    assert state.state == "0.52"
    assert state.attributes["device_class"] == "water"
    assert state.attributes["unit_of_measurement"] == "m³"
    assert state.attributes["state_class"] == "total_increasing"
    assert state.attributes["monthly_limit"] == 25.0
    assert state.attributes["factor"] == 10


async def test_channel_without_a_known_type_has_no_unit(hass, setup_integration):
    state = hass.states.get("sensor.testovyi_pribor_drugoi")
    assert state is not None
    assert "unit_of_measurement" not in state.attributes
    assert "device_class" not in state.attributes


async def test_device_diagnostics_sensors_exist(hass, setup_integration):
    battery = hass.states.get("sensor.testovyi_pribor_zariad_batarei")
    voltage = hass.states.get("sensor.testovyi_pribor_napriazhenie")
    wakeup = hass.states.get("sensor.testovyi_pribor_poslednii_vykhod_na_sviaz")

    assert battery.state == "88"
    assert voltage.state == "3.144"
    assert wakeup.state == "2026-09-01T15:10:05.319271+00:00"
```

Идентификаторы сущностей выводятся из имени прибора и имени сущности. Если фактические
`entity_id` окажутся другими, посмотреть реальные значения командой
`pytest tests/test_entities.py -v -s` с временной вставкой `print(hass.states.async_entity_ids())`
и поправить константы в тесте — но не подгонять код под красивые имена.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `pytest tests/test_entities.py -v`
Expected: FAIL — платформа `sensor` не найдена, сущности не созданы.

- [ ] **Step 3: Создать `sensor.py`**

```python
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
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_entities.py -v`
Expected: PASS. Если сущности не найдены — проверить `entity_id` по подсказке из Step 1.

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/sensor.py tests/test_entities.py
git commit -m "feat: publish channel readings and device diagnostics as sensors"
```

---

### Task 12: Бинарные сенсоры

> **Отменено при исполнении:** Steps 1, 2 и 4 (тесты и прогон) не выполняются.
> Выполняются Step 3 (создать `binary_sensor.py`) и Step 5 (коммит).
> Правка фикстуры со свежим `last_wakeup`, описанная в Step 1, не нужна:
> она требовалась только тестам.

**Files:**
- Create: `custom_components/waterius_cloud/binary_sensor.py`
- Modify: `tests/test_entities.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/test_entities.py`:

```python
async def test_broken_channel_reports_a_problem(hass, setup_integration):
    ok = hass.states.get("binary_sensor.testovyi_pribor_goriachaia_voda_problema")
    broken = hass.states.get("binary_sensor.testovyi_pribor_drugoi_problema")

    assert ok.state == "off"
    assert broken.state == "on"
    assert broken.attributes["warnings"] == ["Счётчик не передаёт импульсы"]


async def test_device_connectivity_follows_the_cloud_flag(hass, setup_integration):
    state = hass.states.get("binary_sensor.testovyi_pribor_sviaz")

    assert state.state == "on"
    assert state.attributes["device_class"] == "connectivity"
```

Метка времени в фикстуре — 2026-09-01, то есть в прошлом относительно любого запуска тестов
позже 2026-09-04, и расчётный порог офлайна сработает. Чтобы тест не начал падать со временем,
в фикстуре `setup_integration` дату надо подменять на свежую. Заменить фикстуру `sources` на:

```python
@pytest.fixture
def sources():
    from homeassistant.util import dt as dt_util

    payload = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))["results"]
    payload[0]["last_wakeup"] = dt_util.utcnow().isoformat().replace("+00:00", "Z")
    return payload
```

и в `test_device_diagnostics_sensors_exist` заменить проверку точного значения `wakeup.state` на:

```python
    assert wakeup.state not in ("unknown", "unavailable")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `pytest tests/test_entities.py -k "problem or connectivity" -v`
Expected: FAIL — сущности отсутствуют.

- [ ] **Step 3: Создать `binary_sensor.py`**

```python
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
from .entity import WateriusDeviceEntity, async_setup_dynamic_entities
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
        channel = self.channel
        if channel is not None:
            self._attr_name = f"{channel.name}: проблема"

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
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_entities.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/binary_sensor.py tests/test_entities.py
git commit -m "feat: add channel problem and device connectivity binary sensors"
```

---

### Task 13: Кнопка принудительного обновления

> **Отменено при исполнении:** Steps 1, 2 и 4 (тесты и прогон) не выполняются.
> Выполняются Step 3 (создать `button.py`) и Step 5 (коммит).

**Files:**
- Create: `custom_components/waterius_cloud/button.py`
- Modify: `tests/test_entities.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/test_entities.py`:

```python
from homeassistant.exceptions import HomeAssistantError  # noqa: E402

from custom_components.waterius_cloud.api import WateriusRateLimitError  # noqa: E402


async def test_refresh_button_is_unavailable_when_the_cloud_forbids_it(
    hass, setup_integration
):
    state = hass.states.get("button.testovyi_pribor_obnovit_seichas")

    assert state is not None
    assert state.state == "unavailable"


async def test_refresh_button_calls_the_api(hass, sources):
    sources[0]["can_refresh"] = True
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "tok"}, title="user@example.com"
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.waterius_cloud.coordinator.WateriusApi.get_sources",
        return_value=sources,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with patch(
            "custom_components.waterius_cloud.coordinator.WateriusApi.refresh_source"
        ) as refresh:
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.testovyi_pribor_obnovit_seichas"},
                blocking=True,
            )

        refresh.assert_called_once_with(35488)


async def test_refresh_button_surfaces_the_cooldown(hass, sources):
    sources[0]["can_refresh"] = True
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="13382", data={CONF_TOKEN: "tok"}, title="user@example.com"
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.waterius_cloud.coordinator.WateriusApi.get_sources",
        return_value=sources,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with (
            patch(
                "custom_components.waterius_cloud.coordinator.WateriusApi.refresh_source",
                side_effect=WateriusRateLimitError("подождите", retry_after=45),
            ),
            pytest.raises(HomeAssistantError),
        ):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.testovyi_pribor_obnovit_seichas"},
                blocking=True,
            )
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `pytest tests/test_entities.py -k button -v`
Expected: FAIL — сущность кнопки отсутствует.

- [ ] **Step 3: Создать `button.py`**

```python
"""Button platform for the Waterius Cloud integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import WateriusError, WateriusRateLimitError
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
        except WateriusRateLimitError as err:
            wait = f" Подождите {err.retry_after} с." if err.retry_after else ""
            raise HomeAssistantError(
                f"Облако Ватериус отклонило обновление.{wait}"
            ) from err
        except WateriusError as err:
            raise HomeAssistantError(f"Не удалось обновить прибор: {err}") from err

        await self.coordinator.async_request_refresh()
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `pytest tests/test_entities.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/button.py tests/test_entities.py
git commit -m "feat: add refresh button gated on can_refresh"
```

---

### Task 14: Тексты и переводы

**Files:**
- Create: `custom_components/waterius_cloud/strings.json`
- Create: `custom_components/waterius_cloud/translations/ru.json`
- Create: `custom_components/waterius_cloud/translations/en.json`

- [ ] **Step 1: Создать `strings.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Ватериус: личный кабинет",
        "description": "Введите токен доступа к account.waterius.ru. Как его получить — описано в README интеграции.",
        "data": { "token": "Токен" }
      },
      "reauth_confirm": {
        "title": "Токен Ватериус больше не работает",
        "description": "Получите новый токен и введите его. Токен сбрасывается, если выйти из личного кабинета в браузере.",
        "data": { "token": "Токен" }
      }
    },
    "error": {
      "invalid_auth": "Личный кабинет не принял токен",
      "cannot_connect": "Не удалось связаться с account.waterius.ru",
      "unknown": "Непредвиденная ошибка"
    },
    "abort": {
      "already_configured": "Этот аккаунт Ватериус уже добавлен",
      "reauth_successful": "Токен обновлён",
      "wrong_account": "Этот токен принадлежит другому аккаунту Ватериус"
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Настройки опроса",
        "data": { "scan_interval_minutes": "Интервал опроса, минут" },
        "data_description": {
          "scan_interval_minutes": "Прибор выходит на связь раз в сутки, опрашивать облако чаще раза в час смысла нет."
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "battery": { "name": "Заряд батареи" },
      "voltage": { "name": "Напряжение" },
      "last_wakeup": { "name": "Последний выход на связь" }
    },
    "binary_sensor": {
      "connectivity": { "name": "Связь" }
    },
    "button": {
      "refresh": { "name": "Обновить сейчас" }
    }
  }
}
```

- [ ] **Step 2: Создать `translations/ru.json`**

```bash
mkdir -p custom_components/waterius_cloud/translations
cp custom_components/waterius_cloud/strings.json custom_components/waterius_cloud/translations/ru.json
```

- [ ] **Step 3: Создать `translations/en.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Waterius cabinet",
        "description": "Enter an access token for account.waterius.ru. See the integration README for how to obtain one.",
        "data": { "token": "Token" }
      },
      "reauth_confirm": {
        "title": "The Waterius token stopped working",
        "description": "Obtain a new token and enter it. Signing out of the web cabinet resets the token.",
        "data": { "token": "Token" }
      }
    },
    "error": {
      "invalid_auth": "The cabinet rejected the token",
      "cannot_connect": "Cannot reach account.waterius.ru",
      "unknown": "Unexpected error"
    },
    "abort": {
      "already_configured": "This Waterius account is already configured",
      "reauth_successful": "Token updated",
      "wrong_account": "This token belongs to a different Waterius account"
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Polling settings",
        "data": { "scan_interval_minutes": "Scan interval, minutes" },
        "data_description": {
          "scan_interval_minutes": "The device wakes up once a day, so polling the cloud more often than hourly gains nothing."
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "battery": { "name": "Battery" },
      "voltage": { "name": "Voltage" },
      "last_wakeup": { "name": "Last seen" }
    },
    "binary_sensor": {
      "connectivity": { "name": "Connectivity" }
    },
    "button": {
      "refresh": { "name": "Refresh now" }
    }
  }
}
```

- [ ] **Step 4: Прогнать весь набор тестов**

Run: `pytest -v`
Expected: PASS. Имена диагностических сущностей теперь берутся из переводов — если
`entity_id` в `tests/test_entities.py` разошлись, поправить константы в тестах.

- [ ] **Step 5: Commit**

```bash
git add custom_components/waterius_cloud/strings.json custom_components/waterius_cloud/translations tests/test_entities.py
git commit -m "feat: add config flow strings and ru/en translations"
```

---

### Task 15: README и проверки репозитория

**Files:**
- Create: `README.md`
- Create: `.github/workflows/validate.yml`

- [ ] **Step 1: Создать `README.md`**

```markdown
# Ватериус (Личный кабинет) для Home Assistant

Читает показания счётчиков из личного кабинета [account.waterius.ru](https://account.waterius.ru)
и публикует их сущностями Home Assistant.

Интеграция нужна, когда прибор Ватериус стоит на объекте, недоступном из сети Home Assistant,
и штатные пути (MQTT или HTTP прямо с устройства) не годятся. Если прибор в одной сети с
Home Assistant — используйте штатную настройку прошивки, она лучше: данные приходят сразу,
без облака и без токенов.

## Что появляется в Home Assistant

Каждый прибор становится устройством, каждый счётчик — сенсором.

- Показание счётчика: `device_class` и единица подбираются по типу канала (вода, газ,
  электричество, отопление), `state_class: total_increasing` — годится для панели «Энергия»
  и долгосрочной статистики
- Проблема канала: счётчик не работает или облако сообщило предупреждение
- Заряд батареи, напряжение, время последнего выхода на связь
- Связь: прибор считается офлайн по флагу облака либо если он молчит дольше 2,5 своих периодов
- Кнопка «Обновить сейчас» — активна, только если облако разрешает будить прибор
  (у обычного Ватериуса на батарейках она будет неактивна, и это правильно)

## Установка

1. HACS → Интеграции → ⋮ → Пользовательские репозитории → добавить
   `https://github.com/coolexer/ha-waterius-cloud`, тип «Integration»
2. Установить «Ватериус (Личный кабинет)», перезапустить Home Assistant
3. Настройки → Устройства и службы → Добавить интеграцию → «Ватериус»

## Как получить токен

Личный кабинет защищает вход Google reCAPTCHA, поэтому интеграция не может залогиниться
по паролю — токен добывается один раз вручную.

1. Открыть `https://account.waterius.ru/login` в браузере
2. Открыть инструменты разработчика (F12), вкладку «Сеть» (Network)
3. Войти в кабинет обычным образом — почта и пароль
4. Найти в списке запрос `login/` (полный адрес `https://account.waterius.ru/dj-rest-auth/login/`)
5. Открыть его вкладку «Ответ» (Response) — там поле `key`. Это и есть токен
6. Вставить значение `key` в поле токена при добавлении интеграции

**Не нажимайте «Выход» в веб-кабинете** — это, скорее всего, отзовёт токен, и интеграция
попросит ввести новый. Просто закрывайте вкладку. Если токен всё же отвалился, Home Assistant
сам покажет «Требуется повторная аутентификация» — получите новый токен теми же шагами.

Токен даёт полный доступ к вашему аккаунту Ватериус. Он хранится в конфигурации Home Assistant.

## Чего интеграция не делает

- Не передаёт показания в управляющие компании и ничего не пишет в облако
- Не восстанавливает историю: облако отдаёт только текущее показание, архива в API нет,
  поэтому статистика начинается с момента установки

## Известное ограничение

Показание можно поправить в личном кабинете вручную, в том числе уменьшить.
`state_class: total_increasing` воспримет это как сброс счётчика и запишет в статистику
лишнее потребление за тот час. Лечится разово через «Разработчик → Статистика».

## Настройки

Интервал опроса меняется в настройках интеграции (по умолчанию 60 минут, минимум 15).
Прибор просыпается раз в сутки — чаще опрашивать облако бессмысленно.
```

- [ ] **Step 2: Создать `.github/workflows/validate.yml`**

```yaml
name: Validate

on:
  push:
  pull_request:
  schedule:
    - cron: "0 3 * * 1"

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration

  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements_test.txt
      - run: pytest -v
```

- [ ] **Step 3: Прогнать весь набор тестов**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add README.md .github/workflows/validate.yml
git commit -m "docs: add README with token instructions and CI validation"
```

---

### Task 16: Проверка на живом Home Assistant

Автотесты работают на фикстуре. Эта задача проверяет интеграцию против настоящего облака и
настоящего Home Assistant — единственное место, где выяснится, верны ли догадки про
`Authorization: Token` на живом токене.

**Files:** нет изменений кода, пока проверка не выявит расхождений.

- [ ] **Step 1: Скопировать интеграцию в Home Assistant**

Скопировать каталог `custom_components/waterius_cloud` в `/config/custom_components/`
на инстансе Home Assistant и перезапустить его.

- [ ] **Step 2: Включить подробный лог**

Добавить в `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.waterius_cloud: debug
```

- [ ] **Step 3: Добавить интеграцию**

Настройки → Устройства и службы → Добавить интеграцию → «Ватериус» → вставить токен,
полученный по инструкции из README.

Expected: создаётся устройство с именем вашего прибора и сущности — два сенсора показаний
(Горячая вода 0.52, Холодная вода 0.66), три диагностических сенсора, два `problem`,
один `connectivity`, одна неактивная кнопка.

Поскольку config flow и платформы сущностей тестами не покрыты, этот шаг проверяет их
вместо тестов. Пройти надо весь список:

- Показания: «Горячая вода» = 0.52, «Холодная вода» = 0.66, единица м³, у обеих
  в атрибутах есть `monthly_limit` (25 и 50), `factor` = 10, `number` (0 и 1)
- Обе сущности показаний имеют `state_class: total_increasing` и видны в «Энергия →
  Потребление воды» при добавлении
- Диагностика: заряд 88 %, напряжение 3.144 В, последний выход на связь непустой
- `connectivity` = «Подключено», кнопка «Обновить сейчас» — недоступна (`can_refresh: false`)
- Оба `problem` — «ОК»
- Устройство показывает версию прошивки `1.1.20-32` и MAC
- Повторное добавление той же интеграции с тем же токеном отклоняется
  с «Аккаунт уже настроен»
- Изменение интервала опроса в настройках интеграции применяется без ошибок
  и перезагружает запись
- Reauth: временно испортить токен в `.storage/core.config_entries` при остановленном
  Home Assistant, запустить, убедиться, что появилось «Требуется повторная
  аутентификация», и вернуть верный токен через диалог

- [ ] **Step 4: Проверить журнал**

Run: `grep waterius_cloud /config/home-assistant.log`
Expected: нет исключений, нет `UpdateFailed`.

Если вместо этого в журнале `ConfigEntryAuthFailed` — токен не принимается: проверить,
что скопировано именно значение `key` без кавычек и пробелов, и что вход в кабинете
не выполнялся заново после его получения.

- [ ] **Step 5: Записать фактический результат в README**

Дописать в README раздел:

```markdown
## Проверено

- Home Assistant <версия>, прибор Ватериус <модель>, прошивка 1.1.20-32, два канала
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: record the verified setup"
```

---

## Готовность

После Task 16 интеграция работает на живом инстансе. Отложено сознательно и в объём не входит:
восстановление истории (облако её не отдаёт), поддержка источников Saures, запись показаний.
