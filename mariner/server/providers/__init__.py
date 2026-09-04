import logging
from typing import List

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from mariner.server.providers.base import NetworkPrintProvider
from mariner.server.providers.uvtools import UVToolsProvider

logger = logging.getLogger(__name__)

_providers: List[NetworkPrintProvider] = [
    UVToolsProvider(),
]


def get_provider_prefixes() -> List[str]:
    return [p.name for p in _providers]


def register_providers(app: Flask, csrf: CSRFProtect) -> None:
    for provider in _providers:
        bp = provider.create_blueprint()
        csrf.exempt(bp)
        app.register_blueprint(bp)
        logger.info("Registered network print provider: %s", provider.name)
