import ssl

from kasa.transports.sslcontext import get_ssl_context


async def test_ssl_context_extends_python_defaults_with_legacy_suites() -> None:
    """Some ciphers are added on top of Python's defaults for compatibility."""
    default = {c["name"] for c in ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).get_ciphers()}
    enabled = {c["name"] for c in (await get_ssl_context()).get_ciphers()}
    assert default <= enabled
    assert {"AES128-GCM-SHA256", "AES256-SHA"} <= enabled
