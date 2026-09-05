"""SDCP v3.0.0 network print provider.

Makes Mariner discoverable and controllable by SDCP clients such as ChiTuBox,
which expect a ChiTu mainboard speaking the protocol natively.

Unlike the UVTools provider, SDCP does not ride on Mariner's HTTP port: the
protocol hard-codes a UDP discovery port and a combined WebSocket/upload port,
so this provider runs its own listeners.
"""

import logging
from typing import Optional

from flask import Blueprint

from mariner import config
from mariner.server.providers.base import NetworkPrintProvider

logger: logging.Logger = logging.getLogger(__name__)


class SDCPProvider(NetworkPrintProvider):
    def __init__(self) -> None:
        self._service: Optional[object] = None

    @property
    def name(self) -> str:
        return "sdcp"

    @property
    def provides_http_routes(self) -> bool:
        return False

    def register_routes(self, blueprint: Blueprint) -> None:
        return None

    def start(self) -> None:
        if not config.get_sdcp_enabled():
            logger.info("SDCP provider is disabled in config")
            return

        try:
            from mariner.server.providers.sdcp.service import SDCPService
        except ImportError as exc:
            logger.error("SDCP provider needs aiohttp, which is not installed: %s", exc)
            return

        service = SDCPService()
        service.start()
        self._service = service
