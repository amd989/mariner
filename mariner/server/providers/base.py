from abc import ABC, abstractmethod

from flask import Blueprint


class NetworkPrintProvider(ABC):
    """Base class for network print providers.

    Each provider exposes a set of HTTP endpoints that external tools
    (UVTools, etc.) can call to upload files, start prints, and query
    printer status.  Providers are registered as Flask blueprints with
    CSRF exemption so that headless clients can call them directly.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used as the URL prefix (e.g. ``uvtools``)."""
        ...

    @abstractmethod
    def register_routes(self, blueprint: Blueprint) -> None:
        """Add route rules to *blueprint*."""
        ...

    def create_blueprint(self) -> Blueprint:
        bp = Blueprint(
            f"provider_{self.name}",
            __name__,
            url_prefix=f"/{self.name}",
        )
        self.register_routes(bp)
        return bp
