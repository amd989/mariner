"""The SDCP network service: UDP discovery plus a WebSocket/HTTP server.

Runs one asyncio event loop on a daemon thread. Blocking work (serial I/O,
file assembly) is pushed to the default executor so the loop stays responsive.
"""

import asyncio
import json
import logging
import socket
import threading
from typing import Any, Dict, List, Optional, Set

from aiohttp import WSMsgType, web

from mariner import config
from mariner.server.providers.sdcp import constants, identity, messages
from mariner.server.providers.sdcp.bridge import PrinterBridge
from mariner.server.providers.sdcp.history import HistoryStore, TaskStatus
from mariner.server.providers.sdcp.uploads import UploadManager

logger: logging.Logger = logging.getLogger(__name__)

# aiohttp rejects bodies over client_max_size. Chunks are ~1MB plus multipart
# overhead; allow generous headroom for clients that use a larger packet size.
MAX_UPLOAD_BODY: int = 16 * 1024 * 1024

# Consecutive non-printing status samples required before a history task is
# closed. Guards against a transient serial failure, which reads as idle.
IDLE_SAMPLES_BEFORE_CLOSE: int = 2


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Answers the ``M99999`` broadcast with this printer's identity."""

    def __init__(self, service: "SDCPService") -> None:
        self._service = service
        self._transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self._transport = transport

    def datagram_received(self, data: bytes, addr: Any) -> None:
        if data.strip() != constants.DISCOVERY_MAGIC:
            return
        # Bound to a local because building the reply calls out, which would
        # otherwise invalidate the None check on the attribute.
        transport = self._transport
        if transport is None:
            return
        peer = addr[0] if addr else None
        payload = self._service.build_discovery_response(peer)
        logger.info("SDCP: discovery request from %s", peer)
        transport.sendto(json.dumps(payload).encode("utf-8"), addr)


