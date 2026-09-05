"""Stable identifiers for the emulated SDCP mainboard.

SDCP clients key their bookkeeping on ``MainboardID``, so it has to stay the
same across restarts. We derive it from the host's machine-id (falling back to
the primary MAC address) unless the user pins one in ``config.toml``.
"""

import hashlib
import socket
import uuid
from functools import lru_cache
from typing import Optional

from mariner import config


@lru_cache(maxsize=None)
def _machine_seed() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, "r") as handle:
                value = handle.read().strip()
        except OSError:
            continue
        if value:
            return value
    # uuid.getnode() falls back to a random node id when no MAC is readable,
    # which would change the mainboard id across restarts. It is the best
    # available option on hosts without a machine-id file.
    return f"{uuid.getnode():012x}"


def get_mainboard_id() -> str:
    """16 hex character mainboard identifier."""
    configured = config.get_sdcp_mainboard_id()
    if configured:
        return configured
    seed = f"mariner-sdcp-mainboard-{_machine_seed()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]


def get_brand_id() -> str:
    """32 hex character brand identifier (the top level ``Id`` field)."""
    seed = f"mariner-sdcp-brand-{_machine_seed()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def get_local_ip(peer: Optional[str] = None) -> str:
    """Best-effort local IP address, as seen from *peer*.

    Routing to the peer picks the right source address on multi-homed hosts,
    which matters because the discovery reply tells the client where to
    connect back to.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((peer or "8.8.8.8", 1))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
