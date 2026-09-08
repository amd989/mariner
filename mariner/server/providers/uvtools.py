"""UVTools network print provider.

Exposes endpoints compatible with UVTools' remote printer feature.
UVTools sends raw binary file bodies (not multipart) and substitutes
``{0}`` in configured URL paths with the filename.  It only inspects
the HTTP status code, so successful responses return 200 with a short
JSON body.

Recommended UVTools configuration for Mariner
----------------------------------------------
Host : <Mariner IP>
Port : 5050  (or whatever ``mariner.conf`` sets)
Extensions : ctb;cbddlp;fdg;photon

=============  ======  =======================
Operation      Method  Request path
=============  ======  =======================
UploadFile     POST    uvtools/upload/{0}
PrintFile      GET     uvtools/print/{0}
DeleteFile     GET     uvtools/delete/{0}
PausePrint     GET     uvtools/pause
ResumePrint    GET     uvtools/resume
StopPrint      GET     uvtools/stop
GetFiles       GET     uvtools/files
PrintStatus    GET     uvtools/status
PrinterInfo    GET     uvtools/info
=============  ======  =======================
"""

import logging
import os
from typing import Union

import serial
from flask import Blueprint, Response, abort, jsonify, request

from mariner import config
from mariner.exceptions import UnexpectedPrinterResponse
from mariner.file_formats.utils import get_file_extension, get_supported_extensions
from mariner.printer import ChiTuPrinter, PrinterState
from mariner.server.providers.base import NetworkPrintProvider
from mariner.server.providers.filenames import safe_filename
from mariner.server.utils import read_cached_sliced_model_file, retry

logger: logging.Logger = logging.getLogger(__name__)


