import os
import pathlib
from typing import Any
from unittest.mock import Mock, patch

from flask.testing import FlaskClient
from pyfakefs.fake_filesystem import FakeFilesystem
from pyfakefs.fake_filesystem_unittest import TestCase
from pyexpect import expect

from mariner import config
from mariner.config import _get_config
from mariner.printer import ChiTuPrinter, PrinterState, PrintStatus
from mariner.server.app import app


class UVToolsProviderTest(TestCase):
    ctb_file_contents: bytes
    client: FlaskClient
    fs: FakeFilesystem
    printer_mock: Any
    printer_patcher: Any

    def setUp(self) -> None:
        path = (
            pathlib.Path(__file__).parent.parent.parent.parent.absolute()
            / "file_formats"
            / "tests"
            / "stairs.ctb"
        )
        with open(path, "rb") as f:
            self.ctb_file_contents = f.read()

        _get_config.cache_clear()
        self.setUpPyfakefs(
            additional_skip_names=["importlib.metadata"],
        )
        self.fs.create_file(
            "/mnt/usb_share/foobar.ctb", contents=self.ctb_file_contents
        )

        self.client = app.test_client()
        app.config["WTF_CSRF_ENABLED"] = False

        self.printer_mock = Mock(spec=ChiTuPrinter)
        self.printer_patcher = patch("mariner.server.providers.uvtools.ChiTuPrinter")
        printer_constructor_mock = self.printer_patcher.start()
        printer_constructor_mock.return_value = self.printer_mock
        self.printer_mock.__enter__ = Mock(return_value=self.printer_mock)
        self.printer_mock.__exit__ = Mock(return_value=None)

    def tearDown(self) -> None:
        self.printer_patcher.stop()

    # ---- Upload ----

    def test_upload_file_via_post(self) -> None:
        response = self.client.post(
            "/uvtools/upload/mymodel.ctb",
            data=self.ctb_file_contents,
            content_type="application/octet-stream",
        )
        expect(response.status_code).to_equal(200)
        expect(response.get_json()["success"]).to_equal(True)
        expect(os.path.isfile(config.get_files_directory() / "mymodel.ctb")).to_equal(
            True
        )

    def test_upload_file_via_put(self) -> None:
        response = self.client.put(
            "/uvtools/upload/mymodel.ctb",
            data=self.ctb_file_contents,
            content_type="application/octet-stream",
        )
        expect(response.status_code).to_equal(200)
        expect(response.get_json()["success"]).to_equal(True)

    def test_upload_file_rejects_unsupported_extension(self) -> None:
        response = self.client.post(
            "/uvtools/upload/image.jpg",
            data=b"fake",
            content_type="application/octet-stream",
        )
        expect(response.status_code).to_equal(400)

    def test_upload_file_rejects_empty_body(self) -> None:
        response = self.client.post(
            "/uvtools/upload/mymodel.ctb",
            data=b"",
            content_type="application/octet-stream",
        )
        expect(response.status_code).to_equal(400)

    def test_upload_file_sanitizes_dangerous_filename(self) -> None:
        response = self.client.post(
            "/uvtools/upload/.._.._etc_passwd.ctb",
            data=b"fake-ctb-data",
            content_type="application/octet-stream",
        )
        expect(response.status_code).to_equal(200)
        expect(
            os.path.isfile(config.get_files_directory() / "etc_passwd.ctb")
        ).to_equal(True)

    # ---- Print ----

    def test_print_file(self) -> None:
        response = self.client.get("/uvtools/print/foobar.ctb")
        expect(response.status_code).to_equal(200)
        expect(response.get_json()).to_equal({"success": True})
        self.printer_mock.start_printing.assert_called_once_with("foobar.ctb")

    def test_print_file_not_found(self) -> None:
        response = self.client.get("/uvtools/print/missing.ctb")
        expect(response.status_code).to_equal(404)

    # ---- Delete ----

    def test_delete_file(self) -> None:
        expect(os.path.isfile(config.get_files_directory() / "foobar.ctb")).to_equal(
            True
        )
        response = self.client.get("/uvtools/delete/foobar.ctb")
        expect(response.status_code).to_equal(200)
        expect(os.path.isfile(config.get_files_directory() / "foobar.ctb")).to_equal(
            False
        )

    def test_delete_file_not_found(self) -> None:
        response = self.client.get("/uvtools/delete/nope.ctb")
        expect(response.status_code).to_equal(404)

    # ---- Pause / Resume / Stop ----

    def test_pause_print(self) -> None:
        response = self.client.get("/uvtools/pause")
        expect(response.status_code).to_equal(200)
        self.printer_mock.pause_printing.assert_called_once()

    def test_pause_print_with_filename(self) -> None:
        response = self.client.get("/uvtools/pause/foobar.ctb")
        expect(response.status_code).to_equal(200)
        self.printer_mock.pause_printing.assert_called_once()

    def test_resume_print(self) -> None:
        response = self.client.get("/uvtools/resume")
        expect(response.status_code).to_equal(200)
        self.printer_mock.resume_printing.assert_called_once()

    def test_stop_print(self) -> None:
        response = self.client.get("/uvtools/stop")
        expect(response.status_code).to_equal(200)
        self.printer_mock.stop_printing.assert_called_once()

    def test_stop_print_with_filename(self) -> None:
        response = self.client.get("/uvtools/stop/foobar.ctb")
        expect(response.status_code).to_equal(200)
        self.printer_mock.stop_printing.assert_called_once()

    # ---- Get Files ----

    def test_get_files(self) -> None:
        response = self.client.get("/uvtools/files")
        expect(response.status_code).to_equal(200)
        data = response.get_json()
        expect("foobar.ctb" in data["files"]).to_equal(True)

    # ---- Print Status ----

    def test_print_status_printing(self) -> None:
        self.printer_mock.get_selected_file.return_value = "foobar.ctb"
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.PRINTING,
            current_byte=256537,
            total_bytes=832745,
        )
        response = self.client.get("/uvtools/status")
        expect(response.status_code).to_equal(200)
        data = response.get_json()
        expect(data["state"]).to_equal("PRINTING")
        expect(data["selected_file"]).to_equal("foobar.ctb")

    def test_print_status_idle(self) -> None:
        self.printer_mock.get_selected_file.return_value = ""
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.IDLE,
        )
        response = self.client.get("/uvtools/status")
        expect(response.status_code).to_equal(200)
        data = response.get_json()
        expect(data["state"]).to_equal("IDLE")

    # ---- Printer Info ----

    def test_printer_info(self) -> None:
        self.printer_mock.get_firmware_version.return_value = "V4.9.2"
        response = self.client.get("/uvtools/info")
        expect(response.status_code).to_equal(200)
        data = response.get_json()
        expect(data["name"]).to_equal("Mariner")
        expect(data["firmware"]).to_equal("V4.9.2")
        expect(".ctb" in data["extensions"]).to_equal(True)
