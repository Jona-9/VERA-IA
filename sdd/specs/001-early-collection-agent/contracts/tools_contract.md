# Contract: Action Tools with Tool-Enforced Boundaries

**Purpose**: Formalizar las herramientas de acción invocables por el agente orquestador, garantizando que todos los límites de seguridad y reglas de buen trato residan en el código de las herramientas (RF-11, Principio II de la Constitución).

## 1. Herramienta: `ScheduleNoticeTool`

### Responsabilidad
Valida las precondiciones duras de política y programa un aviso de cobranza en el sistema. Si alguna regla de política o estado de pago no se cumple, la herramienta **rechaza deterministamente** la solicitud y arroja un error tipificado.

### Esquema de Entrada (Pydantic Contract)
```python
from datetime import date
from pydantic import BaseModel, Field, EmailStr

class ScheduleNoticeInput(BaseModel):
    account_id: str = Field(description="Identificador de la cuenta u obligación")
    evaluation_id: str = Field(description="Identificador de la evaluación que justifica el aviso")
    risk_band: str = Field(description="Banda de riesgo estimada ('BAJA', 'MODERADA', 'ALTA', 'CRITICA')")
    scheduled_date: date = Field(description="Fecha propuesta para el envío dentro de la ventana")
    tone: str = Field(description="Tono autorizado ('NEUTRAL', 'PREVENTIVE', 'FIRM')")
    subject: str = Field(description="Asunto del correo redactado")
    body_text: str = Field(description="Cuerpo del mensaje validado previamente por ToneGuard")
```

### Esquema de Salida
```python
class ScheduleNoticeOutput(BaseModel):
    success: bool
    notice_id: Optional[str] = None
    status: str  # 'APPROVED', 'REJECTED'
    rejection_code: Optional[str] = None
    message: str
```

### Validaciones Duras Inviolables (Código Ejecutado en la Herramienta)
1. **Regla de No Contacto si Pagó**: La herramienta consulta el saldo corriente y los pagos del ciclo. Si el saldo es 0 o existe un pago registrado, rechaza con código `ERR_ALREADY_PAID`.
2. **Regla de Pago en Trámite**: Si existen registros de pago en proceso (`IN_PROCESS`), rechaza con código `ERR_PAYMENT_IN_PROGRESS`.
3. **Regla de Ventana Autorizada**: Compara `scheduled_date` contra `due_date`:
   - Si la fecha está fuera de la ventana declarada en la política para la banda dada, rechaza con código `ERR_OUTSIDE_WINDOW`.
4. **Regla de Máximo de Avisos**: Cuenta los avisos despachados/aprobados para el cliente en el ciclo actual. Si $\text{notices\_count} \ge \text{max\_notices}$, rechaza con código `ERR_MAX_NOTICES_EXCEEDED`.
5. **Regla de Separación Mínima**: Si la fecha del último aviso despachado está a menos días de `min_separation_days`, rechaza con código `ERR_MIN_SEPARATION_VIOLATED`.
6. **Regla de Restricción de Tono Firme**: Si `tone == 'FIRM'` y `scheduled_date <= due_date` o `risk_band` no es 'ALTA'/'CRITICA', rechaza con código `ERR_INVALID_TONE_FOR_BAND`.

---

## 2. Herramienta: `FetchPendingPaymentsTool`

### Responsabilidad
Permite al agente consultar si existen transacciones bancarias en trámite para investigar casos inconsistentes (RF-09).

### Esquema de Entrada
```python
class FetchPendingPaymentsInput(BaseModel):
    account_id: str
    cutoff_date: date
```

### Esquema de Salida
```python
class PendingPaymentItem(BaseModel):
    payment_id: str
    amount: float
    reported_date: date
    channel: str
    status: str

class FetchPendingPaymentsOutput(BaseModel):
    account_id: str
    pending_payments: List[PendingPaymentItem]
    has_unreflected_payment: bool
```

---

## 3. Herramienta: `ReevaluateClientTool`

### Responsabilidad
Dispara una reevaluación inmediata de un cliente tras una corrección de datos ingresada en la cola de revisión por el analista (RF-13).

### Esquema de Entrada
```python
class ReevaluateClientInput(BaseModel):
    account_id: str
    cutoff_date: date
    reason: str
```

### Esquema de Salida
```python
class ReevaluateClientOutput(BaseModel):
    account_id: str
    new_risk_band: str
    new_action: str
    decision_updated: bool
    summary: str
```
