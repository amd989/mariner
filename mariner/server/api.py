import os
import traceback
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Union

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
from mariner.printer import ChiTuPrinter, PrinterState
from mariner.server.utils import (
    read_cached_preview,
    read_cached_sliced_model_file,
    retry,
)


api = Blueprint("api", __name__, url_prefix="/api")

# Tracks M4000 D: first field across HTTP requests so we can tell "bytes read"
# vs "bytes remaining" firmware (see print_status).
_m4000_prev: Optional[Tuple[int, int]] = None
_m4000_interpretation: Optional[str] = None


def reset_m4000_d_tracking() -> None:
    """Clear M4000 D: interpretation state (e.g. between tests)."""
    global _m4000_prev, _m4000_interpretation
    _m4000_prev = None
    _m4000_interpretation = None


def _file_byte_for_layer_lookup(
    current_byte: int,
    total_bytes: int,
    state: PrinterState,
) -> int:
    """Map M4000 D: first value to a byte offset for end_byte_offset_by_layer."""
    global _m4000_prev, _m4000_interpretation

    if state in (PrinterState.IDLE, PrinterState.CLOSED) or total_bytes == 0:
        reset_m4000_d_tracking()
        return current_byte

    if current_byte == 0:
        _m4000_prev = (0, total_bytes)
        return 0

    if _m4000_prev is not None and _m4000_prev[1] != total_bytes:
        _m4000_interpretation = None

    mode = config.get_m4000_d_field()
    if mode == "read":
        file_pos = current_byte
    elif mode == "remaining":
        file_pos = total_bytes - current_byte
    else:
        prev_cb, prev_tb = _m4000_prev if _m4000_prev else (None, None)
        if prev_tb == total_bytes and prev_cb is not None:
            if prev_cb == 0 and current_byte > 0:
                if current_byte > int(total_bytes * 0.85):
                    _m4000_interpretation = "remaining"
                else:
                    _m4000_interpretation = "read"
            elif prev_cb > 0:
                if current_byte < prev_cb:
                    _m4000_interpretation = "remaining"
                elif current_byte > prev_cb:
                    _m4000_interpretation = "read"
        if _m4000_interpretation == "remaining":
            file_pos = total_bytes - current_byte
        else:
            file_pos = current_byte

    _m4000_prev = (current_byte, total_bytes)
    return max(0, file_pos)


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
        print_status = retry(
            printer.get_print_status,
            UnexpectedPrinterResponse,
            num_retries=3,
        )

        selected_file = retry(
            printer.get_selected_file,
            UnexpectedPrinterResponse,
            num_retries=3,
        )

        if (
            print_status.state == PrinterState.IDLE
            or print_status.state == PrinterState.CLOSED
        ):
            progress = 0.0
            print_details = {}
        else:
            sliced_model_file = read_cached_sliced_model_file(
                config.get_files_directory() / selected_file
            )

            current_byte = print_status.current_byte or 0
            total_bytes = print_status.total_bytes or 0
            file_byte = _file_byte_for_layer_lookup(
                current_byte, total_bytes, print_status.state
            )
            if file_byte == 0:
                current_layer = 1
            else:
                # Find the layer corresponding to file_byte position (see
                # _file_byte_for_layer_lookup for M4000 D: read vs remaining).
                current_layer = 1
                end_byte_offsets = sliced_model_file.end_byte_offset_by_layer
                for i, end_byte in enumerate(end_byte_offsets):
                    if file_byte <= end_byte:
                        current_layer = i + 1
                        break
                else:
                    # If file_byte is beyond all layers, use the last layer
                    current_layer = len(end_byte_offsets)

            progress = (
                100.0
                * none_throws(current_layer - 1)
                / none_throws(sliced_model_file.layer_count)
            )

            print_details = {
                "current_layer": current_layer,
                "layer_count": sliced_model_file.layer_count,
                "print_time_secs": sliced_model_file.print_time_secs,
                "time_left_secs": round(
                    sliced_model_file.print_time_secs * (100.0 - progress) / 100.0
                ),
            }

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
                    if dir_entry.name.startswith("._"):
                        if b"Mac OS X" not in open(dir_entry.path, "rb").read(32):
                            sliced_model_file = read_cached_sliced_model_file(
                                path / dir_entry.name
                            )
                    else:
                        sliced_model_file = read_cached_sliced_model_file(
                            path / dir_entry.name
                        )

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
