"""Constants and enums from the SDCP v3.0.0 specification.

Reference: SDCP (Smart Device Control Protocol) V3.0.0,
Shenzhen CBD Technology Co., Ltd.
"""

from enum import IntEnum

PROTOCOL_VERSION = "V3.0.0"

DISCOVERY_MAGIC = b"M99999"
DEFAULT_DISCOVERY_PORT = 3000
DEFAULT_SERVER_PORT = 3030

WEBSOCKET_PATH = "/websocket"
UPLOAD_PATH = "/uploadFile/upload"
# Not in the spec: the protocol only says Thumbnail carries an address, so we
# serve the rendered previews ourselves alongside the rest of the service.
THUMBNAIL_PATH = "/thumbnail"

# Storage prefixes used by the protocol for file paths.
LOCAL_PREFIX = "/local/"
USB_PREFIX = "/usb/"


class Cmd(IntEnum):
    """Request command codes."""

    REFRESH_STATUS = 0
    REFRESH_ATTRIBUTES = 1
    START_PRINT = 128
    PAUSE_PRINT = 129
    STOP_PRINT = 130
    CONTINUE_PRINT = 131
    STOP_FEEDING = 132
    SKIP_PREHEATING = 133
    CHANGE_NAME = 192
    TERMINATE_TRANSFER = 255
    LIST_FILES = 258
    DELETE_FILES = 259
    HISTORY_TASKS = 320
    TASK_DETAILS = 321
    VIDEO_STREAM = 386
    TIMELAPSE = 387


class MachineStatus(IntEnum):
    """Top-level machine status (``CurrentStatus`` / ``PreviousStatus``)."""

    IDLE = 0
    PRINTING = 1
    FILE_TRANSFERRING = 2
    EXPOSURE_TESTING = 3
    DEVICES_TESTING = 4


class PrintStatus(IntEnum):
    """Printing sub-status (``PrintInfo.Status``)."""

    IDLE = 0
    HOMING = 1
    DROPPING = 2
    EXPOSURING = 3
    LIFTING = 4
    PAUSING = 5
    PAUSED = 6
    STOPPING = 7
    STOPPED = 8
    COMPLETE = 9
    FILE_CHECKING = 10


class PrintError(IntEnum):
    """``PrintInfo.ErrorNumber`` values."""

    NONE = 0
    CHECK = 1
    FILEIO = 2
    INVALID_RESOLUTION = 3
    UNKNOWN_FORMAT = 4
    UNKNOWN_MODEL = 5


class PrintCtrlAck(IntEnum):
    """Ack codes for print control commands (128-131)."""

    OK = 0
    BUSY = 1
    NOT_FOUND = 2
    MD5_FAILED = 3
    FILEIO_FAILED = 4
    INVALID_RESOLUTION = 5
    UNKNOWN_FORMAT = 6
    UNKNOWN_MODEL = 7


class FileTransferAck(IntEnum):
    """Ack codes for terminate-file-transfer (255)."""

    SUCCESS = 0
    NOT_TRANSFER = 1
    CHECKING = 2
    NOT_FOUND = 3


class VideoStreamAck(IntEnum):
    """Ack codes for enable/disable video stream (386)."""

    SUCCESS = 0
    EXCEEDED_LIMIT = 1
    CAMERA_MISSING = 2
    UNKNOWN = 3


class ErrorCode(IntEnum):
    """Codes reported on the ``sdcp/error`` topic."""

    MD5_FAILED = 1
    FORMAT_FAILED = 2


# HTTP upload endpoint result codes.
UPLOAD_SUCCESS_CODE = "000000"
UPLOAD_FAILURE_CODE = "111111"


class UploadError(IntEnum):
    """Failure reasons returned by the file upload endpoint."""

    OFFSET_ERROR = -1
    OFFSET_MISMATCH = -2
    FILE_OPEN_FAILED = -3
    UNKNOWN = -4
