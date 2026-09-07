import logging
import os
import subprocess
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import serial
from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    make_response,
    request,
)
from pyre_extensions import none_throws
from werkzeug.utils import secure_filename

from mariner import config
from mariner.exceptions import MarinerException, UnexpectedPrinterResponse
from mariner.file_formats import SlicedModelFile
from mariner.file_formats.utils import get_file_extension, get_supported_extensions
from mariner.printer import ChiTuPrinter, PrinterState, PrintStatus
from mariner.server.utils import (
    read_cached_preview,
    read_cached_sliced_model_file,
    retry,
)


logger: logging.Logger = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")

# Monotonic Z-derived layer estimate. Only updated when Z is near an integer
# multiple of layer_height (exposure phase). During retract the Z reading is
# meaningless for layer estimation, so we hold the last known value.
_last_z_layer: Optional[int] = None
_last_z_total_bytes: Optional[int] = None


def reset_progress_tracking() -> None:
    """Clear progress tracking state (e.g. between tests)."""
    global _last_z_layer, _last_z_total_bytes
    _last_z_layer = None
    _last_z_total_bytes = None


def _layer_from_z_position(
    z_pos_mm: Optional[float],
    layer_height_mm: float,
    layer_count: int,
    total_bytes: int,
) -> Optional[int]:
    """Derive current exposed layer from Z. Returns None if Z not in exposure phase.

    MSLA printers retract Z between layers (lift → tilt → descend), so a poll
    can catch Z mid-retract where Z is not near n*layer_height. In that case
    we can't infer the layer and the caller should fall back to the last
    known value.
    """
    global _last_z_layer, _last_z_total_bytes

    if _last_z_total_bytes != total_bytes:
        _last_z_layer = None
        _last_z_total_bytes = total_bytes

    if z_pos_mm is None or z_pos_mm <= 0 or layer_height_mm <= 0:
        return _last_z_layer

    layer_float = z_pos_mm / layer_height_mm
    nearest = round(layer_float)
    tolerance = 0.1
    if abs(layer_float - nearest) > tolerance:
        return _last_z_layer
    # Z above the last layer is a retract lift, not an exposure position.
    if nearest > layer_count:
        return _last_z_layer

    layer = max(1, min(layer_count, nearest))
    if _last_z_layer is None or layer > _last_z_layer:
        _last_z_layer = layer
    return _last_z_layer


def _layer_from_byte_offset(current_byte: int, end_byte_offsets: List[int]) -> int:
    """Fallback layer lookup: find first layer whose end-byte covers current_byte."""
    if current_byte <= 0 or not end_byte_offsets:
        return 1
    for i, end_byte in enumerate(end_byte_offsets):
        if current_byte <= end_byte:
            return i + 1
    return len(end_byte_offsets)


@api.errorhandler(MarinerException)
def handle_mariner_exception(exception: MarinerException) -> Tuple[Response, int]:
    tb = traceback.TracebackException.from_exception(exception)
    return (
        jsonify(
            {
                "title": exception.get_title(),
                "description": exception.get_description(),
                "traceback": "".join(tb.format()),
            }
        ),
        500,
    )


@api.route("/print_status", methods=["GET"])
def print_status() -> Union[str, Response]:
    with ChiTuPrinter() as printer:

        # the printer sends periodic "ok" responses over serial. this means that
        # sometimes we get an unexpected response from the printer (an "ok" instead of
        # the print status we expected). due to this, we retry at most 3 times here
        # until we have a successful response. see issue #180
        transient_errors = (UnexpectedPrinterResponse, serial.SerialException)
        try:
            print_status = retry(
                printer.get_print_status,
                transient_errors,
                num_retries=3,
            )

            selected_file = retry(
                printer.get_selected_file,
                transient_errors,
                num_retries=3,
            )
        except transient_errors:
            # Treat repeated bad/empty serial responses as a temporary disconnect
            # so the UI can keep polling and recover without surfacing a 500.
            reset_progress_tracking()
            print_status = PrintStatus(state=PrinterState.CLOSED)
            selected_file = ""

        # An empty selected_file means the printer serial call failed or the
        # board returned no filename — we can't look up layer metadata without
        # it, so degrade gracefully like IDLE/CLOSED instead of crashing in
        # read_cached_sliced_model_file's isfile assert.
        if (
            print_status.state == PrinterState.IDLE
            or print_status.state == PrinterState.CLOSED
            or not selected_file
        ):
            progress = 0.0
            print_details = {}
        else:
            sliced_model_file = read_cached_sliced_model_file(
                config.get_files_directory() / selected_file
            )

            current_byte = print_status.current_byte or 0
            layer_count = none_throws(sliced_model_file.layer_count)
            layer_height_mm = sliced_model_file.layer_height_mm

            # Z-derived layer is the ground-truth physical layer. ChiTu D: byte
            # position runs ahead of actual exposure (firmware reads/buffers
            # layers before exposing them), so Z is preferred; byte offset is
            # only a fallback for the pre-exposure ramp where Z isn't usable.
            z_layer: Optional[int] = None
            if print_status.state in (PrinterState.PRINTING, PrinterState.PAUSED):
                z_layer = _layer_from_z_position(
                    print_status.z_pos_mm,
                    layer_height_mm,
                    layer_count,
                    print_status.total_bytes or 0,
                )

            if z_layer is not None:
                current_layer = z_layer
            else:
                current_layer = _layer_from_byte_offset(
                    current_byte, sliced_model_file.end_byte_offset_by_layer
                )

            progress = 100.0 * (current_layer - 1) / layer_count

            print_details = {
                "current_layer": current_layer,
                "layer_count": sliced_model_file.layer_count,
                "print_time_secs": sliced_model_file.print_time_secs,
                "time_left_secs": round(
                    sliced_model_file.print_time_secs * (100.0 - progress) / 100.0
                ),
            }

            logger.debug(
                "print_status debug: state=%s file=%r D=(%s/%s) "
                "z=%s z_layer=%s progress=%.3f layer=%s/%s",
                print_status.state.name,
                selected_file,
                current_byte,
                print_status.total_bytes,
                print_status.z_pos_mm,
                z_layer,
                progress,
                current_layer,
                layer_count,
            )

        return jsonify(
            {
                "state": print_status.state.value,
                "selected_file": selected_file,
                "progress": progress,
                **print_details,
            }
        )


