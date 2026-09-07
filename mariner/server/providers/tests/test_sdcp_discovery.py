import json
from typing import Any
from unittest import TestCase
from unittest.mock import Mock

from pyexpect import expect

from mariner.server.providers.sdcp import constants
from mariner.server.providers.sdcp.service import _DiscoveryProtocol


class DiscoveryProtocolTest(TestCase):
    """Unit tests for the UDP discovery responder.

    The transport here is a plain Mock, which is deliberately not an
    ``asyncio.DatagramTransport`` subclass. Before CPython 3.12 the real
    ``_SelectorDatagramTransport`` is not one either, so any runtime type
    check in ``connection_made`` would leave discovery permanently dead.
    """

    protocol: _DiscoveryProtocol
    service: Any
    transport: Any

    def setUp(self) -> None:
        self.service = Mock()
        self.service.build_discovery_response.return_value = {
            "Id": "brand-id",
            "Data": {"Name": "Mariner", "MainboardIP": "192.168.1.9"},
        }
        self.protocol = _DiscoveryProtocol(self.service)
        self.transport = Mock()

    def _connect(self) -> None:
        self.protocol.connection_made(self.transport)

    def test_connection_made_accepts_a_non_subclass_transport(self) -> None:
        self._connect()
        self.protocol.datagram_received(
            constants.DISCOVERY_MAGIC, ("192.168.1.5", 3000)
        )
        self.transport.sendto.assert_called_once()

    def test_reply_is_json_sent_back_to_the_sender(self) -> None:
        self._connect()
        addr = ("192.168.1.5", 55000)
        self.protocol.datagram_received(constants.DISCOVERY_MAGIC, addr)

        payload, reply_addr = self.transport.sendto.call_args[0]
        expect(reply_addr).to_equal(addr)
        expect(json.loads(payload.decode("utf-8"))["Id"]).to_equal("brand-id")

    def test_reply_is_built_for_the_requesting_peer(self) -> None:
        self._connect()
        self.protocol.datagram_received(
            constants.DISCOVERY_MAGIC, ("192.168.1.5", 55000)
        )
        self.service.build_discovery_response.assert_called_once_with("192.168.1.5")

    def test_trailing_whitespace_is_tolerated(self) -> None:
        self._connect()
        self.protocol.datagram_received(
            constants.DISCOVERY_MAGIC + b"\r\n", ("192.168.1.5", 3000)
        )
        self.transport.sendto.assert_called_once()

    def test_other_payloads_are_ignored(self) -> None:
        self._connect()
        self.protocol.datagram_received(b"something else", ("192.168.1.5", 3000))
        self.transport.sendto.assert_not_called()

    def test_datagram_before_connection_made_is_safe(self) -> None:
        # No transport yet: must not raise, and must not reply.
        self.protocol.datagram_received(
            constants.DISCOVERY_MAGIC, ("192.168.1.5", 3000)
        )
        self.transport.sendto.assert_not_called()
