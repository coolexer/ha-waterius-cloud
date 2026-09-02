"""Test bootstrap.

``aioresponses`` 0.7.9 constructs ``aiohttp.ClientResponse`` without the
``stream_writer`` keyword argument that aiohttp >=3.12 made required. This
breaks every mocked request under the aiohttp/homeassistant versions pinned
here (aiohttp==3.14.3). There is no newer aioresponses release that fixes
this yet, so we patch the missing keyword to default to ``None`` for the
duration of the test session.
"""

from __future__ import annotations

from unittest.mock import Mock

import aioresponses.core as _aioresponses_core

_original_init = _aioresponses_core.ClientResponse.__init__


def _patched_init(self, *args, **kwargs):
    if kwargs.get("stream_writer") is None:
        stub = Mock()
        stub.output_size = 0
        kwargs["stream_writer"] = stub
    _original_init(self, *args, **kwargs)


_aioresponses_core.ClientResponse.__init__ = _patched_init
