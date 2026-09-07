import hashlib
import json
import os
import pathlib
import re
from typing import Any
from unittest.mock import Mock, patch

from pyexpect import expect
from pyfakefs.fake_filesystem import FakeFilesystem
from pyfakefs.fake_filesystem_unittest import TestCase

from mariner import config
from mariner.config import _get_config
from mariner.exceptions import UnexpectedPrinterResponse
from mariner.printer import ChiTuPrinter, PrinterState, PrintStatus
from mariner.server.providers.sdcp import constants, identity, messages
from mariner.server.providers.sdcp.bridge import PrinterBridge, strip_storage_prefix
from mariner.server.providers.sdcp.uploads import UploadManager


class StripStoragePrefixTest(TestCase):
    def test_strips_local_prefix(self) -> None:
        expect(strip_storage_prefix("/local/foo.ctb")).to_equal("foo.ctb")

    def test_strips_usb_prefix(self) -> None:
        expect(strip_storage_prefix("/usb/nested/foo.ctb")).to_equal("nested/foo.ctb")

    def test_leaves_bare_name_alone(self) -> None:
        expect(strip_storage_prefix("foo.ctb")).to_equal("foo.ctb")

    def test_strips_leading_slash(self) -> None:
        expect(strip_storage_prefix("/foo.ctb")).to_equal("foo.ctb")

    def test_handles_empty(self) -> None:
        expect(strip_storage_prefix("")).to_equal("")


class MessageEnvelopeTest(TestCase):
    def setUp(self) -> None:
        _get_config.cache_clear()
        identity._machine_seed.cache_clear()

    def test_response_envelope_shape(self) -> None:
        message = messages.response(constants.Cmd.START_PRINT, {"Ack": 0}, "req-1")
        expect(message["Topic"]).to_equal(
            f"sdcp/response/{identity.get_mainboard_id()}"
        )
        expect(message["Data"]["Cmd"]).to_equal(128)
        expect(message["Data"]["Data"]).to_equal({"Ack": 0})
        expect(message["Data"]["RequestID"]).to_equal("req-1")
        expect(message["Data"]["MainboardID"]).to_equal(identity.get_mainboard_id())

    def test_status_envelope_has_no_id_field(self) -> None:
        message = messages.status({"CurrentStatus": [0]})
        expect("Id" in message).to_equal(False)
        expect(message["Topic"]).to_equal(f"sdcp/status/{identity.get_mainboard_id()}")
        expect(message["Status"]).to_equal({"CurrentStatus": [0]})

    def test_attributes_envelope_has_no_id_field(self) -> None:
        message = messages.attributes({"Name": "Mariner"})
        expect("Id" in message).to_equal(False)
        expect(message["Topic"]).to_equal(
            f"sdcp/attributes/{identity.get_mainboard_id()}"
        )

    def test_error_envelope_nests_under_data(self) -> None:
        message = messages.error(int(constants.ErrorCode.MD5_FAILED))
        expect(message["Data"]["Data"]["ErrorCode"]).to_equal(1)
        expect(message["Topic"]).to_equal(f"sdcp/error/{identity.get_mainboard_id()}")

    def test_discovery_response_shape(self) -> None:
        message = messages.discovery_response(
            name="My Printer",
            machine_name="Mars 3",
            brand_name="CBD",
            mainboard_ip="192.168.1.5",
            firmware_version="V1.0.0",
            protocol_version="V3.0.0",
        )
        expect(message["Data"]["Name"]).to_equal("My Printer")
        expect(message["Data"]["MainboardIP"]).to_equal("192.168.1.5")
        expect(message["Data"]["ProtocolVersion"]).to_equal("V3.0.0")
        expect(message["Data"]["MainboardID"]).to_equal(identity.get_mainboard_id())
        # Discovery replies must be a single UDP datagram of valid JSON.
        expect(json.loads(json.dumps(message))).to_equal(message)

    def test_discovery_omits_internal_machine_name_by_default(self) -> None:
        message = messages.discovery_response(
            name="My Printer",
            machine_name="ELEGOO Mars 3",
            brand_name="ELEGOO",
            mainboard_ip="192.168.1.5",
            firmware_version="V1.0.0",
            protocol_version="V3.0.0",
        )
        expect("InternalMachineName" in message["Data"]).to_equal(False)

    def test_discovery_includes_internal_machine_name_when_set(self) -> None:
        message = messages.discovery_response(
            name="My Printer",
            machine_name="ELEGOO Mars 3",
            brand_name="ELEGOO",
            mainboard_ip="192.168.1.5",
            firmware_version="V1.0.0",
            protocol_version="V3.0.0",
            internal_machine_name="Mars 3",
        )
        expect(message["Data"]["InternalMachineName"]).to_equal("Mars 3")
        expect(message["Data"]["BrandName"]).to_equal("ELEGOO")

    def test_client_picture_key_resolves_on_both_lookup_paths(self) -> None:
        """ChituManager derives its image key two different ways.

        Discovery uses BrandName + (InternalMachineName or MachineName);
        attributes uses (InternalMachineName or MachineName) alone. Both must
        normalise to the same key or the printer falls back to a generic
        picture.
        """

        def normalise(value: str) -> str:
            return re.sub(r"\s*", "", value).lower()

        brand = "ELEGOO"
        machine_name = "ELEGOO Mars 3"
        internal = "Mars 3"

        discovery_key = normalise(brand + internal)
        # Attributes deliberately carry no InternalMachineName.
        attributes_key = normalise(machine_name)

        expect(discovery_key).to_equal("elegoomars3")
        expect(attributes_key).to_equal("elegoomars3")

    def test_upload_success_payload(self) -> None:
        expect(messages.upload_success()).to_equal(
            {
                "code": "000000",
                "messages": None,
                "data": {},
                "success": True,
            }
        )

    def test_upload_failure_payload(self) -> None:
        payload = messages.upload_failure(constants.UploadError.OFFSET_MISMATCH)
        expect(payload["success"]).to_equal(False)
        expect(payload["code"]).to_equal("111111")
        expect(payload["messages"][0]["message"]).to_equal(-2)


