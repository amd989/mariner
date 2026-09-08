"""Chunked file upload handling for the SDCP HTTP server.

SDCP clients send a file as a sequence of ~1MB multipart POSTs that all share
a ``Uuid`` and carry an ``Offset``. Chunks are appended to a scratch file next
to the destination so the final move is an atomic same-filesystem rename.
"""

import hashlib
import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

from mariner import config
from mariner.file_formats.utils import get_file_extension, get_supported_extensions
from mariner.server.providers.filenames import safe_filename
from mariner.server.providers.sdcp import constants

logger: logging.Logger = logging.getLogger(__name__)

SCRATCH_DIRNAME: str = ".sdcp_uploads"


@dataclass
class ChunkResult:
    ok: bool
    error: Optional[int] = None
    completed: bool = False
    filename: str = ""
    md5_failed: bool = False
    format_failed: bool = False


@dataclass
class _Session:
    filename: str
    total_size: int
    expected_md5: str
    verify: bool
    scratch_path: Path
    handle: BinaryIO
    offset: int = 0
    # hashlib's hash objects have no public type to name here.
    hasher: Any = field(default_factory=hashlib.md5)

    def close(self) -> None:
        try:
            self.handle.close()
        except OSError:
            pass


class UploadManager:
    """Assembles chunked uploads into files in Mariner's files directory."""

    _lock: threading.Lock

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, _Session] = {}

    def is_transferring(self) -> bool:
        with self._lock:
            return bool(self._sessions)

    def _scratch_dir(self) -> Path:
        # Kept inside the files directory so finalize() is a rename rather
        # than a cross-filesystem copy of a potentially huge file.
        path = config.get_files_directory() / SCRATCH_DIRNAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    def handle_chunk(
        self,
        *,
        upload_uuid: str,
        filename: str,
        offset: int,
        total_size: int,
        expected_md5: str,
        verify: bool,
        data: bytes,
    ) -> ChunkResult:
        if offset < 0 or total_size < 0:
            return ChunkResult(ok=False, error=constants.UploadError.OFFSET_ERROR)

        safe_name = safe_filename(filename)
        if safe_name is None:
            logger.warning("SDCP: refusing unsafe upload filename %r", filename)
            return ChunkResult(
                ok=False,
                error=constants.UploadError.UNKNOWN,
                format_failed=True,
            )

        if get_file_extension(safe_name) not in get_supported_extensions():
            return ChunkResult(
                ok=False,
                error=constants.UploadError.UNKNOWN,
                format_failed=True,
            )

        with self._lock:
            session = self._sessions.get(upload_uuid)

            # Offset 0 always (re)starts a transfer, so a client retrying from
            # the beginning discards whatever was buffered before.
            if session is None or offset == 0:
                if session is not None:
                    self._discard(upload_uuid, session)
                try:
                    scratch = self._scratch_dir() / f"{upload_uuid}.part"
                    handle = open(scratch, "wb")
                except OSError as exc:
                    logger.warning("SDCP: cannot open scratch file: %s", exc)
                    return ChunkResult(
                        ok=False, error=constants.UploadError.FILE_OPEN_FAILED
                    )
                session = _Session(
                    filename=safe_name,
                    total_size=total_size,
                    expected_md5=(expected_md5 or "").lower(),
                    verify=verify,
                    scratch_path=scratch,
                    handle=handle,
                )
                self._sessions[upload_uuid] = session
                logger.info(
                    "SDCP: upload starting: %s uuid=%s total_size=%d "
                    "check=%s declared_md5=%s",
                    safe_name,
                    upload_uuid,
                    total_size,
                    verify,
                    expected_md5 or "<none>",
                )

            if offset != session.offset:
                return ChunkResult(
                    ok=False, error=constants.UploadError.OFFSET_MISMATCH
                )

            # Clients may pad the final packet. TotalSize is authoritative, so
            # anything past it is dropped: writing it produces a file longer
            # than the original, which breaks formats that store a checksum in
            # their trailing bytes (encrypted CTB seeks back from the end).
            if session.total_size:
                remaining = session.total_size - session.offset
                if remaining <= 0:
                    data = b""
                elif len(data) > remaining:
                    data = data[:remaining]

            try:
                session.handle.write(data)
            except OSError as exc:
                logger.warning("SDCP: write failed: %s", exc)
                self._discard(upload_uuid, session)
                return ChunkResult(
                    ok=False, error=constants.UploadError.FILE_OPEN_FAILED
                )

            session.hasher.update(data)
            session.offset += len(data)

            if session.total_size and session.offset >= session.total_size:
                return self._finalize(upload_uuid, session)

        return ChunkResult(ok=True)

    def _finalize(self, upload_uuid: str, session: _Session) -> ChunkResult:
        session.close()
        self._sessions.pop(upload_uuid, None)

        computed = session.hasher.hexdigest()
        logger.info(
            "SDCP: upload finished: %s bytes=%d declared_total=%d check=%s "
            "declared_md5=%s computed_md5=%s",
            session.filename,
            session.offset,
            session.total_size,
            session.verify,
            session.expected_md5 or "<none>",
            computed,
        )

        if session.verify and session.expected_md5:
            if computed != session.expected_md5:
                logger.warning(
                    "SDCP: MD5 mismatch for %s (expected %s, got %s)",
                    session.filename,
                    session.expected_md5,
                    computed,
                )
                self._unlink(session.scratch_path)
                return ChunkResult(
                    ok=False,
                    error=constants.UploadError.UNKNOWN,
                    md5_failed=True,
                    filename=session.filename,
                )

        files_dir = config.get_files_directory().resolve()
        destination = (files_dir / session.filename).resolve()
        try:
            destination.relative_to(files_dir)
        except ValueError:
            self._unlink(session.scratch_path)
            return ChunkResult(
                ok=False,
                error=constants.UploadError.UNKNOWN,
                format_failed=True,
            )

        try:
            os.replace(session.scratch_path, destination)
        except OSError as exc:
            logger.warning("SDCP: could not move upload into place: %s", exc)
            self._unlink(session.scratch_path)
            return ChunkResult(ok=False, error=constants.UploadError.FILE_OPEN_FAILED)

        self._sync()
        self._cleanup_scratch_dir()
        logger.info("SDCP: received %s (%d bytes)", session.filename, session.offset)
        return ChunkResult(ok=True, completed=True, filename=session.filename)

    def terminate(self, upload_uuid: str, filename: str = "") -> int:
        """Handle Cmd 255, returning the matching ack code."""
        with self._lock:
            session = self._sessions.get(upload_uuid)
            if session is None:
                return int(constants.FileTransferAck.NOT_TRANSFER)
            self._discard(upload_uuid, session)
        self._cleanup_scratch_dir()
        return int(constants.FileTransferAck.SUCCESS)

    def _discard(self, upload_uuid: str, session: _Session) -> None:
        session.close()
        self._sessions.pop(upload_uuid, None)
        self._unlink(session.scratch_path)

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def _cleanup_scratch_dir(self) -> None:
        if self._sessions:
            return
        path = config.get_files_directory() / SCRATCH_DIRNAME
        try:
            shutil.rmtree(path)
        except OSError:
            pass

    @staticmethod
    def _sync() -> None:
        # The printer reads the same files over USB mass storage, so flush
        # before telling the client the transfer succeeded.
        sync = getattr(os, "sync", None)
        if sync is not None:
            try:
                sync()
            except OSError:
                pass
