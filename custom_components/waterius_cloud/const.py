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