class UVToolsProvider(NetworkPrintProvider):
    @property
    def name(self) -> str:
        return "uvtools"

    def register_routes(self, blueprint: Blueprint) -> None:
        blueprint.add_url_rule(
            "/upload/<filename>",
            endpoint="upload_file",
            view_func=self._upload_file,
            methods=["POST", "PUT"],
        )
        blueprint.add_url_rule(
            "/print/<filename>",
            endpoint="print_file",
            view_func=self._print_file,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/delete/<filename>",
            endpoint="delete_file",
            view_func=self._delete_file,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/pause",
            endpoint="pause_print",
            view_func=self._pause_print,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/pause/<filename>",
            endpoint="pause_print_with_file",
            view_func=self._pause_print,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/resume",
            endpoint="resume_print",
            view_func=self._resume_print,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/resume/<filename>",
            endpoint="resume_print_with_file",
            view_func=self._resume_print,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/stop",
            endpoint="stop_print",
            view_func=self._stop_print,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/stop/<filename>",
            endpoint="stop_print_with_file",
            view_func=self._stop_print,
            methods=["GET", "POST"],
        )
        blueprint.add_url_rule(
            "/files",
            endpoint="get_files",
            view_func=self._get_files,
            methods=["GET"],
        )
        blueprint.add_url_rule(
            "/status",
            endpoint="print_status",
            view_func=self._print_status,
            methods=["GET"],
        )
        blueprint.add_url_rule(
            "/info",
            endpoint="printer_info",
            view_func=self._printer_info,
            methods=["GET"],
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _upload_file(self, filename: str) -> Union[str, Response]:
        """Accept a raw-binary file upload.

        UVTools streams the file bytes directly in the request body
        (no multipart, no form fields).  The filename comes from the
        URL path.
        """
        safe_name = safe_filename(filename)
        if safe_name is None:
            logger.warning("UVTools: refusing unsafe filename %r", filename)
            abort(400)

        ext = get_file_extension(safe_name)
        if ext not in get_supported_extensions():
            abort(400)

        files_dir = config.get_files_directory().resolve()
        dest = (files_dir / safe_name).resolve()
        try:
            dest.relative_to(files_dir)
        except ValueError:
            abort(400)

        data = request.get_data()
        if not data:
            abort(400)

        dest.write_bytes(data)
        try:
            os.sync()
        except AttributeError:
            pass

        logger.info("UVTools upload: %s (%d bytes)", safe_name, len(data))
        return jsonify({"success": True, "filename": safe_name})

    def _print_file(self, filename: str) -> Union[str, Response]:
        safe_name = safe_filename(filename)
        if safe_name is None:
            logger.warning("UVTools: refusing unsafe filename %r", filename)
            abort(400)

        file_path = config.get_files_directory() / safe_name
        if not os.path.isfile(file_path):
            abort(404)

        with ChiTuPrinter() as printer:
            printer.start_printing(safe_name)

        logger.info("UVTools print: %s", safe_name)
        return jsonify({"success": True})

    def _delete_file(self, filename: str) -> Union[str, Response]:
        safe_name = safe_filename(filename)
        if safe_name is None:
            logger.warning("UVTools: refusing unsafe filename %r", filename)
            abort(400)

        files_dir = config.get_files_directory().resolve()
        path = (files_dir / safe_name).resolve()
        try:
            path.relative_to(files_dir)
        except ValueError:
            abort(400)

        if not os.path.isfile(path):
            abort(404)

        os.remove(path)
        logger.info("UVTools delete: %s", safe_name)
        return jsonify({"success": True})

    def _pause_print(self, filename: str = "") -> Union[str, Response]:
        with ChiTuPrinter() as printer:
            printer.pause_printing()
        logger.info("UVTools pause")
        return jsonify({"success": True})

    def _resume_print(self, filename: str = "") -> Union[str, Response]:
        with ChiTuPrinter() as printer:
            printer.resume_printing()
        logger.info("UVTools resume")
        return jsonify({"success": True})

    def _stop_print(self, filename: str = "") -> Union[str, Response]:
        with ChiTuPrinter() as printer:
            printer.stop_printing()
        logger.info("UVTools stop")
        return jsonify({"success": True})

    def _get_files(self) -> Union[str, Response]:
        files_dir = config.get_files_directory()
        supported = get_supported_extensions()
        file_list = []

        with os.scandir(files_dir) as entries:
            for entry in sorted(entries, key=lambda e: e.stat().st_mtime, reverse=True):
                if entry.is_file() and get_file_extension(entry.name) in supported:
                    file_list.append(entry.name)

        return jsonify({"files": file_list})

    def _print_status(self) -> Union[str, Response]:
        transient_errors = (UnexpectedPrinterResponse, serial.SerialException)
        try:
            with ChiTuPrinter() as printer:
                status = retry(
                    printer.get_print_status, transient_errors, num_retries=3
                )
                selected_file = retry(
                    printer.get_selected_file, transient_errors, num_retries=3
                )
        except transient_errors:
            return jsonify({"state": PrinterState.CLOSED.value})

        result = {
            "state": status.state.value,
            "selected_file": selected_file,
        }

        if (
            status.state not in (PrinterState.IDLE, PrinterState.CLOSED)
            and selected_file
        ):
            try:
                sliced = read_cached_sliced_model_file(
                    config.get_files_directory() / selected_file
                )
                layer_count = sliced.layer_count or 0
                progress = 0.0
                if (
                    status.current_byte
                    and status.total_bytes
                    and status.total_bytes > 0
                ):
                    progress = 100.0 * status.current_byte / status.total_bytes
                result.update(
                    {
                        "progress": round(progress, 2),
                        "layer_count": layer_count,
                        "print_time_secs": sliced.print_time_secs,
                    }
                )
            except Exception:
                pass

        return jsonify(result)

    def _printer_info(self) -> Union[str, Response]:
        info = {
            "name": config.get_printer_display_name() or "Mariner",
            "extensions": list(get_supported_extensions()),
        }

        try:
            with ChiTuPrinter() as printer:
                info["firmware"] = printer.get_firmware_version()
        except Exception:
            pass

        return jsonify(info)
