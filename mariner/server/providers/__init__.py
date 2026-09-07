import logging
from typing import List

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from mariner.server.providers.base import NetworkPrintProvider
from mariner.server.providers.sdcp import SDCPProvider
from mariner.server.providers.uvtools import UVToolsProvider

logger: logging.Logger = logging.getLogger(__name__)

_providers: List[NetworkPrintProvider] = [
    UVToolsProvider(),
    SDCPProvider(),
]


def get_provider_prefixes() -> List[str]:
    """URL prefixes owned by providers, so the SPA fallback can skip them."""
    return [p.name for p in _providers if p.provides_http_routes]


def register_providers(app: Flask, csrf: CSRFProtect) -> None:
    """Attach provider blueprints to *app*. Safe to call at import time."""
    for provider in _providers:
        if not provider.provides_http_routes:
            continue
        bp = provider.create_blueprint()
        csrf.exempt(bp)
        app.register_blueprint(bp)
        logger.info("Registered network print provider: %s", provider.name)


def start_providers() -> None:
    """Start providers that run their own listeners.

    Called from the server entry point rather than at import time so that
    importing the app (in tests, or under a WSGI loader) binds no ports.
    """
    for provider in _providers:
        try:
            provider.start()
        except Exception:
            logger.exception("Failed to start provider %s", provider.name)
