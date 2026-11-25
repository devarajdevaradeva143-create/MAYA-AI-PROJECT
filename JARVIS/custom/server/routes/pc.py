"""Laptop control endpoints: status, command, confirm, cancel.
Device status endpoint for phone -> laptop stats reporting.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from custom.server import policy
from custom.server.auth import DeviceDep
from custom.server.errors import ApiError
from custom.server.models import (
    PcCancelRequest,
    PcCommandRequest,
    PcCommandResponse,
    PcConfirmRequest,
    DeviceStatusRequest,
)

router = APIRouter(prefix="/pc", tags=["pc"])

PC_RATE_LIMIT = 30


@router.get("/status")
def pc_status(
    request: Request,
    device: DeviceDep,
) -> dict:
    del device
    try:
        return request.app.state.services.monitor.snapshot()
    except Exception as exc:  # noqa: BLE001 - mapped to contract error
        raise ApiError(5000, "Status unavailable") from exc


def _execute(request: Request, action: str, params: dict) -> dict:
    try:
        result = request.app.state.services.pc.execute(action, params)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - never leak internals
        raise ApiError(5000, "Action failed") from exc
    return result if isinstance(result, dict) else {"message": str(result)}


def _validate(request: Request, action: str, params: dict) -> str:
    return policy.validate(action, params, request.app.state.services.settings.allowed_roots)


@router.post("/command", response_model=PcCommandResponse, response_model_exclude_none=True)
def pc_command(
    body: PcCommandRequest,
    request: Request,
    device: DeviceDep,
) -> PcCommandResponse:
    state = request.app.state
    state.limiter.hit(f"pc:{device.device_id}", PC_RATE_LIMIT, 60)

    description = _validate(request, body.action, body.params)

    if body.confirm_token:
        pending = state.confirm.pop(body.confirm_token, device.device_id)
        if pending.action != body.action or pending.params != body.params:
            raise ApiError(4002, "Confirmation does not match this action")
        _validate(request, pending.action, pending.params)
        return PcCommandResponse(
            status="done",
            result=_execute(request, pending.action, pending.params),
        )

    if policy.decision(body.action) == policy.ASK:
        token, expires_in = state.confirm.create(
            device_id=device.device_id,
            action=body.action,
            params=body.params,
            description=description,
        )
        return PcCommandResponse(
            status="needs_confirmation",
            confirm_token=token,
            description=description,
            expires_in=expires_in,
        )

    return PcCommandResponse(
        status="done",
        result=_execute(request, body.action, body.params),
    )


@router.post("/confirm", response_model=PcCommandResponse, response_model_exclude_none=True)
def pc_confirm(
    body: PcConfirmRequest,
    request: Request,
    device: DeviceDep,
) -> PcCommandResponse:
    state = request.app.state
    state.limiter.hit(f"pc:{device.device_id}", PC_RATE_LIMIT, 60)
    pending = state.confirm.pop(body.confirm_token, device.device_id)
    _validate(request, pending.action, pending.params)
    return PcCommandResponse(
        status="done",
        result=_execute(request, pending.action, pending.params),
    )


@router.post("/cancel", response_model=PcCommandResponse, response_model_exclude_none=True)
def pc_cancel(
    body: PcCancelRequest,
    request: Request,
    device: DeviceDep,
) -> PcCommandResponse:
    request.app.state.confirm.cancel(body.confirm_token, device.device_id)
    return PcCommandResponse(status="cancelled")


# --- Device status (phone reports its own stats) --------------------------

@router.post("/device/status")
def device_status(
    body: DeviceStatusRequest,
    request: Request,
    device: DeviceDep,
) -> dict:
    """Phone POSTs its local stats (battery, storage, RAM, uptime).
    Stored per device_id and broadcast via events WebSocket.
    """
    # Verify the device_id matches the authenticated device
    if body.device_id != device.device_id:
        raise ApiError(4002, "Device ID mismatch")

    # Store in device record (extend TokenStore to persist phone stats)
    state = request.app.state
    state.tokens.update_phone_stats(device.device_id, body.stats.model_dump())

    return {"status": "ok"}
