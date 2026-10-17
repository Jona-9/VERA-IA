"""
Cliente de despacho SMTP configurable por entorno (RF-15, Principio XII).

En entorno `local` (demo) solo se permite enviar a un servidor loopback; cualquier otro host
lanza `UnsafeSMTPTargetError` antes de abrir el socket.
"""

import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Dict, Optional, Union

import yaml
from pydantic import BaseModel

from src.domain.entities import ContactNotice
from src.mail.server import LOOPBACK_HOSTS

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


class UnsafeSMTPTargetError(RuntimeError):
    """Intento de despachar correo a un servidor no local durante la demo."""


class MailSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1025
    sender_email: str = "noreply@demo.veraia.local"
    sender_name: str = "VERAIA Cobranza Preventiva"
    environment: str = "local"

    @classmethod
    def from_config(cls, path: Union[str, Path] = DEFAULT_CONFIG_PATH) -> "MailSettings":
        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        return cls(environment=config.get("environment", "local"), **config.get("smtp", {}))


class SMTPMailClient:
    """Envía avisos vía smtplib al servidor configurado (captura local en la demo)."""

    def __init__(self, settings: Optional[MailSettings] = None, timeout_seconds: float = 5.0):
        self.settings = settings or MailSettings()
        self.timeout_seconds = timeout_seconds
        if self.settings.environment == "local" and self.settings.host not in LOOPBACK_HOSTS:
            raise UnsafeSMTPTargetError(
                f"Entorno 'local': el despacho solo puede dirigirse a loopback, no a "
                f"'{self.settings.host}'"
            )

    def send(self, recipient: str, subject: str, body_text: str,
             extra_headers: Optional[Dict[str, str]] = None) -> str:
        """Envía un correo de texto plano y retorna su Message-ID."""
        message = EmailMessage()
        message["From"] = formataddr((self.settings.sender_name, self.settings.sender_email))
        message["To"] = recipient
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=self.settings.sender_email.split("@")[-1])
        for name, value in (extra_headers or {}).items():
            message[name] = value
        message.set_content(body_text)

        with smtplib.SMTP(self.settings.host, self.settings.port,
                          timeout=self.timeout_seconds) as smtp:
            smtp.send_message(message)
        return message["Message-ID"]

    def send_notice(self, notice: ContactNotice, recipient: str) -> str:
        """Despacha un ContactNotice ya aprobado por ScheduleNoticeTool."""
        return self.send(
            recipient=recipient,
            subject=notice.subject,
            body_text=notice.body_text,
            extra_headers={"X-VERAIA-Notice-Id": notice.notice_id},
        )
