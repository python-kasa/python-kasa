"""Shared SSL context for the transports talking https to local devices.

Not security sensitive: certificates are not verified.
The extra ciphers exist only for compatibility,
as Python's defaults lack suites older firmware needs.
"""

from __future__ import annotations

import asyncio
import ssl
from functools import cache

LEGACY_CIPHERS = [
    "AES256-GCM-SHA384",
    "AES256-SHA256",
    "AES128-GCM-SHA256",
    "AES128-SHA256",
    "AES256-SHA",
    "AES128-SHA",
    "ECDHE-RSA-AES128-SHA",
    "ECDHE-RSA-AES256-SHA",
]


@cache
def _create_ssl_context() -> ssl.SSLContext:
    """Return the cached context, blocking on first use."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Append to the defaults so suites newer firmware needs are not dropped.
    default = [cipher["name"] for cipher in context.get_ciphers()]
    context.set_ciphers(":".join([*default, *LEGACY_CIPHERS]))
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


async def get_ssl_context() -> ssl.SSLContext:
    """Return the cached context, created in an executor as that blocks."""
    return await asyncio.get_running_loop().run_in_executor(None, _create_ssl_context)
