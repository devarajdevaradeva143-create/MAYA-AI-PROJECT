"""WhatsApp hand-off: deep links, policy validation and PC page wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from custom.server import policy
from custom.server.errors import ApiError

from app.services import control_service
from app.services.control_service import ControlService
from app.ui.pages.pc_page import ACTION_IDS, PCPage


class RecordingControl:
    """Captures what the page asks the control service to do."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((action, dict(params)))
        return {"message": "ok"}


def test_uri_strips_symbols_and_encodes_text() -> None:
    uri = control_service.build_whatsapp_uri("+91 98765-43210", "Hi Maya & co?")

    assert uri.startswith("whatsapp://send?phone=919876543210&text=")
    assert "Hi%20Maya%20%26%20co%3F" in uri


def test_fallback_url_uses_wa_me() -> None:
    assert control_service.build_wa_me_url("919876543210", "hello") == (
        "https://wa.me/919876543210?text=hello"
    )


def test_short_number_rejected() -> None:
    with pytest.raises(RuntimeError):
        control_service.build_whatsapp_uri("123", "hi")


def test_handler_uses_protocol_when_registered(tmp_path: Path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(ControlService, "_require_windows", lambda self: None)
    monkeypatch.setattr(control_service, "_protocol_registered", lambda scheme: True)
    monkeypatch.setattr(control_service.os, "startfile", opened.append, raising=False)

    service = ControlService(audit_path=tmp_path / "audit.jsonl")
    result = service.execute(
        "whatsapp.message", {"number": "+91 98765 43210", "text": "Hello Maya"}
    )

    assert "WhatsApp opened" in result["message"]
    assert opened and opened[0].startswith("whatsapp://send?phone=919876543210")


def test_handler_falls_back_to_browser(tmp_path: Path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(ControlService, "_require_windows", lambda self: None)
    monkeypatch.setattr(control_service, "_protocol_registered", lambda scheme: False)
    monkeypatch.setattr(control_service.os, "startfile", opened.append, raising=False)

    service = ControlService(audit_path=tmp_path / "audit.jsonl")
    result = service.execute("whatsapp.message", {"number": "919876543210", "text": "Hi"})

    assert "wa.me" in result["message"]
    assert opened == ["https://wa.me/919876543210?text=Hi"]


def test_policy_asks_and_validates() -> None:
    assert policy.decision("whatsapp.message") == policy.ASK
    description = policy.validate(
        "whatsapp.message", {"number": "919876543210", "text": "hello"}, []
    )
    assert "WhatsApp" in description

    with pytest.raises(ApiError):
        policy.validate("whatsapp.message", {"number": "12", "text": "hello"}, [])
    with pytest.raises(ApiError):
        policy.validate("whatsapp.message", {"number": "919876543210", "text": "   "}, [])


def test_pc_page_lists_whatsapp(qtbot) -> None:
    page = PCPage(control=RecordingControl())
    qtbot.addWidget(page)

    assert page._action_combo.findText("WhatsApp message") >= 0
    assert ACTION_IDS["WhatsApp message"] == "whatsapp.message"


def test_confirm_path_maps_labels_to_action_ids(qtbot) -> None:
    control = RecordingControl()
    page = PCPage(control=control)
    qtbot.addWidget(page)

    page._show_confirm("Lock workstation", "risk")
    page._execute_after_confirm("Lock workstation")

    assert control.calls == [("system.lock", {})]


def test_whatsapp_confirm_passes_params(qtbot) -> None:
    control = RecordingControl()
    page = PCPage(control=control)
    qtbot.addWidget(page)

    params = {"number": "919876543210", "text": "Hello"}
    page._show_confirm("Send WhatsApp to 919876543210", "risk", params, "whatsapp.message")
    page._execute_after_confirm("Send WhatsApp to 919876543210")

    assert control.calls == [("whatsapp.message", params)]
