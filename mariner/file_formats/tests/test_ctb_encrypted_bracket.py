import pathlib
from unittest import TestCase

import png
from pyexpect import expect

from mariner.file_formats.ctb_encrypted import (
    HASH_LENGTH,
    CTBEncryptedFile,
    CTBEncryptedHeader,
    check_encrypted,
)
from mariner.file_formats.utils import get_file_format


class BracketEncryptedCTBTest(TestCase):
    """An encrypted CTB that carries bytes after its signature.

    Written by a current ChiTuBox, this file places 4 bytes after the
    signature block. Parsing it by seeking back HASH_LENGTH from the end of
    the file reads 4 bytes of that trailer plus only part of the signature,
    and the checksum comparison then fails with "malformed file". The header
    declares where the signature actually lives, so that is what must be
    used. bolts.ctb, whose signature ends exactly at EOF, covers the case
    where both approaches agree.
    """

    def _path(self) -> pathlib.Path:
        return pathlib.Path(__file__).parent.absolute() / "bracket.ctb"

    def test_bracket_ctb_is_detected_as_encrypted(self) -> None:
        path = self._path()
        expect(check_encrypted(str(path))).to_equal(CTBEncryptedFile)
        expect(get_file_format(str(path))).to_equal(CTBEncryptedFile)

    def test_signature_is_not_at_the_end_of_the_file(self) -> None:
        # The premise of this fixture. If a future ChiTuBox stops writing the
        # trailer, this file stops covering the regression and should be
        # replaced rather than the assertion relaxed.
        raw = self._path().read_bytes()
        header = CTBEncryptedHeader.unpack(raw[: CTBEncryptedHeader.get_size()])
        expect(header.signature_size).to_equal(HASH_LENGTH)
        start = header.signature_offset
        end = start + header.signature_size
        expect(len(raw) - end).to_equal(4)
        # Seeking from the end would therefore read the wrong bytes.
        expect(raw[start:end]).not_to_equal(raw[-HASH_LENGTH:])

    def test_bracket_ctb_metadata_and_layer_end_offsets(self) -> None:
        ctb = CTBEncryptedFile.read(self._path())
        expect(ctb.filename).to_equal("bracket.ctb")
        expect(ctb.layer_count).to_equal(220)
        expect(len(ctb.end_byte_offset_by_layer)).to_equal(220)
        expect(ctb.resolution).to_equal((4098, 2560))
        expect(ctb.print_time_secs).to_equal(2011)
        expect(ctb.bed_size_mm[0]).close_to(143.43, max_delta=1e-2)
        expect(ctb.bed_size_mm[1]).close_to(89.6, max_delta=1e-2)
        expect(ctb.bed_size_mm[2]).close_to(175.0, max_delta=1e-2)
        # Note: unlike bolts.ctb these offsets are NOT monotonic. Five layers
        # in this file have no encrypted payload, so read() falls back to
        # layer_def_offset + data_length, which is on a different scale to
        # the encrypted_data_offset used for the rest. Ordering is therefore
        # not an invariant of this format and is deliberately not asserted.
        offsets = ctb.end_byte_offset_by_layer
        expect(len(offsets)).to_equal(220)
        expect(max(offsets)).to_equal(1678193)

    def test_bracket_ctb_preview_renders(self) -> None:
        preview: png.Image = CTBEncryptedFile.read_preview(self._path())
        expect(preview.info["alpha"]).is_false()
