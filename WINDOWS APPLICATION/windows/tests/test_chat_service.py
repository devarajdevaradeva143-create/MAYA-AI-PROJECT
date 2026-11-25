"""ChatService tests: history, personas, streaming, cancel, context window."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.chat_service import MAX_INPUT_CHARS, ChatService
from tests.fakes import FakeEngine


class RecordingEngine(FakeEngine):
    """FakeEngine that keeps every message list it was given."""

    def __init__(self, reply: str = "ok", chunks: list[str] | None = None) -> None:
        super().__init__(reply=reply, chunks=chunks)
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages):
        self.calls.append([dict(item) for item in messages])
        return super().chat(messages)

    def chat_stream(self, messages):
        self.calls.append([dict(item) for item in messages])
        yield from super().chat_stream(messages)


class HookEngine:
    """Yields chunks and runs a hook after each one (cancel tests)."""

    def __init__(self, chunks: list[str], on_chunk=None) -> None:
        self.chunks = chunks
        self.on_chunk = on_chunk

    def chat(self, messages):
        del messages
        return "".join(self.chunks)

    def chat_stream(self, messages):
        del messages
        for chunk in self.chunks:
            yield chunk
            if self.on_chunk is not None:
                self.on_chunk()


def _service(tmp_path: Path, engine=None) -> ChatService:
    return ChatService(
        engine or RecordingEngine(),
        tmp_path / "chat_history.json",
        persona_loader=lambda name: f"PROMPT:{name}",
    )


def test_send_records_history_with_system_prompt(tmp_path) -> None:
    engine = RecordingEngine(reply="Vanakkam da!")
    service = _service(tmp_path, engine)

    reply = service.send("hi")

    assert reply == "Vanakkam da!"
    assert engine.calls[0][0] == {"role": "system", "content": "PROMPT:girlfriend"}
    assert engine.calls[0][-1] == {"role": "user", "content": "hi"}
    assert [item["role"] for item in service.messages()] == ["user", "assistant"]
    assert service.messages()[1]["content"] == "Vanakkam da!"


def test_history_survives_restart(tmp_path) -> None:
    first = _service(tmp_path)
    first.send("hello")

    second = _service(tmp_path)

    assert second.persona == "maya"
    assert second.messages()[0] == {"role": "user", "content": "hello"}


def test_persona_switch_clears_history_and_persists(tmp_path) -> None:
    service = _service(tmp_path)
    service.send("hi")

    service.set_persona("teacher")

    assert service.persona == "teacher"
    assert service.messages() == []

    restarted = _service(tmp_path)
    assert restarted.persona == "teacher"


def test_unknown_persona_is_rejected(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError):
        service.set_persona("robot")


def test_new_chat_keeps_persona_but_clears_messages(tmp_path) -> None:
    service = _service(tmp_path)
    service.set_persona("teacher")
    service.send("hi")

    service.new_chat()

    assert service.persona == "teacher"
    assert service.messages() == []


def test_stream_yields_chunks_and_saves_reply(tmp_path) -> None:
    service = _service(tmp_path, RecordingEngine(chunks=["Van", "akkam"]))

    chunks = list(service.stream("hi"))

    assert chunks == ["Van", "akkam"]
    stored = service.messages()
    assert stored[-1] == {"role": "assistant", "content": "Vanakkam"}


def test_cancel_mid_stream_does_not_save(tmp_path) -> None:
    service = _service(tmp_path)
    service._engine = HookEngine(["first", "second"], on_chunk=service.cancel)

    chunks = list(service.stream("hi"))

    assert chunks == ["first"]
    assert service.was_cancelled is True
    assert service.messages() == []


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_is_rejected(tmp_path, text: str) -> None:
    service = _service(tmp_path)

    with pytest.raises(Exception, match="empty"):
        service.send(text)


def test_long_input_is_rejected(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(Exception, match="longer than"):
        service.send("x" * (MAX_INPUT_CHARS + 1))


def test_context_keeps_system_and_last_19(tmp_path) -> None:
    engine = RecordingEngine(reply="r")
    service = _service(tmp_path, engine)

    for index in range(15):
        service.send(f"message {index}")

    engine.calls.clear()
    service.send("latest")

    sent = engine.calls[0]
    assert sent[0]["role"] == "system"
    assert len([item for item in sent if item["role"] != "system"]) == 20  # 19 + new user
    assert sent[-1] == {"role": "user", "content": "latest"}