class SDCPBridgeTest(TestCase):
    ctb_file_contents: bytes
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
        self.setUpPyfakefs(additional_skip_names=["importlib.metadata"])
        self.fs.create_file(
            "/mnt/usb_share/foobar.ctb", contents=self.ctb_file_contents
        )

        self.printer_mock = Mock(spec=ChiTuPrinter)
        self.printer_patcher = patch(
            "mariner.server.providers.sdcp.bridge.ChiTuPrinter"
        )
        constructor = self.printer_patcher.start()
        constructor.return_value = self.printer_mock
        self.printer_mock.__enter__ = Mock(return_value=self.printer_mock)
        self.printer_mock.__exit__ = Mock(return_value=None)

        self.bridge = PrinterBridge()

    def tearDown(self) -> None:
        self.printer_patcher.stop()

    def test_status_while_idle(self) -> None:
        self.printer_mock.get_selected_file.return_value = ""
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.IDLE
        )
        status = self.bridge.snapshot_status()
        expect(status["CurrentStatus"]).to_equal([int(constants.MachineStatus.IDLE)])
        expect(status["PrintInfo"]["Status"]).to_equal(int(constants.PrintStatus.IDLE))

    def test_status_while_printing_reports_layers(self) -> None:
        self.printer_mock.get_selected_file.return_value = "foobar.ctb"
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.PRINTING,
            current_byte=256537,
            total_bytes=832745,
        )
        status = self.bridge.snapshot_status()
        expect(status["CurrentStatus"]).to_equal(
            [int(constants.MachineStatus.PRINTING)]
        )
        expect(status["PrintInfo"]["Status"]).to_equal(
            int(constants.PrintStatus.EXPOSURING)
        )
        expect(status["PrintInfo"]["TotalLayer"]).to_equal(400)
        expect(status["PrintInfo"]["CurrentLayer"]).to_equal(130)
        expect(status["PrintInfo"]["Filename"]).to_equal("foobar.ctb")
        expect(status["PrintInfo"]["TotalTicks"]).to_equal(5621 * 1000)

    def test_status_while_paused(self) -> None:
        self.printer_mock.get_selected_file.return_value = "foobar.ctb"
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.PAUSED,
            current_byte=256537,
            total_bytes=832745,
        )
        status = self.bridge.snapshot_status()
        expect(status["PrintInfo"]["Status"]).to_equal(
            int(constants.PrintStatus.PAUSED)
        )

    def test_status_reports_file_transfer(self) -> None:
        self.printer_mock.get_selected_file.return_value = ""
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.IDLE
        )
        status = self.bridge.snapshot_status(transferring=True)
        expect(status["CurrentStatus"]).to_equal(
            [int(constants.MachineStatus.FILE_TRANSFERRING)]
        )

    def test_attributes_advertise_supported_types(self) -> None:
        self.printer_mock.get_selected_file.return_value = ""
        self.printer_mock.get_print_status.return_value = PrintStatus(
            state=PrinterState.IDLE
        )
        attributes = self.bridge.snapshot_attributes()
        expect("CTB" in attributes["SupportFileType"]).to_equal(True)
        expect(attributes["ProtocolVersion"]).to_equal("V3.0.0")
        expect(attributes["MainboardID"]).to_equal(identity.get_mainboard_id())
        expect("FILE_TRANSFER" in attributes["Capabilities"]).to_equal(True)
        expect("PRINT_CONTROL" in attributes["Capabilities"]).to_equal(True)

    def test_absent_hardware_is_omitted_not_reported_broken(self) -> None:
        # SDCP's 0 means "disconnected", which clients show as a fault, so
        # hardware a Mars 3 does not have must be left out entirely rather
        # than reported as 0.
        devices = self.bridge.snapshot_attributes()["DevicesStatus"]
        expect("XMotorStatus" in devices).to_equal(False)
        expect("RotateMotorStatus" in devices).to_equal(False)

    def test_devices_present_on_every_printer_report_healthy(self) -> None:
        devices = self.bridge.snapshot_attributes()["DevicesStatus"]
        expect(devices["ZMotorStatus"]).to_equal(1)
        expect(devices["LCDStatus"]).to_equal(1)
        expect(devices["TempSensorStatusOfUVLED"]).to_equal(1)
        expect(devices["RelaseFilmState"]).to_equal(1)
        expect(devices["SgStatus"]).to_equal(1)

    def test_optional_hardware_is_reported_when_configured(self) -> None:
        with patch.object(config, "get_sdcp_optional_devices", lambda: ["x_motor"]):
            devices = self.bridge.snapshot_attributes()["DevicesStatus"]
        expect(devices["XMotorStatus"]).to_equal(1)
        # Only what was configured; the rotary axis stays omitted.
        expect("RotateMotorStatus" in devices).to_equal(False)

    def test_both_optional_devices_can_be_enabled(self) -> None:
        with patch.object(
            config,
            "get_sdcp_optional_devices",
            lambda: ["x_motor", "rotate_motor"],
        ):
            devices = self.bridge.snapshot_attributes()["DevicesStatus"]
        expect(devices["XMotorStatus"]).to_equal(1)
        expect(devices["RotateMotorStatus"]).to_equal(1)

    def test_firmware_version_is_read_from_the_printer(self) -> None:
        self.printer_mock.get_firmware_version.return_value = "V4.5.0_1.0_e13_LCDE1"
        attributes = self.bridge.snapshot_attributes()
        expect(attributes["FirmwareVersion"]).to_equal("V4.5.0_1.0_e13_LCDE1")

    def test_firmware_version_is_read_only_once(self) -> None:
        self.printer_mock.get_firmware_version.return_value = "V4.5.0"
        self.bridge.firmware_version()
        self.bridge.firmware_version()
        self.bridge.firmware_version()
        # Serial is contended, and the version cannot change while running.
        expect(self.printer_mock.get_firmware_version.call_count).to_equal(1)

    def test_configured_firmware_version_wins(self) -> None:
        self.printer_mock.get_firmware_version.return_value = "V4.5.0"
        with patch.object(config, "get_sdcp_firmware_version", lambda: "V9.9.9"):
            expect(self.bridge.firmware_version()).to_equal("V9.9.9")
        self.printer_mock.get_firmware_version.assert_not_called()

    def test_firmware_version_falls_back_when_printer_is_unreachable(self) -> None:
        self.printer_mock.get_firmware_version.side_effect = UnexpectedPrinterResponse(
            "garbage"
        )
        expect(self.bridge.firmware_version()).to_equal("V1.0.0")

    def test_geometry_skips_an_unreadable_file(self) -> None:
        # A corrupt upload must not leave the printer advertising 0x0 when a
        # readable file is also present.
        self.fs.create_file("/mnt/usb_share/corrupt.ctb", contents="garbage")
        os.utime("/mnt/usb_share/corrupt.ctb", (2_000_000_000, 2_000_000_000))

        attributes = self.bridge.snapshot_attributes()
        expect(attributes["Resolution"]).to_equal("1440x2560")
        expect(attributes["XYZsize"]).to_equal("68.04x120.96x150")

    def test_geometry_falls_back_when_nothing_is_readable(self) -> None:
        os.remove("/mnt/usb_share/foobar.ctb")
        self.fs.create_file("/mnt/usb_share/corrupt.ctb", contents="garbage")

        attributes = self.bridge.snapshot_attributes()
        expect(attributes["Resolution"]).to_equal("0x0")
        expect(attributes["XYZsize"]).to_equal("0x0x0")

    def test_configured_geometry_wins_over_derivation(self) -> None:
        with patch.object(config, "get_sdcp_resolution", lambda: "4098x2560"):
            with patch.object(config, "get_sdcp_xyz_size", lambda: "143.43x89.6x175"):
                attributes = self.bridge.snapshot_attributes()
        expect(attributes["Resolution"]).to_equal("4098x2560")
        expect(attributes["XYZsize"]).to_equal("143.43x89.6x175")

    def test_attributes_never_carry_internal_machine_name(self) -> None:
        # ChituManager's attributes lookup omits BrandName, so MachineName
        # alone has to be the full key; an InternalMachineName here would
        # shadow it and break the picture match.
        attributes = self.bridge.snapshot_attributes()
        expect("InternalMachineName" in attributes).to_equal(False)

    def test_attributes_derive_geometry_from_sliced_file(self) -> None:
        attributes = self.bridge.snapshot_attributes()
        expect(attributes["Resolution"]).to_equal("1440x2560")
        expect(attributes["XYZsize"]).to_equal("68.04x120.96x150")

    def test_start_print_dispatches_to_printer(self) -> None:
        ack = self.bridge.start_print("/local/foobar.ctb")
        expect(ack).to_equal(int(constants.PrintCtrlAck.OK))
        self.printer_mock.start_printing.assert_called_once_with("foobar.ctb")

    def test_start_print_missing_file(self) -> None:
        ack = self.bridge.start_print("/local/nope.ctb")
        expect(ack).to_equal(int(constants.PrintCtrlAck.NOT_FOUND))
        self.printer_mock.start_printing.assert_not_called()

    def test_start_print_rejects_path_traversal(self) -> None:
        ack = self.bridge.start_print("/local/../../etc/passwd")
        expect(ack).to_equal(int(constants.PrintCtrlAck.NOT_FOUND))
        self.printer_mock.start_printing.assert_not_called()

    def test_pause_resume_stop(self) -> None:
        expect(self.bridge.pause_print()).to_equal(int(constants.PrintCtrlAck.OK))
        self.printer_mock.pause_printing.assert_called_once()

        expect(self.bridge.resume_print()).to_equal(int(constants.PrintCtrlAck.OK))
        self.printer_mock.resume_printing.assert_called_once()

        expect(self.bridge.stop_print()).to_equal(int(constants.PrintCtrlAck.OK))
        self.printer_mock.stop_printing.assert_called_once()

    def test_list_files(self) -> None:
        self.fs.create_dir("/mnt/usb_share/nested")
        self.fs.create_file("/mnt/usb_share/notes.txt", contents="ignored")

        entries = self.bridge.list_files("/local/")
        names = {entry["name"]: entry for entry in entries}

        expect("/local/foobar.ctb" in names).to_equal(True)
        expect(names["/local/foobar.ctb"]["type"]).to_equal(1)
        expect("/local/nested" in names).to_equal(True)
        expect(names["/local/nested"]["type"]).to_equal(0)
        # Unprintable files are filtered out by the mainboard per the spec.
        expect("/local/notes.txt" in names).to_equal(False)

    def test_list_files_rejects_escape(self) -> None:
        expect(self.bridge.list_files("/local/../../etc")).to_equal([])

    def test_delete_files(self) -> None:
        failures = self.bridge.delete(["/local/foobar.ctb"], [])
        expect(failures).to_equal([])
        expect(pathlib.Path("/mnt/usb_share/foobar.ctb").exists()).to_equal(False)

    def test_delete_reports_failures(self) -> None:
        failures = self.bridge.delete(["/local/missing.ctb"], [])
        expect(failures).to_equal(["/local/missing.ctb"])

    def test_delete_refuses_to_remove_root(self) -> None:
        failures = self.bridge.delete([], ["/local/"])
        expect(failures).to_equal(["/local/"])
        expect(pathlib.Path("/mnt/usb_share").is_dir()).to_equal(True)


