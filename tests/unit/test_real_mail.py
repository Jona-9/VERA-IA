"""Envío real por SMTP: configuración por entorno, modo prueba y avisos de seguridad."""

import pytest

from src.mail import client as mail_client
from src.mail.client import MailConfigError, MailSettings, SMTPMailClient, build_mail_client

BASE_ENV = {
    "VERAIA_SMTP_HOST": "smtp.proveedor.test",
    "VERAIA_SMTP_USER": "cuenta@proveedor.test",
    "VERAIA_SMTP_PASSWORD": "secreto",
    "VERAIA_MAIL_REDIRECT_TO": "prueba@ejemplo.test",
}


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context = host, port, context
        self.calls, self.sent = [], []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(mail_client.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mail_client.smtplib, "SMTP_SSL", FakeSMTP)


def test_real_send_uses_starttls_login_and_redirects_to_test_address():
    settings = MailSettings.from_env(BASE_ENV)
    SMTPMailClient(settings).send("ana@cliente.test", "Su próxima cuota", "Hola")
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.proveedor.test", 587)
    assert smtp.calls == ["starttls", ("login", "cuenta@proveedor.test", "secreto")]
    message = smtp.sent[0]
    assert message["To"] == "prueba@ejemplo.test"
    assert message["X-VERAIA-Original-Recipient"] == "ana@cliente.test"
    assert message["Subject"].startswith("[PRUEBA para ana@cliente.test]")


def test_ssl_security_defaults_to_port_465():
    settings = MailSettings.from_env({**BASE_ENV, "VERAIA_SMTP_SECURITY": "ssl"})
    assert settings.port == 465
    SMTPMailClient(settings).send("ana@cliente.test", "Asunto", "Hola")
    assert FakeSMTP.instances[0].calls == [("login", "cuenta@proveedor.test", "secreto")]


def test_real_recipients_only_with_explicit_opt_in():
    env = {k: v for k, v in BASE_ENV.items() if k != "VERAIA_MAIL_REDIRECT_TO"}
    with pytest.raises(MailConfigError, match="destinatario de prueba"):
        MailSettings.from_env(env)
    settings = MailSettings.from_env({**env, "VERAIA_MAIL_ALLOW_REAL_RECIPIENTS": "1"})
    SMTPMailClient(settings).send("ana@cliente.test", "Asunto", "Hola")
    message = FakeSMTP.instances[0].sent[0]
    assert message["To"] == "ana@cliente.test"
    assert message["Subject"] == "Asunto"


def test_missing_host_and_bad_security_are_rejected():
    with pytest.raises(MailConfigError, match="VERAIA_SMTP_HOST"):
        MailSettings.from_env({})
    with pytest.raises(MailConfigError, match="VERAIA_SMTP_SECURITY"):
        MailSettings.from_env({**BASE_ENV, "VERAIA_SMTP_SECURITY": "tls13"})


def test_build_mail_client_defaults_to_local_capture(monkeypatch):
    monkeypatch.delenv("VERAIA_MAIL_MODE", raising=False)
    assert build_mail_client().settings.is_local


def test_build_mail_client_real_mode_reads_environment(monkeypatch):
    monkeypatch.setenv("VERAIA_MAIL_MODE", "real")
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    client = build_mail_client()
    assert not client.settings.is_local and client.settings.redirect_to == "prueba@ejemplo.test"
