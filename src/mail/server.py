"""
Servidor SMTP de captura local embebido (RF-15, Principio XII).

Levanta `aiosmtpd` en un hilo daemon escuchando únicamente en loopback (127.0.0.1:1025 por
defecto). Todo mensaje recibido se persiste como `CapturedEmail` en un `CaptureStore`
(memoria o SQLite) y NUNCA se reenvía: el servidor es un sumidero sin capacidad de relay.
"""

import sqlite3
import threading
import uuid
from datetime import datetime
from email import message_from_bytes, policy
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple, Union

from aiosmtpd.controller import Controller

from src.domain.entities import CapturedEmail

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1025
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class UnsafeSMTPBindError(ValueError):
    """Se intentó exponer el servidor de captura fuera de la interfaz loopback."""


class CaptureStore(Protocol):
    def add(self, email: CapturedEmail) -> None: ...
    def list(self) -> List[CapturedEmail]: ...
    def clear(self) -> None: ...


class InMemoryCaptureStore:
    """Bandeja en memoria, segura entre hilos."""

    def __init__(self):
        self._emails: List[CapturedEmail] = []
        self._lock = threading.Lock()

    def add(self, email: CapturedEmail) -> None:
        with self._lock:
            self._emails.append(email)

    def list(self) -> List[CapturedEmail]:
        with self._lock:
            return list(self._emails)

    def clear(self) -> None:
        with self._lock:
            self._emails.clear()


class SQLiteCaptureStore:
    """Bandeja persistida en la tabla `captured_emails` (una conexión por operación)."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS captured_emails (
                    email_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    captured_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def add(self, email: CapturedEmail) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO captured_emails VALUES (?, ?, ?, ?, ?, ?)",
                (email.email_id, email.sender, email.recipient, email.subject,
                 email.raw_content, email.captured_at.isoformat()),
            )

    def list(self) -> List[CapturedEmail]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT email_id, sender, recipient, subject, raw_content, captured_at "
                "FROM captured_emails ORDER BY captured_at"
            ).fetchall()
        return [
            CapturedEmail(email_id=r[0], sender=r[1], recipient=r[2], subject=r[3],
                          raw_content=r[4], captured_at=datetime.fromisoformat(r[5]))
            for r in rows
        ]

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM captured_emails")


class CaptureHandler:
    """Handler aiosmtpd: convierte cada (mensaje, destinatario) en un CapturedEmail."""

    def __init__(self, store: CaptureStore):
        self.store = store

    async def handle_DATA(self, server, session, envelope) -> str:
        raw = envelope.content if isinstance(envelope.content, bytes) else envelope.content.encode()
        parsed = message_from_bytes(raw, policy=policy.default)
        subject = str(parsed.get("Subject", ""))
        raw_text = raw.decode("utf-8", errors="replace")
        captured_at = datetime.now()
        for recipient in envelope.rcpt_tos:
            self.store.add(CapturedEmail(
                email_id=uuid.uuid4().hex,
                sender=envelope.mail_from,
                recipient=recipient,
                subject=subject,
                raw_content=raw_text,
                captured_at=captured_at,
            ))
        return "250 Message captured locally (not relayed)"


class LocalSMTPServer:
    """Servidor de captura en hilo daemon. Uso: `with LocalSMTPServer() as srv: ...`"""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 store: Optional[CaptureStore] = None):
        if host not in LOOPBACK_HOSTS:
            raise UnsafeSMTPBindError(
                f"El servidor de captura solo puede escuchar en loopback, no en '{host}'"
            )
        self.host = host
        self.port = port
        self.store: CaptureStore = store if store is not None else InMemoryCaptureStore()
        self._controller: Optional[Controller] = None

    @property
    def is_running(self) -> bool:
        return self._controller is not None

    def start(self) -> "LocalSMTPServer":
        if self._controller is None:
            controller = Controller(CaptureHandler(self.store), hostname=self.host, port=self.port)
            controller.start()  # aiosmtpd ejecuta su loop en un hilo daemon propio
            self._controller = controller
        return self

    def stop(self) -> None:
        if self._controller is not None:
            self._controller.stop()
            self._controller = None

    def captured(self) -> List[CapturedEmail]:
        return self.store.list()

    def __enter__(self) -> "LocalSMTPServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


_running_servers: Dict[Tuple[str, int], LocalSMTPServer] = {}
_registry_lock = threading.Lock()


def start_embedded_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                          store: Optional[CaptureStore] = None) -> LocalSMTPServer:
    """Idempotente: reutiliza el servidor ya levantado en (host, port).

    Pensado para Streamlit, que re-ejecuta el script en cada interacción.
    """
    with _registry_lock:
        server = _running_servers.get((host, port))
        if server is None or not server.is_running:
            server = LocalSMTPServer(host, port, store).start()
            _running_servers[(host, port)] = server
        return server


def stop_embedded_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    with _registry_lock:
        server = _running_servers.pop((host, port), None)
    if server is not None:
        server.stop()