@api.route("/list_files", methods=["GET"])
def list_files() -> Union[str, Response]:
    path_parameter = str(request.args.get("path", "."))
    path = (config.get_files_directory() / path_parameter).resolve()
    files_directory_resolved = config.get_files_directory().resolve()
    if (
        files_directory_resolved not in path.parents
        and path != files_directory_resolved
    ):
        abort(400)
    with os.scandir(path) as dir_entries:
        files = []
        directories = []
        for dir_entry in sorted(
            dir_entries, key=lambda t: t.stat().st_mtime, reverse=True
        ):
            if dir_entry.is_file():
                sliced_model_file: Optional[SlicedModelFile] = None
                if get_file_extension(dir_entry.name) in get_supported_extensions():
                    # A file with a supported extension can still fail to
                    # parse: truncated, corrupted in transfer, or a format
                    # variant this build does not understand. That must not
                    # take down the whole listing, so it is reported as a
                    # file that cannot be printed.
                    try:
                        if dir_entry.name.startswith("._"):
                            if b"Mac OS X" not in open(dir_entry.path, "rb").read(32):
                                sliced_model_file = read_cached_sliced_model_file(
                                    path / dir_entry.name
                                )
                        else:
                            sliced_model_file = read_cached_sliced_model_file(
                                path / dir_entry.name
                            )
                    except Exception:
                        logger.warning(
                            "Could not read %s; listing it as unprintable",
                            dir_entry.name,
                            exc_info=True,
                        )
                        sliced_model_file = None

                file_data: Dict[str, Any] = {
                    "filename": dir_entry.name,
                    "path": str(
                        (path / dir_entry.name).relative_to(files_directory_resolved)
                    ),
                }

                if sliced_model_file:
                    file_data = {
                        "print_time_secs": sliced_model_file.print_time_secs,
                        "can_be_printed": True,
                        **file_data,
                    }
                else:
                    file_data = {
                        "can_be_printed": False,
                        **file_data,
                    }

                files.append(file_data)
            else:
                directories.append({"dirname": dir_entry.name})
        return jsonify(
            {
                "directories": directories,
                "files": files,
            }
        )


@api.route("/file_details", methods=["GET"])
def file_details() -> Union[str, Response]:
    filename = str(request.args.get("filename"))
    path = (config.get_files_directory() / filename).resolve()
    files_directory_resolved = config.get_files_directory().resolve()
    if (
        files_directory_resolved not in path.parents
        and path != files_directory_resolved
    ):
        abort(400)
    if not os.path.isfile(path):
        abort(400)
    sliced_model_file = read_cached_sliced_model_file(path)
    return jsonify(
        {
            "filename": sliced_model_file.filename,
            "path": filename,
            "bed_size_mm": list(sliced_model_file.bed_size_mm),
            "height_mm": round(sliced_model_file.height_mm, 4),
            "layer_count": sliced_model_file.layer_count,
            "layer_height_mm": round(sliced_model_file.layer_height_mm, 4),
            "resolution": list(sliced_model_file.resolution),
            "print_time_secs": sliced_model_file.print_time_secs,
        }
    )


