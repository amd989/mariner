"""Translation layer between SDCP concepts and Mariner's printer/file code.

Everything in here is blocking (serial I/O, filesystem walks). The asyncio
service calls it through an executor so the event loop keeps serving the
WebSocket while the printer is being polled.
"""

import logging
import os
import shutil
import threading
import uuid as uuid_module
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

import serial

from mariner import config
from mariner.exceptions import UnexpectedPrinterResponse
from mariner.file_formats.utils import get_file_extension, get_supported_extensions
from mariner.printer import ChiTuPrinter, PrinterState
from mariner.server.api import _layer_from_byte_offset
from mariner.server.providers.sdcp import constants, identity
from mariner.server.utils import (
    read_cached_preview,
    read_cached_sliced_model_file,
    retry,
)

logger: logging.Logger = logging.getLogger(__name__)

# Hardware the protocol can describe but that most MSLA printers do not
# have. Reported only when config says the machine is fitted with it, since
# SDCP's 0 means "disconnected" rather than "not fitted".
# How many recent files to try when deriving the machine's resolution and
# build volume. More than one so a single unreadable file does not leave the
# printer advertising 0x0.
GEOMETRY_SAMPLE_FILES: int = 5

# Only used when the board cannot be reached and config sets nothing.
FALLBACK_FIRMWARE_VERSION: str = "V1.0.0"

OPTIONAL_DEVICES: Dict[str, str] = {
    "x_motor": "XMotorStatus",
    "rotate_motor": "RotateMotorStatus",
}

_TRANSIENT_ERRORS: Tuple[Type[Exception], ...] = (
    UnexpectedPrinterResponse,
    serial.SerialException,
)

# Mariner's printer state maps onto an SDCP top-level status plus a printing
# sub-status. Mariner cannot see the lift/drop phases the protocol models, so
# an active print always reports EXPOSURING.
_STATE_MAP: Dict[PrinterState, Tuple[int, int]] = {
    PrinterState.IDLE: (
        constants.MachineStatus.IDLE,
        constants.PrintStatus.IDLE,
    ),
    PrinterState.CLOSED: (
        constants.MachineStatus.IDLE,
        constants.PrintStatus.IDLE,
    ),
    PrinterState.STARTING_PRINT: (
        constants.MachineStatus.PRINTING,
        constants.PrintStatus.HOMING,
    ),
    PrinterState.PRINTING: (
        constants.MachineStatus.PRINTING,
        constants.PrintStatus.EXPOSURING,
    ),
    PrinterState.PAUSED: (
        constants.MachineStatus.PRINTING,
        constants.PrintStatus.PAUSED,
    ),
}


def strip_storage_prefix(path: str) -> str:
    """Drop the ``/local/`` or ``/usb/`` prefix SDCP uses for storage roots.

    Mariner has a single files directory, so both roots resolve to it.
    """
    value = (path or "").strip()
    for prefix in (constants.LOCAL_PREFIX, constants.USB_PREFIX):
        if value.startswith(prefix):
            return value.removeprefix(prefix)
    return value.lstrip("/")


def _safe_resolve(relative: str) -> Optional[Path]:
    """Resolve *relative* inside the files directory, or None if it escapes."""
    files_dir = config.get_files_directory().resolve()
    candidate = (files_dir / relative).resolve()
    if candidate != files_dir and files_dir not in candidate.parents:
        return None
    return candidate


