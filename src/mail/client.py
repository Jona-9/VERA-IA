"""
Cliente de despacho SMTP configurable por entorno (RF-15, Principio XII).

En entorno `local` (demo) solo se permite enviar a un servidor loopback; cualquier otro host
lanza `UnsafeSMTPTargetError` antes de abrir el socket.

Envío real: con `VERAIA_MAIL_MODE=real` el cliente sale por el SMTP del proveedor configurado en
variables de entorno (ver `.env.example`). Por seguridad exige `VERAIA_MAIL_REDIRECT_TO` (modo prueba:
todo aviso va a esa dirección) o, de forma explícita, `VERAIA_MAIL_ALLOW_REAL_RECIPIENTS=1`.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

import yaml
from pydantic import BaseModel

from src.domain.entities import ContactNotice
from src.mail.server import LOOPBACK_HOSTS

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


class UnsafeSMTPTargetError(RuntimeError):
    """Intento de despachar correo a un servidor no local durante la demo."""


class MailConfigError(RuntimeError):
    """Configuración de envío real incompleta o insegura."""


class MailSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1025
    sender_email: str = "noreply@demo.veraia.local"
    sender_name: str = "VERAIA Cobranza Preventiva"
    environment: str = "local"
    username: Optional[str] = None
    password: Optional[str] = None
    security: str = "none"  # 'none' | 'starttls' | 'ssl'
    redirect_to: Optional[str] = None
    allow_real_recipients: bool = False

    @property
    def is_local(self) -> bool:
        return self.host in LOOPBACK_HOSTS

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "MailSettings":
        """Ajustes de envío real desde variables de entorno (`VERAIA_MAIL_MODE=real`)."""
        env = os.environ if env is None else env
        host = env.get("VERAIA_SMTP_HOST", "").strip()
        if not host:
            raise MailConfigError("Falta VERAIA_SMTP_HOST para el envío real.")
        security = env.get("VERAIA_SMTP_SECURITY", "starttls").strip().lower()
        if security not in ("none", "starttls", "ssl"):
            raise MailConfigError("VERAIA_SMTP_SECURITY debe ser none, starttls o ssl.")
        sender = env.get("VERAIA_MAIL_FROM", "").strip() or env.get("VERAIA_SMTP_USER", "").strip()
        if not sender:
            raise MailConfigError("Falta VERAIA_MAIL_FROM (o VERAIA_SMTP_USER) como remitente.")
        settings = cls(
            host=host,
            port=int(env.get("VERAIA_SMTP_PORT", "465" if security == "ssl" else "587")),
            sender_email=sender,
            sender_name=env.get("VERAIA_MAIL_FROM_NAME", cls.model_fields["sender_name"].default),
            environment="production",
            username=env.get("VERAIA_SMTP_USER") or None,
            password=env.get("VERAIA_SMTP_PASSWORD") or None,
            security=security,
            redirect_to=env.get("VERAIA_MAIL_REDIRECT_TO", "").strip() or None,
            allow_real_recipients=env.get("VERAIA_MAIL_ALLOW_REAL_RECIPIENTS", "") == "1",
        )
        if not settings.redirect_to and not settings.allow_real_recipients:
            raise MailConfigError(
                "Envío real sin destinatario de prueba: define VERAIA_MAIL_REDIRECT_TO o, si los "
                "correos de la cartera son reales, VERAIA_MAIL_ALLOW_REAL_RECIPIENTS=1."
            )
        return settings

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
        if self.settings.redirect_to:
            # Modo prueba: el aviso llega a la dirección de prueba, con el destinatario original a la vista.
            message["X-VERAIA-Original-Recipient"] = recipient
            subject = f"[PRUEBA para {recipient}] {subject}"
            recipient = self.settings.redirect_to
        message["To"] = recipient
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=self.settings.sender_email.split("@")[-1])
        for name, value in (extra_headers or {}).items():
            message[name] = value
        message.set_content(body_text)

        with self._connect() as smtp:
            smtp.send_message(message)
        return message["Message-ID"]

    def _connect(self) -> smtplib.SMTP:
        cfg = self.settings
        if cfg.security == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=self.timeout_seconds,
                                                  context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(cfg.host, cfg.port, timeout=self.timeout_seconds)
            if cfg.security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
        if cfg.username and cfg.password:
            smtp.login(cfg.username, cfg.password)
        return smtp

    def send_notice(self, notice: ContactNotice, recipient: str) -> str:
        """Despacha un ContactNotice ya aprobado por ScheduleNoticeTool."""
        return self.send(
            recipient=recipient,
            subject=notice.subject,
            body_text=notice.body_text,
            extra_headers={"X-VERAIA-Notice-Id": notice.notice_id},
        )


def build_mail_client() -> SMTPMailClient:
    """Cliente según el entorno: captura local por defecto, SMTP real con `VERAIA_MAIL_MODE=real`."""
    if os.environ.get("VERAIA_MAIL_MODE", "capture").strip().lower() == "real":
        return SMTPMailClient(MailSettings.from_env())
    return SMTPMailClient()
