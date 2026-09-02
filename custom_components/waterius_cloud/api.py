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
            if not isinstance(payload, dict):
                raise WateriusConnectionError(
                    "Облако Ватериус вернуло пустой или неожиданный ответ"
                )
            sources.extend(payload.get("results") or [])
            url = payload.get("next")
        return sources

    async def refresh_source(self, source_id: int) -> None:
        """Попросить облако обновить данные прибора.

        Кабинет дёргает этот эндпоинт методом GET и ограничивает частоту:
        повторный вызов раньше кулдауна возвращает 429.
        """
        await self._request("GET", f"{self._base_url}/api/source/{source_id}/update")
