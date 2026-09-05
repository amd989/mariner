import logging
import multiprocessing
import os
from typing import Dict

from flask import abort, render_template
from waitress import serve

from mariner import config
from mariner.file_formats.utils import get_supported_extensions
from mariner.server.api import api as api_blueprint
from mariner.server.app import app as flask_app, csrf
from mariner.server.providers import register_providers
from mariner.server.utils import (
    read_cached_preview,
    read_cached_sliced_model_file,
)

from itertools import chain


flask_app.register_blueprint(api_blueprint)
register_providers(flask_app, csrf)


def render_index() -> str:
    template_vars: Dict[str, str] = {
        "supported_extensions": ",".join(get_supported_extensions()),
    }
    printer_display_name = config.get_printer_display_name()
    if printer_display_name is not None:
        template_vars["printer_display_name"] = printer_display_name
    return render_template("index.html", **template_vars)


@flask_app.route("/", methods=["GET"])
def index() -> str:
    return render_index()


@flask_app.get("/<path:spa_path>")
def spa_fallback(spa_path: str) -> str:
    # Let /api/* and provider routes pass through to their blueprints.
    if spa_path == "api" or spa_path.startswith("api/"):
        abort(404)
    from mariner.server.providers import get_provider_prefixes

    for prefix in get_provider_prefixes():
        if spa_path == prefix or spa_path.startswith(prefix + "/"):
            abort(404)
    return render_index()


class CacheBootstrapper(multiprocessing.Process):
    def run(self) -> None:
        os.nice(5)
        globs = [
            config.get_files_directory().rglob(f"*{extension}")
            for extension in get_supported_extensions()
        ]
        for file in chain.from_iterable(globs):
            read_cached_sliced_model_file(file.absolute())
            read_cached_preview(file.absolute())


def main() -> None:
    CacheBootstrapper().start()

    # Global log level applies to mariner.* and waitress output.
    log_level = getattr(logging, config.get_log_level(), logging.INFO)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=log_level)
    else:
        logging.getLogger().setLevel(log_level)
    logging.getLogger("mariner").setLevel(log_level)
    logging.getLogger("waitress").setLevel(log_level)

    serve(flask_app, host=config.get_http_host(), port=config.get_http_port())