class UploadManagerTest(TestCase):
    fs: FakeFilesystem

    def setUp(self) -> None:
        _get_config.cache_clear()
        self.setUpPyfakefs(additional_skip_names=["importlib.metadata"])
        self.fs.create_dir("/mnt/usb_share")
        self.manager = UploadManager()

    def _upload(
        self,
        data: bytes,
        *,
        filename: str = "model.ctb",
        chunk_size: int = 1024,
        verify: bool = True,
        md5: str = "",
        upload_uuid: str = "abc",
    ) -> Any:
        digest = md5 or hashlib.md5(data).hexdigest()
        result = None
        for offset in range(0, len(data), chunk_size):
            end = offset + chunk_size
            result = self.manager.handle_chunk(
                upload_uuid=upload_uuid,
                filename=filename,
                offset=offset,
                total_size=len(data),
                expected_md5=digest,
                verify=verify,
                data=data[offset:end],
            )
            if not result.ok:
                return result
        return result

    def test_single_chunk_upload(self) -> None:
        payload = b"x" * 512
        result = self._upload(payload)
        expect(result.ok).to_equal(True)
        expect(result.completed).to_equal(True)
        expect(result.filename).to_equal("model.ctb")
        expect(pathlib.Path("/mnt/usb_share/model.ctb").read_bytes()).to_equal(payload)

    def test_multi_chunk_upload_is_reassembled_in_order(self) -> None:
        payload = bytes(range(256)) * 40
        result = self._upload(payload, chunk_size=1024)
        expect(result.ok).to_equal(True)
        expect(result.completed).to_equal(True)
        expect(pathlib.Path("/mnt/usb_share/model.ctb").read_bytes()).to_equal(payload)

    def test_transferring_flag_tracks_active_upload(self) -> None:
        expect(self.manager.is_transferring()).to_equal(False)
        self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=2048,
            expected_md5="",
            verify=False,
            data=b"y" * 1024,
        )
        expect(self.manager.is_transferring()).to_equal(True)
        self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=1024,
            total_size=2048,
            expected_md5="",
            verify=False,
            data=b"y" * 1024,
        )
        expect(self.manager.is_transferring()).to_equal(False)

    def test_padding_past_total_size_is_dropped(self) -> None:
        # ChiTuBox pads the final packet. Writing the padding makes the file
        # longer than the original, which breaks encrypted CTB parsing since
        # its checksum is read by seeking back from the end.
        payload = b"real-ctb-payload" * 8
        result = self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=len(payload),
            expected_md5="",
            verify=False,
            data=payload + b"\x00\x01\x02\x03",
        )
        expect(result.ok).to_equal(True)
        expect(result.completed).to_equal(True)
        landed = pathlib.Path("/mnt/usb_share/model.ctb").read_bytes()
        expect(len(landed)).to_equal(len(payload))
        expect(landed).to_equal(payload)

    def test_padding_on_the_last_of_several_chunks_is_dropped(self) -> None:
        payload = bytes(range(256)) * 8
        half = len(payload) // 2
        self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=len(payload),
            expected_md5="",
            verify=False,
            data=payload[:half],
        )
        result = self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=half,
            total_size=len(payload),
            expected_md5="",
            verify=False,
            data=payload[half:] + b"\xde\xad\xbe\xef",
        )
        expect(result.completed).to_equal(True)
        expect(pathlib.Path("/mnt/usb_share/model.ctb").read_bytes()).to_equal(payload)

    def test_md5_is_checked_against_the_unpadded_file(self) -> None:
        payload = b"exactly-this-content" * 4
        digest = hashlib.md5(payload).hexdigest()
        result = self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=len(payload),
            expected_md5=digest,
            verify=True,
            data=payload + b"\x00\x00\x00\x00",
        )
        expect(result.ok).to_equal(True)
        expect(result.md5_failed).to_equal(False)

    def test_offset_mismatch_is_rejected(self) -> None:
        self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=4096,
            expected_md5="",
            verify=False,
            data=b"z" * 1024,
        )
        result = self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=9999,
            total_size=4096,
            expected_md5="",
            verify=False,
            data=b"z" * 1024,
        )
        expect(result.ok).to_equal(False)
        expect(result.error).to_equal(int(constants.UploadError.OFFSET_MISMATCH))

    def test_negative_offset_is_rejected(self) -> None:
        result = self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=-1,
            total_size=10,
            expected_md5="",
            verify=False,
            data=b"z",
        )
        expect(result.ok).to_equal(False)
        expect(result.error).to_equal(int(constants.UploadError.OFFSET_ERROR))

    def test_md5_mismatch_discards_the_file(self) -> None:
        result = self._upload(b"q" * 256, md5="0" * 32)
        expect(result.ok).to_equal(False)
        expect(result.md5_failed).to_equal(True)
        expect(pathlib.Path("/mnt/usb_share/model.ctb").exists()).to_equal(False)

    def test_md5_is_not_checked_when_verification_is_off(self) -> None:
        result = self._upload(b"q" * 256, md5="0" * 32, verify=False)
        expect(result.ok).to_equal(True)
        expect(result.completed).to_equal(True)

    def test_unsupported_extension_is_rejected(self) -> None:
        result = self._upload(b"data", filename="notes.txt")
        expect(result.ok).to_equal(False)
        expect(result.format_failed).to_equal(True)

    def test_filename_is_sanitized(self) -> None:
        result = self._upload(b"data" * 64, filename=".._.._etc_passwd.ctb")
        expect(result.ok).to_equal(True)
        expect(pathlib.Path("/mnt/usb_share/etc_passwd.ctb").exists()).to_equal(True)

    def test_restarting_at_offset_zero_resets_the_transfer(self) -> None:
        self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=4096,
            expected_md5="",
            verify=False,
            data=b"a" * 1024,
        )
        payload = b"b" * 2048
        result = self._upload(payload, chunk_size=2048, verify=True)
        expect(result.ok).to_equal(True)
        expect(pathlib.Path("/mnt/usb_share/model.ctb").read_bytes()).to_equal(payload)

    def test_terminate_without_transfer(self) -> None:
        ack = self.manager.terminate("nope")
        expect(ack).to_equal(int(constants.FileTransferAck.NOT_TRANSFER))

    def test_terminate_active_transfer(self) -> None:
        self.manager.handle_chunk(
            upload_uuid="abc",
            filename="model.ctb",
            offset=0,
            total_size=4096,
            expected_md5="",
            verify=False,
            data=b"a" * 1024,
        )
        ack = self.manager.terminate("abc")
        expect(ack).to_equal(int(constants.FileTransferAck.SUCCESS))
        expect(self.manager.is_transferring()).to_equal(False)
        expect(pathlib.Path("/mnt/usb_share/model.ctb").exists()).to_equal(False)
