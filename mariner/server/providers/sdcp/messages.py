"""Builders for the SDCP JSON message envelopes.

Each topic uses a slightly different envelope shape; the spec is not uniform
about where ``Id`` appears or how deeply ``Data`` nests, so every shape gets
its own builder here rather than one generic one.
"""

import time
from typing import Any, Dict, List, Optional

from mariner.server.providers.sdcp import identity


def _timestamp() -> int:
    return int(time.time())


def topic(kind: str) -> str:
    return f"sdcp/{kind}/{identity.get_mainboard_id()}"


def discovery_response(
    *,
    name: str,
    machine_name: str,
    brand_name: str,
    mainboard_ip: str,
    firmware_version: str,
    protocol_version: str,
    internal_machine_name: str = "",
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "Name": name,
        "MachineName": machine_name,
        "BrandName": brand_name,
        "MainboardIP": mainboard_ip,
        "MainboardID": identity.get_mainboard_id(),
        "ProtocolVersion": protocol_version,
        "FirmwareVersion": firmware_version,
    }
    # Undocumented in the v3.0.0 spec, but ChituManager prefers it over
    # MachineName when matching a printer to its picture, and in the
    # discovery reply it concatenates BrandName in front of it. Setting it
    # to the bare model lets the brand stay populated without the brand
    # being doubled into the lookup key. Omitted entirely when unset.
    if internal_machine_name:
        data["InternalMachineName"] = internal_machine_name
    return {"Id": identity.get_brand_id(), "Data": data}


def response(
    cmd: int,
    data: Dict[str, Any],
    request_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "Id": identity.get_brand_id(),
        "Data": {
            "Cmd": int(cmd),
            "Data": data,
            "RequestID": request_id,
            "MainboardID": identity.get_mainboard_id(),
            "TimeStamp": _timestamp(),
        },
        "Topic": topic("response"),
    }


def status(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Status": payload,
        "MainboardID": identity.get_mainboard_id(),
        "TimeStamp": _timestamp(),
        "Topic": topic("status"),
    }


def attributes(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Attributes": payload,
        "MainboardID": identity.get_mainboard_id(),
        "TimeStamp": _timestamp(),
        "Topic": topic("attributes"),
    }


def error(error_code: int) -> Dict[str, Any]:
    return {
        "Id": identity.get_brand_id(),
        "Data": {
            "Data": {"ErrorCode": error_code},
            "MainboardID": identity.get_mainboard_id(),
            "TimeStamp": _timestamp(),
        },
        "Topic": topic("error"),
    }


def notice(message: Any, notice_type: int) -> Dict[str, Any]:
    return {
        "Id": identity.get_brand_id(),
        "Data": {
            "Data": {"Message": message, "Type": notice_type},
            "MainboardID": identity.get_mainboard_id(),
            "TimeStamp": _timestamp(),
        },
        "Topic": topic("notice"),
    }


def upload_success() -> Dict[str, Any]:
    from mariner.server.providers.sdcp.constants import UPLOAD_SUCCESS_CODE

    return {
        "code": UPLOAD_SUCCESS_CODE,
        "messages": None,
        "data": {},
        "success": True,
    }


def upload_failure(error_code: int, reason: Optional[str] = None) -> Dict[str, Any]:
    from mariner.server.providers.sdcp.constants import UPLOAD_FAILURE_CODE

    messages: List[Dict[str, Any]] = [
        {"field": "common_field", "message": int(error_code)}
    ]
    if reason:
        messages.append({"field": "filename", "message": reason})
    return {
        "code": UPLOAD_FAILURE_CODE,
        "messages": messages,
        "data": None,
        "success": False,
    }
