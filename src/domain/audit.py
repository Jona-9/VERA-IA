"""
Modelo y utilidades de auditoría inmutable para VERAIA.
Garantiza el cumplimiento del Principio Constitucional VII (Trazabilidad completa).
"""

from datetime import datetime
from typing import Dict, Any, Optional
import uuid
from src.domain.entities import AuditLogEntry


def create_audit_entry(
    account_id: str,
    event_type: str,
    actor: str,
    payload: Dict[str, Any],
    log_id: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> AuditLogEntry:
    """Crea una instancia validada de AuditLogEntry con valores por defecto."""
    return AuditLogEntry(
        log_id=log_id or f"LOG-{uuid.uuid4().hex[:12].upper()}",
        account_id=account_id,
        timestamp=timestamp or datetime.now(),
        event_type=event_type,
        actor=actor,
        payload=payload,
    )
