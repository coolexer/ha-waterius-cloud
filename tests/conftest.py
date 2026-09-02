"""Test bootstrap.

``aioresponses`` 0.7.9 constructs ``aiohttp.ClientResponse`` without the
``stream_writer`` keyword argument that aiohttp made required in 3.12, so every
mocked request raises ``TypeError`` under a recent aiohttp. There is no
aioresponses release that fixes this yet, so we supply the argument ourselves.

The patch is applied only when the installed aiohttp actually wants that
argument: older aiohttp rejects it, and pinning either way would tie the test
suite to one aiohttp version.
"""

from __future__ import annotations

import inspect
from unittest.mock import Mock

import aioresponses.core as _aioresponses_core

_ClientResponse = _aioresponses_core.ClientResponse
_original_init = _ClientResponse.__init__

_NEEDS_STREAM_WRITER = "stream_writer" in inspect.signature(_original_init).parameters


def _patched_init(self, *args, **kwargs):
    if kwargs.get("stream_writer") is None:
        stub = Mock()
        stub.output_size = 0
        kwargs["stream_writer"] = stub
    _original_init(self, *args, **kwargs)


if _NEEDS_STREAM_WRITER:
    _ClientResponse.__init__ = _patched_init