class PrinterBridge:
    """Serializes access to the printer and renders SDCP payloads."""

    _lock: threading.Lock

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._previous_status: int = int(constants.MachineStatus.IDLE)
        # Read once from the board and kept: it cannot change while running,
        # and every attribute report would otherwise cost a serial round trip.
        self._firmware_version: Optional[str] = None

    # -- printer reads -------------------------------------------------

    def _read_printer(self) -> Tuple[PrinterState, str, int, int, Optional[float]]:
        with self._lock:
            try:
                with ChiTuPrinter() as printer:
                    status = retry(
                        printer.get_print_status, _TRANSIENT_ERRORS, num_retries=3
                    )
                    selected = retry(
                        printer.get_selected_file, _TRANSIENT_ERRORS, num_retries=3
                    )
            except _TRANSIENT_ERRORS:
                return (PrinterState.CLOSED, "", 0, 0, None)
            except OSError as exc:
                logger.debug("SDCP: printer unreachable: %s", exc)
                return (PrinterState.CLOSED, "", 0, 0, None)

        return (
            status.state,
            selected or "",
            status.current_byte or 0,
            status.total_bytes or 0,
            status.z_pos_mm,
        )

    def snapshot_status(self, *, transferring: bool = False) -> Dict[str, Any]:
        state, selected, current_byte, total_bytes, _z = self._read_printer()
        machine_status, print_status = _STATE_MAP.get(
            state,
            (constants.MachineStatus.IDLE, constants.PrintStatus.IDLE),
        )

        if transferring:
            machine_status = constants.MachineStatus.FILE_TRANSFERRING

        current_layer = 0
        total_layer = 0
        total_ticks = 0
        current_ticks = 0

        if selected and state not in (PrinterState.IDLE, PrinterState.CLOSED):
            sliced = self._read_sliced(selected)
            if sliced is not None:
                total_layer = sliced.layer_count or 0
                current_layer = _layer_from_byte_offset(
                    current_byte, sliced.end_byte_offset_by_layer
                )
                total_ticks = int((sliced.print_time_secs or 0) * 1000)
                if total_layer:
                    progress = max(0.0, min(1.0, (current_layer - 1) / total_layer))
                    current_ticks = int(total_ticks * progress)

        payload = {
            "CurrentStatus": [int(machine_status)],
            "PreviousStatus": int(self._previous_status),
            "PrintScreen": 0,
            "ReleaseFilm": 0,
            "TempOfUVLED": 0,
            "TimeLapseStatus": 0,
            "TempOfBox": 0,
            "TempTargetBox": 0,
            "PrintInfo": {
                "Status": int(print_status),
                "CurrentLayer": current_layer,
                "TotalLayer": total_layer,
                "CurrentTicks": current_ticks,
                "TotalTicks": total_ticks,
                "Filename": selected,
                "ErrorNumber": int(constants.PrintError.NONE),
                "TaskId": self._task_id(selected),
            },
        }
        self._previous_status = int(machine_status)
        return payload

    def snapshot_attributes(self) -> Dict[str, Any]:
        files_dir = config.get_files_directory()
        try:
            usage = shutil.disk_usage(files_dir)
            remaining = usage.free
        except OSError:
            remaining = 0

        firmware = self.firmware_version()
        resolution, xyz_size = self._machine_geometry()

        return {
            "Name": self.printer_name(),
            "MachineName": config.get_sdcp_machine_name(),
            "BrandName": config.get_sdcp_brand_name(),
            "ProtocolVersion": constants.PROTOCOL_VERSION,
            "FirmwareVersion": firmware,
            "Resolution": resolution,
            "XYZsize": xyz_size,
            "MainboardIP": identity.get_local_ip(),
            "MainboardID": identity.get_mainboard_id(),
            "NumberOfVideoStreamConnected": 0,
            "MaximumVideoStreamAllowed": 0,
            "NetworkStatus": "eth",
            "UsbDiskStatus": 1,
            # Mariner proxies files and print control but has no camera.
            "Capabilities": ["FILE_TRANSFER", "PRINT_CONTROL"],
            "SupportFileType": [
                ext.lstrip(".").upper() for ext in get_supported_extensions()
            ],
            "DevicesStatus": self._devices_status(),
            "ReleaseFilmMax": 0,
            "TempOfUVLEDMax": 0,
            "CameraStatus": 0,
            "RemainingMemory": remaining,
            "TLPNoCapPos": 0.0,
            "TLPStartCapPos": 0.0,
            "TLPInterLayers": 0,
        }

    def printer_name(self) -> str:
        return config.get_printer_display_name() or "Mariner"

    def firmware_version(self) -> str:
        """The board's real firmware version, e.g. ``V4.5.0_1.0_e13_LCDE1``.

        Config wins if set. Otherwise it is read from the board once via
        M4002, falling back to a placeholder only if the board cannot be
        reached, so clients see the measured value rather than an invented
        one.
        """
        configured = config.get_sdcp_firmware_version()
        if configured:
            return configured

        if self._firmware_version is None:
            self._firmware_version = self._read_firmware_version()
        return self._firmware_version or FALLBACK_FIRMWARE_VERSION

    def _read_firmware_version(self) -> Optional[str]:
        with self._lock:
            try:
                with ChiTuPrinter() as printer:
                    version = retry(
                        printer.get_firmware_version,
                        _TRANSIENT_ERRORS,
                        num_retries=2,
                    )
            except _TRANSIENT_ERRORS:
                return None
            except OSError as exc:
                logger.debug("SDCP: could not read firmware version: %s", exc)
                return None
        logger.info("SDCP: printer firmware version is %s", version)
        return str(version)

    def _devices_status(self) -> Dict[str, int]:
        """The device self-check report.

        Mariner cannot read any of these sensors over the ChiTu serial link,
        so this reports "no fault detected" rather than inventing failures.
        Hardware that is not fitted is omitted instead of being reported as
        0, which the protocol defines as disconnected and clients surface as
        an error.
        """
        devices: Dict[str, int] = {
            "TempSensorStatusOfUVLED": 1,
            "LCDStatus": 1,
            "SgStatus": 1,
            "ZMotorStatus": 1,
            "RelaseFilmState": 1,
        }
        fitted = config.get_sdcp_optional_devices()
        for name, field in OPTIONAL_DEVICES.items():
            if name in fitted:
                devices[field] = 1
        return devices

    def _machine_geometry(self) -> Tuple[str, str]:
        """Resolution and build volume, from config or a sliced file.

        Several files are tried, newest first, because a single unreadable
        one (truncated, or a format variant this build cannot parse) would
        otherwise leave the machine reporting 0x0.
        """
        resolution = config.get_sdcp_resolution()
        xyz_size = config.get_sdcp_xyz_size()
        if resolution and xyz_size:
            return (resolution, xyz_size)

        derived_resolution = ""
        derived_xyz = ""
        for filename in self._printable_files_newest_first(GEOMETRY_SAMPLE_FILES):
            sliced = self._read_sliced(filename)
            if sliced is None:
                continue
            try:
                width, height = sliced.resolution
                bed = sliced.bed_size_mm
                derived_resolution = f"{width}x{height}"
                derived_xyz = f"{bed[0]:g}x{bed[1]:g}x{bed[2]:g}"
            except (TypeError, ValueError, IndexError):
                continue
            break

        return (
            resolution or derived_resolution or "0x0",
            xyz_size or derived_xyz or "0x0x0",
        )

    def _printable_files_newest_first(self, limit: int) -> List[str]:
        files_dir = config.get_files_directory()
        supported = get_supported_extensions()
        candidates: List[Tuple[float, str]] = []
        try:
            with os.scandir(files_dir) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    if get_file_extension(entry.name) not in supported:
                        continue
                    candidates.append((entry.stat().st_mtime, entry.name))
        except OSError:
            return []
        candidates.sort(reverse=True)
        return [name for _mtime, name in candidates[:limit]]

    def _read_sliced(self, filename: str) -> Optional[Any]:
        path = _safe_resolve(filename)
        if path is None or not os.path.isfile(path):
            return None
        try:
            return read_cached_sliced_model_file(path)
        except Exception as exc:  # parsing failures must not break status
            logger.debug("SDCP: could not parse %s: %s", filename, exc)
            return None

    def has_preview(self, filename: str) -> bool:
        """Whether *filename* is still on disk and a format we can render."""
        path = _safe_resolve(filename)
        if path is None or not os.path.isfile(path):
            return False
        return get_file_extension(filename) in get_supported_extensions()

    def render_preview(self, filename: str) -> Optional[bytes]:
        """PNG preview bytes for *filename*, or None if it cannot be made."""
        path = _safe_resolve(filename)
        if path is None or not os.path.isfile(path):
            return None
        try:
            return read_cached_preview(path)
        except Exception as exc:
            logger.debug("SDCP: no preview for %s: %s", filename, exc)
            return None

    def _task_id(self, filename: str) -> str:
        if not filename:
            return ""
        seed = f"{identity.get_mainboard_id()}:{filename}"
        return uuid_module.uuid5(uuid_module.NAMESPACE_URL, seed).hex

    # -- print control -------------------------------------------------

    def start_print(self, filename: str, start_layer: int = 0) -> int:
        relative = strip_storage_prefix(filename)
        if not relative:
            return int(constants.PrintCtrlAck.NOT_FOUND)

        path = _safe_resolve(relative)
        if path is None or not os.path.isfile(path):
            return int(constants.PrintCtrlAck.NOT_FOUND)

        if get_file_extension(relative) not in get_supported_extensions():
            return int(constants.PrintCtrlAck.UNKNOWN_FORMAT)

        try:
            with self._lock:
                with ChiTuPrinter() as printer:
                    printer.start_printing(relative)
        except _TRANSIENT_ERRORS as exc:
            logger.warning("SDCP: start print failed: %s", exc)
            return int(constants.PrintCtrlAck.FILEIO_FAILED)
        except OSError as exc:
            logger.warning("SDCP: start print failed: %s", exc)
            return int(constants.PrintCtrlAck.BUSY)
        return int(constants.PrintCtrlAck.OK)

    def _simple_command(self, action: str) -> int:
        try:
            with self._lock:
                with ChiTuPrinter() as printer:
                    getattr(printer, action)()
        except _TRANSIENT_ERRORS as exc:
            logger.warning("SDCP: %s failed: %s", action, exc)
            return int(constants.PrintCtrlAck.BUSY)
        except OSError as exc:
            logger.warning("SDCP: %s failed: %s", action, exc)
            return int(constants.PrintCtrlAck.BUSY)
        return int(constants.PrintCtrlAck.OK)

    def pause_print(self) -> int:
        return self._simple_command("pause_printing")

    def stop_print(self) -> int:
        return self._simple_command("stop_printing")

    def resume_print(self) -> int:
        return self._simple_command("resume_printing")

    # -- file management -----------------------------------------------

    def list_files(self, url: str) -> List[Dict[str, Any]]:
        relative = strip_storage_prefix(url)
        directory = _safe_resolve(relative) if relative else _safe_resolve("")
        if directory is None or not os.path.isdir(directory):
            return []

        files_dir = config.get_files_directory().resolve()
        try:
            usage = shutil.disk_usage(directory)
            total_size = usage.total
        except OSError:
            total_size = 0

        supported = get_supported_extensions()
        entries: List[Dict[str, Any]] = []
        try:
            with os.scandir(directory) as scan:
                for entry in sorted(scan, key=lambda e: e.name):
                    if entry.name.startswith("."):
                        continue
                    rel = Path(entry.path).resolve().relative_to(files_dir)
                    display = f"{constants.LOCAL_PREFIX}{rel.as_posix()}"
                    if entry.is_dir():
                        entries.append(
                            {
                                "name": display,
                                "usedSize": 0,
                                "totalSize": total_size,
                                "storageType": 0,
                                "type": 0,
                            }
                        )
                    elif get_file_extension(entry.name) in supported:
                        entries.append(
                            {
                                "name": display,
                                "usedSize": entry.stat().st_size,
                                "totalSize": total_size,
                                "storageType": 0,
                                "type": 1,
                            }
                        )
        except OSError as exc:
            logger.warning("SDCP: listing %s failed: %s", directory, exc)
        return entries

    def delete(self, file_list: List[str], folder_list: List[str]) -> List[str]:
        """Delete the given paths, returning the ones that could not be removed."""
        failures: List[str] = []

        for raw in file_list or []:
            path = _safe_resolve(strip_storage_prefix(raw))
            if path is None or not os.path.isfile(path):
                failures.append(raw)
                continue
            try:
                os.remove(path)
            except OSError:
                failures.append(raw)

        for raw in folder_list or []:
            relative = strip_storage_prefix(raw)
            path = _safe_resolve(relative)
            files_dir = config.get_files_directory().resolve()
            if path is None or not os.path.isdir(path) or path == files_dir:
                failures.append(raw)
                continue
            try:
                shutil.rmtree(path)
            except OSError:
                failures.append(raw)

        return failures
