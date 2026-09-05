from abc import ABC, abstractmethod

from flask import Blueprint


class NetworkPrintProvider(ABC):
    """Base class for network print providers.

    A provider exposes whatever an external tool needs in order to upload
    files, start prints, and read printer status. There are two ways to do
    that, and a provider may use either:

    * Routes on Mariner's own HTTP port, added in :meth:`register_routes`.
      They are registered as a CSRF-exempt Flask blueprint under ``/<name>/``
      so headless clients can call them without a browser session.
    * Its own listeners, started in :meth:`start`. Protocols that dictate
      their own ports or transports (WebSocket, UDP discovery) need this.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, also used as the URL prefix (e.g. ``uvtools``)."""
        ...

    @property
    def provides_http_routes(self) -> bool:
        """Whether this provider serves routes on Mariner's HTTP port."""
        return True

    def register_routes(self, blueprint: Blueprint) -> None:
        """Add route rules to *blueprint*.

        Providers that run their own listeners do not need to override this.
        """
        return None

    def start(self) -> None:
        """Start background listeners.

        Called once from the server entry point, never at import time, so
        that importing the app in tests does not bind ports.
        """
        return None

    def create_blueprint(self) -> Blueprint:
        bp = Blueprint(
            f"provider_{self.name}",
            __name__,
            url_prefix=f"/{self.name}",
        )
        self.register_routes(bp)
        return bp
