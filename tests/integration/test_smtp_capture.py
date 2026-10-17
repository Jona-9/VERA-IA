"""Pruebas de captura física en el socket SMTP local (T013, RF-15, Principio XII)."""

import socket
from datetime import date

import pytest

from src.domain.entities import ContactNotice, Tone
from src.mail.client import MailSettings, SMTPMailClient, UnsafeSMTPTargetError
from src.mail.server import (
    LocalSMTPServer,
    SQLiteCaptureStore,
    UnsafeSMTPBindError,
    start_embedded_server,
    stop_embedded_server,
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server():
    with LocalSMTPServer(port=free_port()) as srv:
        yield srv


def make_client(port: int) -> SMTPMailClient:
    return SMTPMailClient(MailSettings(port=port))


def test_email_is_captured_over_real_socket(server):
    message_id = make_client(server.port).send(
        "cliente001@demo.veraia.local", "Recordatorio de pago", "Estimado(a) Ana:\n\nSu cuota vence hoy."
    )
    captured = server.captured()
    assert len(captured) == 1
    email = captured[0]
    assert email.recipient == "cliente001@demo.veraia.local"
    assert email.sender == "noreply@demo.veraia.local"
    assert email.subject == "Recordatorio de pago"
    assert message_id in email.raw_content
    assert "Su cuota vence hoy" in email.raw_content


def test_send_notice_preserves_utf8_subject_and_notice_header(server):
    notice = ContactNotice(
        notice_id="N-001", account_id="ACC-001", evaluation_id="E-001",
        scheduled_date=date(2026, 10, 17), tone=Tone.PREVENTIVE,
        subject="Su próxima cuota", body_text="Atención: pago próximo.",
    )
    make_client(server.port).send_notice(notice, "cliente002@demo.veraia.local")
    email = server.captured()[0]
    assert email.subject == "Su próxima cuota"
    assert "X-VERAIA-Notice-Id: N-001" in email.raw_content


def test_sqlite_store_persists_captures(tmp_path):
    store = SQLiteCaptureStore(tmp_path / "capture.db")
    with LocalSMTPServer(port=free_port(), store=store) as srv:
        make_client(srv.port).send("a@demo.veraia.local", "Uno", "cuerpo")
        make_client(srv.port).send("b@demo.veraia.local", "Dos", "cuerpo")
    reopened = SQLiteCaptureStore(tmp_path / "capture.db")
    assert [e.subject for e in reopened.list()] == ["Uno", "Dos"]
    reopened.clear()
    assert reopened.list() == []


def test_server_refuses_non_loopback_bind():
    with pytest.raises(UnsafeSMTPBindError):
        LocalSMTPServer(host="0.0.0.0")


def test_client_refuses_remote_host_in_local_environment():
    with pytest.raises(UnsafeSMTPTargetError):
        SMTPMailClient(MailSettings(host="smtp.gmail.com", port=587))


def test_settings_load_from_project_config():
    settings = MailSettings.from_config()
    assert settings.host == "127.0.0.1"
    assert settings.port == 1025
    assert settings.environment == "local"


def test_embedded_server_is_idempotent():
    port = free_port()
    try:
        first = start_embedded_server(port=port)
        assert start_embedded_server(port=port) is first
    finally:
        stop_embedded_server(port=port)
    assert not first.is_running