@api.route("/upload_file", methods=["POST"])
def upload_file() -> Union[str, Response]:
    file = request.files.get("file")
    if file is None or file.filename == "":
        abort(400)
    file_filename: str = none_throws(file.filename)
    if get_file_extension(file_filename) not in get_supported_extensions():
        abort(400)
    filename = secure_filename(file_filename)

    path_parameter = str(request.args.get("path", "."))
    files_directory_resolved = config.get_files_directory().resolve()
    parent = (config.get_files_directory() / path_parameter).resolve()
    if (
        files_directory_resolved not in parent.parents
        and parent != files_directory_resolved
    ):
        abort(400)
    if not os.path.isdir(parent):
        abort(400)

    dest_path = (parent / filename).resolve()
    try:
        dest_path.relative_to(files_directory_resolved)
    except ValueError:
        abort(400)

    file.save(str(dest_path))
    os.sync()
    return jsonify({"success": True})


@api.route("/delete_file", methods=["POST"])
def delete_file() -> Union[str, Response]:
    filename = str(request.args.get("filename"))
    path = (config.get_files_directory() / filename).resolve()
    files_directory_resolved = config.get_files_directory().resolve()
    if (
        files_directory_resolved not in path.parents
        and path != files_directory_resolved
    ):
        abort(400)
    # we use os.path.isfile instead of Path.is_file here because pyfakefs doesn't
    # seem to properly mock Path.is_file as of pyfakefs 4.4.0
    if not os.path.isfile(path):
        abort(400)
    os.remove(path)
    return jsonify({"success": True})


@api.route("/create_directory", methods=["POST"])
def create_directory() -> Union[str, Response]:
    path_parameter = str(request.args.get("path", "."))
    raw_name = request.args.get("name", type=str)
    if raw_name is None or not raw_name.strip():
        abort(400)
    name_str = raw_name.strip()
    if "/" in name_str or "\\" in name_str or name_str in (".", ".."):
        abort(400)

    safe_name = secure_filename(name_str)
    if not safe_name or safe_name in (".", ".."):
        abort(400)

    files_directory_resolved = config.get_files_directory().resolve()
    parent = (config.get_files_directory() / path_parameter).resolve()
    if (
        files_directory_resolved not in parent.parents
        and parent != files_directory_resolved
    ):
        abort(400)
    if not os.path.isdir(parent):
        abort(400)

    new_path = (parent / safe_name).resolve()
    try:
        new_path.relative_to(files_directory_resolved)
    except ValueError:
        abort(400)

    try:
        os.mkdir(new_path)
    except FileExistsError:
        abort(400)
    return jsonify({"success": True})


@api.route("/file_preview", methods=["GET"])
def file_preview() -> Response:
    filename = str(request.args.get("filename"))
    path = (config.get_files_directory() / filename).resolve()
    files_directory_resolved = config.get_files_directory().resolve()
    if (
        files_directory_resolved not in path.parents
        and path != files_directory_resolved
    ):
        abort(400)
    if not os.path.isfile(path):
        abort(400)

    preview_bytes = read_cached_preview(path)

    response = make_response(preview_bytes)
    response.headers.set("Content-Type", "image/png")
    response.headers.set(
        "Content-Disposition", "attachment", filename=f"{filename}.png"
    )

    return response


class PrinterCommand(Enum):
    START_PRINT = "start_print"
    PAUSE_PRINT = "pause_print"
    RESUME_PRINT = "resume_print"
    CANCEL_PRINT = "cancel_print"
    REBOOT = "reboot"


@api.route("/printer/command/<command>", methods=["POST"])
def printer_command(command: str) -> Union[str, Response]:
    printer_command = PrinterCommand(command)
    with ChiTuPrinter() as printer:
        if printer_command == PrinterCommand.START_PRINT:
            # TODO: validate filename before sending it to the printer
            filename = str(request.args.get("filename"))
            printer.start_printing(filename)
        elif printer_command == PrinterCommand.PAUSE_PRINT:
            printer.pause_printing()
        elif printer_command == PrinterCommand.RESUME_PRINT:
            printer.resume_printing()
        elif printer_command == PrinterCommand.CANCEL_PRINT:
            printer.stop_printing()
        elif printer_command == PrinterCommand.REBOOT:
            printer.reboot()
        return jsonify({"success": True})


@api.route("/host/shutdown", methods=["POST"])
def host_shutdown() -> Union[str, Response]:
    logger.warning("Host shutdown requested via API")
    subprocess.Popen(["shutdown", "-h", "now"])
    return jsonify({"success": True})


@api.route("/host/reboot", methods=["POST"])
def host_reboot() -> Union[str, Response]:
    logger.warning("Host reboot requested via API")
    subprocess.Popen(["reboot"])
    return jsonify({"success": True})