class SDCPService:
    def __init__(self) -> None:
        self._bridge = PrinterBridge()
        self._uploads = UploadManager()
        self._clients: Set[web.WebSocketResponse] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._last_status: Optional[Dict[str, Any]] = None
        self._name_override: Optional[str] = None
        self._idle_observations: int = 0
        self._history: Optional[HistoryStore] = None
        if config.get_sdcp_history_enabled():
            self._history = HistoryStore(
                config.get_sdcp_history_path(),
                limit=config.get_sdcp_history_limit(),
            )

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="sdcp-service", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception:
            logger.exception("SDCP: service stopped unexpectedly")

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        server_port = config.get_sdcp_server_port()
        discovery_port = config.get_sdcp_discovery_port()

        runner = await self._start_http(server_port)
        if runner is None:
            return

        discovery_transport = await self._start_discovery(discovery_port)

        logger.info(
            "SDCP: serving on port %d, discovery on port %d (mainboard %s)",
            server_port,
            discovery_port,
            identity.get_mainboard_id(),
        )

        try:
            await self._poll_status_forever()
        finally:
            if discovery_transport is not None:
                discovery_transport.close()
            await runner.cleanup()

    async def _start_http(self, port: int) -> Optional[web.AppRunner]:
        app = web.Application(client_max_size=MAX_UPLOAD_BODY)
        app.router.add_get(constants.WEBSOCKET_PATH, self._handle_websocket)
        app.router.add_post(constants.UPLOAD_PATH, self._handle_upload)
        app.router.add_get(
            constants.THUMBNAIL_PATH + "/{task_id}", self._handle_thumbnail
        )

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        try:
            await site.start()
        except OSError as exc:
            logger.error("SDCP: cannot bind port %d: %s", port, exc)
            await runner.cleanup()
            return None
        return runner

    async def _start_discovery(self, port: int) -> Optional[asyncio.DatagramTransport]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as exc:
            logger.error("SDCP: cannot bind discovery port %d: %s", port, exc)
            sock.close()
            return None

        assert self._loop is not None
        transport, _protocol = await self._loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self), sock=sock
        )
        return transport

    # -- discovery ------------------------------------------------------

    def build_discovery_response(self, peer: Optional[str]) -> Dict[str, Any]:
        return messages.discovery_response(
            name=self.printer_name(),
            machine_name=config.get_sdcp_machine_name(),
            brand_name=config.get_sdcp_brand_name(),
            mainboard_ip=identity.get_local_ip(peer),
            firmware_version=config.get_sdcp_firmware_version(),
            protocol_version=constants.PROTOCOL_VERSION,
        )

    def printer_name(self) -> str:
        return self._name_override or self._bridge.printer_name()

    # -- websocket ------------------------------------------------------

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        logger.info("SDCP: client connected from %s", request.remote)

        try:
            await self._push_attributes(ws)
            await self._push_status(ws)

            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_text(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("SDCP: websocket handler failed")
        finally:
            self._clients.discard(ws)
            logger.info("SDCP: client disconnected from %s", request.remote)
        return ws

    async def _handle_text(self, ws: web.WebSocketResponse, raw: str) -> None:
        text = (raw or "").strip()
        # The heartbeat is the bare string "ping"; some clients quote it.
        if text in ("ping", '"ping"'):
            await ws.send_str("pong")
            return

        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            logger.warning("SDCP: ignoring non-JSON message")
            return

        inner = payload.get("Data") or {}
        try:
            cmd = int(inner.get("Cmd"))
        except (TypeError, ValueError):
            logger.warning("SDCP: message without a valid Cmd")
            return

        request_id = inner.get("RequestID")
        data = inner.get("Data") or {}
        await self._dispatch(ws, cmd, data, request_id)

    async def _dispatch(
        self,
        ws: web.WebSocketResponse,
        cmd: int,
        data: Dict[str, Any],
        request_id: Optional[str],
    ) -> None:
        logger.debug("SDCP: cmd %s data=%s", cmd, data)

        if cmd == constants.Cmd.REFRESH_STATUS:
            await self._reply(ws, cmd, {"Ack": 0}, request_id)
            await self._push_status(ws)
            return

        if cmd == constants.Cmd.REFRESH_ATTRIBUTES:
            await self._reply(ws, cmd, {"Ack": 0}, request_id)
            await self._push_attributes(ws)
            return

        if cmd == constants.Cmd.START_PRINT:
            filename = str(data.get("Filename", ""))
            try:
                start_layer = int(data.get("StartLayer", 0) or 0)
            except (TypeError, ValueError):
                start_layer = 0
            ack = await self._in_executor(
                self._bridge.start_print, filename, start_layer
            )
            # History is driven purely by observation. Seeding a task here
            # would be closed again by the next status snapshot, because the
            # printer still reports IDLE for a moment after the command.
            await self._reply(ws, cmd, {"Ack": ack}, request_id)
            await self._broadcast_status()
            return

        if cmd in (
            constants.Cmd.PAUSE_PRINT,
            constants.Cmd.STOP_PRINT,
            constants.Cmd.CONTINUE_PRINT,
        ):
            action = {
                int(constants.Cmd.PAUSE_PRINT): self._bridge.pause_print,
                int(constants.Cmd.STOP_PRINT): self._bridge.stop_print,
                int(constants.Cmd.CONTINUE_PRINT): self._bridge.resume_print,
            }[cmd]
            ack = await self._in_executor(action)
            await self._reply(ws, cmd, {"Ack": ack}, request_id)
            await self._broadcast_status()
            return

        if cmd in (constants.Cmd.STOP_FEEDING, constants.Cmd.SKIP_PREHEATING):
            # ChiTu boards driven by Mariner have neither feature; accepting
            # the command keeps clients from treating it as a hard failure.
            await self._reply(ws, cmd, {"Ack": 0}, request_id)
            return

        if cmd == constants.Cmd.CHANGE_NAME:
            name = str(data.get("Name", "")).strip()
            if name:
                # Runtime only: the display name lives in config.toml, which
                # the service does not rewrite.
                self._name_override = name
                logger.info("SDCP: printer name set to %r for this session", name)
            await self._reply(ws, cmd, {"Ack": 0}, request_id)
            await self._broadcast_attributes()
            return

        if cmd == constants.Cmd.TERMINATE_TRANSFER:
            upload_uuid = str(data.get("Uuid", ""))
            filename = str(data.get("FileName", ""))
            ack = await self._in_executor(
                self._uploads.terminate, upload_uuid, filename
            )
            await self._reply(ws, cmd, {"Ack": ack}, request_id)
            return

        if cmd == constants.Cmd.LIST_FILES:
            url = str(data.get("Url", ""))
            file_list = await self._in_executor(self._bridge.list_files, url)
            await self._reply(ws, cmd, {"Ack": 0, "FileList": file_list}, request_id)
            return

        if cmd == constants.Cmd.DELETE_FILES:
            failures = await self._in_executor(
                self._bridge.delete,
                data.get("FileList") or [],
                data.get("FolderList") or [],
            )
            reply: Dict[str, Any] = {"Ack": 0}
            if failures:
                reply["ErrData"] = failures
            await self._reply(ws, cmd, reply, request_id)
            return

        if cmd == constants.Cmd.HISTORY_TASKS:
            task_ids = self._history.task_ids() if self._history else []
            await self._reply(ws, cmd, {"Ack": 0, "HistoryData": task_ids}, request_id)
            return

        if cmd == constants.Cmd.TASK_DETAILS:
            details: List[Dict[str, Any]] = []
            if self._history is not None:
                requested = data.get("Id") or []
                if not isinstance(requested, list):
                    requested = [requested]
                details = self._history.details(
                    [str(t) for t in requested], self._thumbnail_url
                )
            await self._reply(
                ws, cmd, {"Ack": 0, "HistoryDetailList": details}, request_id
            )
            return

        if cmd == constants.Cmd.VIDEO_STREAM:
            await self._reply(
                ws,
                cmd,
                {"Ack": int(constants.VideoStreamAck.CAMERA_MISSING)},
                request_id,
            )
            return

        if cmd == constants.Cmd.TIMELAPSE:
            # No camera, so time-lapse can never be enabled.
            await self._reply(ws, cmd, {"Ack": 1}, request_id)
            return

        logger.info("SDCP: unsupported command %s", cmd)
        await self._reply(ws, cmd, {"Ack": 1}, request_id)

    async def _reply(
        self,
        ws: web.WebSocketResponse,
        cmd: int,
        data: Dict[str, Any],
        request_id: Optional[str],
    ) -> None:
        await self._send(ws, messages.response(cmd, data, request_id))

    # -- status / attribute publishing ----------------------------------

    async def _push_status(self, ws: web.WebSocketResponse) -> None:
        payload = await self._status_payload()
        await self._send(ws, messages.status(payload))

    async def _push_attributes(self, ws: web.WebSocketResponse) -> None:
        payload = await self._attributes_payload()
        await self._send(ws, messages.attributes(payload))

    async def _broadcast_status(self) -> None:
        if not self._clients:
            return
        payload = await self._status_payload()
        self._last_status = payload
        await self._broadcast(messages.status(payload))

    async def _broadcast_attributes(self) -> None:
        if not self._clients:
            return
        payload = await self._attributes_payload()
        await self._broadcast(messages.attributes(payload))

    async def _status_payload(self) -> Dict[str, Any]:
        transferring = self._uploads.is_transferring()
        payload = await self._in_executor(
            lambda: self._bridge.snapshot_status(transferring=transferring)
        )
        self._record_history(payload)
        return payload

    def _record_history(self, payload: Dict[str, Any]) -> None:
        """Open, advance, and close history tasks from an observed status.

        This is the only place prints are noticed, and it runs on the same
        cadence as status polling, so prints started while no client is
        connected are not recorded.
        """
        if self._history is None:
            return
        info = payload.get("PrintInfo") or {}
        filename = str(info.get("Filename") or "")
        printing = int(constants.MachineStatus.PRINTING) in (
            payload.get("CurrentStatus") or []
        )

        if printing and filename:
            self._idle_observations = 0
            total = int(info.get("TotalLayer") or 0)
            self._history.start_task(filename, total)
            self._history.update_progress(
                filename, int(info.get("CurrentLayer") or 0), total
            )
            return

        # A serial read that fails is reported as idle, so closing on the
        # first non-printing sample would split one print into several tasks
        # whenever the link blips. Require a couple in a row.
        self._idle_observations += 1
        if self._idle_observations >= IDLE_SAMPLES_BEFORE_CLOSE:
            # Mariner cannot see the difference between a finished print and
            # a cancelled one, so the store infers it from layers reached.
            self._history.finish_task(TaskStatus.STOPPED)

    async def _attributes_payload(self) -> Dict[str, Any]:
        payload = await self._in_executor(self._bridge.snapshot_attributes)
        if self._name_override:
            payload["Name"] = self._name_override
        return payload

    async def _poll_status_forever(self) -> None:
        interval = config.get_sdcp_poll_interval_secs()
        while True:
            await asyncio.sleep(interval)
            # Polling hits the serial port, which the web UI also uses, so
            # only do it while somebody is actually listening.
            if not self._clients:
                continue
            try:
                payload = await self._status_payload()
            except Exception:
                logger.exception("SDCP: status poll failed")
                continue
            if payload != self._last_status:
                self._last_status = payload
                await self._broadcast(messages.status(payload))

    async def _broadcast(self, message: Dict[str, Any]) -> None:
        for ws in list(self._clients):
            await self._send(ws, message)

    async def _send(self, ws: web.WebSocketResponse, message: Dict[str, Any]) -> None:
        if ws.closed:
            self._clients.discard(ws)
            return
        try:
            await ws.send_str(json.dumps(message))
        except (ConnectionResetError, RuntimeError) as exc:
            logger.debug("SDCP: dropping client: %s", exc)
            self._clients.discard(ws)

    # -- file upload ----------------------------------------------------

    async def _handle_upload(self, request: web.Request) -> web.Response:
        form: Any
        try:
            form = await request.post()
        except Exception as exc:
            logger.warning("SDCP: malformed upload request: %s", exc)
            return web.json_response(
                messages.upload_failure(constants.UploadError.UNKNOWN)
            )

        def field(name: str, default: str = "") -> str:
            # The spec lists these alongside the multipart body, but real
            # clients send some of them as headers.
            value = form.get(name)
            if value is None:
                value = request.headers.get(name)
            if value is None:
                return default
            return str(value)

        # A multipart file part exposes .file / .filename; a plain form value
        # is a str, which means the client did not send the binary payload.
        file_field = form.get("File")
        file_handle: Any = getattr(file_field, "file", None)
        filename: str = str(getattr(file_field, "filename", "") or "")
        if file_handle is None:
            return web.json_response(
                messages.upload_failure(
                    constants.UploadError.UNKNOWN, "Cannot be empty"
                )
            )

        offset: int
        try:
            offset = int(field("Offset", "0") or 0)
        except ValueError:
            return web.json_response(
                messages.upload_failure(constants.UploadError.OFFSET_ERROR)
            )
        total_size: int
        try:
            total_size = int(field("TotalSize", "0") or 0)
        except ValueError:
            total_size = 0

        upload_uuid: str = field("Uuid") or "default"
        expected_md5: str = field("S-File-MD5")
        verify: bool = field("Check", "0") == "1"

        def read_and_store() -> Any:
            data = file_handle.read()
            return self._uploads.handle_chunk(
                upload_uuid=upload_uuid,
                filename=filename,
                offset=offset,
                total_size=total_size,
                expected_md5=expected_md5,
                verify=verify,
                data=data,
            )

        result = await self._in_executor(read_and_store)

        if result.md5_failed:
            await self._broadcast(messages.error(int(constants.ErrorCode.MD5_FAILED)))
        elif result.format_failed:
            await self._broadcast(
                messages.error(int(constants.ErrorCode.FORMAT_FAILED))
            )

        if not result.ok:
            return web.json_response(
                messages.upload_failure(
                    result.error
                    if result.error is not None
                    else constants.UploadError.UNKNOWN
                )
            )

        if result.completed:
            await self._broadcast_status()

        return web.json_response(messages.upload_success())

    # -- thumbnails -----------------------------------------------------

    def _thumbnail_url(self, task_id: str, filename: str) -> str:
        """Address for a task's preview, or "" when it cannot be rendered.

        The file may have been deleted since the print, in which case the
        spec's Thumbnail field is better left empty than pointing at a 404.
        """
        if not filename or not self._bridge.has_preview(filename):
            return ""
        host = identity.get_local_ip()
        port = config.get_sdcp_server_port()
        return f"http://{host}:{port}{constants.THUMBNAIL_PATH}/{task_id}"

    async def _handle_thumbnail(self, request: web.Request) -> web.Response:
        task_id = request.match_info.get("task_id", "")
        # Strip a trailing extension so /thumbnail/<id>.png also resolves.
        task_id = task_id.rsplit(".", 1)[0]

        if self._history is None:
            raise web.HTTPNotFound()
        filename = self._history.filename_for(task_id)
        if not filename:
            raise web.HTTPNotFound()

        preview = await self._in_executor(self._bridge.render_preview, filename)
        if preview is None:
            raise web.HTTPNotFound()
        return web.Response(body=preview, content_type="image/png")

    # -- helpers --------------------------------------------------------

    async def _in_executor(self, func: Any, *args: Any) -> Any:
        assert self._loop is not None
        return await self._loop.run_in_executor(None, func, *args)
