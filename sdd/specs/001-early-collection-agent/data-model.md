# Data Model & Domain Entities: Agente de Cobranza Temprana

**Feature**: `001-early-collection-agent`  
**Date**: 2026-10-17  
**Status**: Complete  

## 1. Visión General del Modelo

El modelo de datos está diseñado para cumplir con los principios de integridad temporal (Principio IV: datos a fecha de corte sin mirar el futuro), trazabilidad completa (Principio VII) y desacoplamiento de datos sensibles (Principio XI). Todos los modelos de dominio se formalizan mediante clases **Pydantic v2** y se persisten en una base de datos relacional local (`SQLite`).

---

## 2. Entidades Principales

### 2.1. Customer (Cliente)
Representa al titular de la cuenta u obligación.
- **`customer_id`** (`str`, PK): Identificador único interno anonimizado (ej. `"CUST-00123"`).
- **`full_name`** (`str`): Nombre de contacto del cliente (utilizado solo para inyección local en la plantilla de correo; jamás transmitido al LLM).
- **`email`** (`str`): Dirección de correo del cliente (en la demo se usan buzones ficticios como `cliente123@demo.veraia.local`).
- **`contact_enabled`** (`bool`): Indicador de si el cliente consiente recibir comunicaciones de contacto (`True` por defecto).
- **`created_at`** (`date`): Fecha de alta del cliente en la cartera.

### 2.2. Account (Obligación / Cuenta)
Representa el producto de crédito o préstamo sujeto a monitoreo.
- **`account_id`** (`str`, PK): Identificador único de la obligación (ej. `"ACC-98765"`).
- **`customer_id`** (`str`, FK): Relación con el cliente titular.
- **`credit_limit`** (`float`): Límite de crédito total asignado a la cuenta.
- **`current_balance`** (`float`): Saldo total adeudado a la fecha de corte.
- **`minimum_payment`** (`float`): Monto mínimo exigible para evitar mora en el período.
- **`due_date`** (`date`): Fecha límite pactada para el pago de la cuota corriente.
- **`status`** (`str`): Estado actual (`"UP_TO_DATE"`, `"PENDING_PAYMENT"`, `"PAID"`, `"OVERDUE"`).

### 2.3. PeriodRecord (Historial de Cuotas / Período)
Registra la evolución mensual/periódica de la obligación. Es la fuente fundamental para el cálculo de señales sin fuga del futuro.
- **`record_id`** (`str`, PK): Identificador del registro histórico.
- **`account_id`** (`str`, FK): Cuenta asociada.
- **`period_index`** (`int`): Índice cronológico del período ($t, t-1, t-2, \dots$).
- **`billing_date`** (`date`): Fecha de emisión y facturación del estado de cuenta.
- **`due_date`** (`date`): Fecha de vencimiento pactada para el período.
- **`billed_amount`** (`float`): Monto total facturado en el período.
- **`paid_amount`** (`float`): Monto efectivamente pagado.
- **`actual_payment_date`** (`date`, nullable): Fecha real en que el cliente realizó el pago.
- **`recorded_payment_date`** (`date`, nullable): Fecha administrativa en que el sistema bancario registró el pago.
- **`days_past_due`** (`int`): Días de atraso reales calculados como $\max(0, \text{actual\_payment\_date} - \text{due\_date})$ o $\text{cutoff\_date} - \text{due\_date}$ si no pagó.
- **`line_utilization`** (`float`): Saldo adeudado dividido por límite de crédito al cierre del período.

### 2.4. SignalSet (Señales de Comportamiento y Deterioro)
Conjunto de indicadores cuantitativos extraídos a una `cutoff_date` específica con datos históricos disponibles hasta esa fecha:
- **`account_id`** (`str`): Cuenta evaluada.
- **`cutoff_date`** (`date`): Fecha de corte en que se toman los datos.
- **`credit_utilization_ratio`** (`float`): Uso actual de la línea de crédito ($\text{saldo} / \text{límite}$).
- **`consecutive_min_payments`** (`int`): Conteo de cuotas consecutivas abonando solo el pago mínimo ($\ge 3$ es señal crítica de deterioro).
- **`payment_to_billed_ratio`** (`float`): Ratio del monto pagado respecto al facturado en el último período.
- **`payment_ratio_drop`** (`float`): Caída porcentual en el ratio de pago respecto al promedio de los últimos 3 períodos.
- **`historical_delinquency_rate`** (`float`): Proporción de períodos pasados con atraso $\ge 1$ día.
- **`max_past_due_days`** (`int`): Máximo número de días de atraso registrado históricamente.
- **`delinquency_trend`** (`float`): Pendiente o variación reciente en días de atraso.

### 2.5. RiskEvaluation (Evaluación y Decisión del Agente)
Resultado de la inferencia analítica y aplicación de políticas para un cliente en un día determinado:
- **`evaluation_id`** (`str`, PK): Identificador único de la evaluación.
- **`account_id`** (`str`, FK): Cuenta evaluada.
- **`evaluation_date`** (`date`): Fecha del ciclo en que se realiza la evaluación.
- **`raw_probability`** (`float`): Probabilidad estimada por el modelo de Regresión Logística.
- **`calibrated_probability`** (`float`): Probabilidad calibrada final tras Platt scaling / isotonic.
- **`risk_band`** (`str`): Banda asignada (`"BAJA"`, `"MODERADA"`, `"ALTA"`, `"CRITICA"`).
- **`previous_risk_band`** (`str`, nullable): Banda previa del cliente para aplicar histéresis.
- **`band_change_confirmed`** (`bool`): Indica si el cambio de banda superó el margen de 0.05 o cumplió 2 ciclos consecutivos.
- **`evidence_quality`** (`str`): Calidad de evidencia (`"SUFFICIENT"`, `"INSUFFICIENT"`, `"INCONSISTENT"`).
- **`action_type`** (`str`): Decisión tomada (`"NO_ACTION"`, `"SCHEDULE_NOTICE"`, `"INVESTIGATE"`, `"ESCALATE_HUMAN"`).
- **`rule_applied`** (`str`): Código o identificador de la regla de política que determinó la acción.
- **`explanation`** (`str`): Justificación textual estructurada de la decisión.

### 2.6. ContactNotice (Aviso de Cobranza)
Mensaje preparado y programado para despacho.
- **`notice_id`** (`str`, PK): Identificador del aviso.
- **`account_id`** (`str`, FK): Cuenta asociada.
- **`evaluation_id`** (`str`, FK): Evaluación que originó el aviso.
- **`channel`** (`str`): Canal formal de contacto (siempre `"EMAIL"`).
- **`scheduled_date`** (`date`): Fecha en que debe enviarse el aviso según la política y la exploración adaptativa.
- **`scheduled_time`** (`str`): Hora prevista de envío (`"10:00:00"`).
- **`tone`** (`str`): Tono asignado (`"NEUTRAL"`, `"PREVENTIVE"`, `"FIRM"`).
- **`subject`** (`str`): Asunto del correo.
- **`body_text`** (`str`): Contenido del mensaje validado.
- **`validation_status`** (`str`): Resultado del ToneGuard (`"PASSED"`, `"FAILED_FALLBACK_APPLIED"`).
- **`status`** (`str`): Estado del aviso (`"SCHEDULED"`, `"APPROVED"`, `"REJECTED_BY_TOOL"`, `"DISPATCHED"`, `"CAPTURED"`).
- **`rejection_reason`** (`str`, nullable): Motivo del rechazo en caso de bloqueo por la herramienta.

### 2.7. ReviewCase (Cola de Revisión Humana)
Casos derivados para supervisión o corrección manual de datos.
- **`case_id`** (`str`, PK): Identificador del caso.
- **`account_id`** (`str`, FK): Cuenta en revisión.
- **`evaluation_id`** (`str`, FK): Evaluación asociada.
- **`days_to_due`** (`int`): Días restantes hasta el vencimiento (criterio de ordenamiento prioritario).
- **`risk_band`** (`str`): Banda de riesgo al momento de la derivación.
- **`reason`** (`str`): Causa de la inconsistencia (ej. `"PENDING_PAYMENT_UNREFLECTED"`).
- **`agent_hypothesis`** (`str`): Hipótesis formulada por el agente (ej. `"Pago de $500 en tránsito de compensación"`).
- **`status`** (`str`): Estado del caso (`"PENDING"`, `"RESOLVED"`, `"DISMISSED"`).
- **`corrected_data`** (`json/str`, nullable): Datos modificados por el analista (ej. nueva fecha de pago).
- **`resolved_by`** (`str`, nullable): Usuario analista que intervino.
- **`resolved_at`** (`datetime`, nullable): Momento de resolución.

### 2.8. CapturedEmail (Bandeja SMTP de Captura Local)
Registro de correos recibidos físicamente por el servidor local `aiosmtpd`.
- **`email_id`** (`str`, PK): Identificador del correo capturado.
- **`sender`** (`str`): Remitente (`noreply@demo.veraia.local`).
- **`recipient`** (`str`): Destinatario capturado.
- **`subject`** (`str`): Asunto.
- **`raw_content`** (`str`): Mensaje RFC 822 íntegro con cabeceras.
- **`captured_at`** (`datetime`): Marca temporal de recepción en el socket local.

### 2.9. AuditLogEntry (Registro Inmutable de Auditoría)
Pista de auditoría exigida por el Principio VII de la constitución.
- **`log_id`** (`str`, PK): Identificador secuencial.
- **`account_id`** (`str`): Cuenta referenciada.
- **`timestamp`** (`datetime`): Momento exacto del evento.
- **`event_type`** (`str`): Tipo de evento (`"EVALUATION"`, `"POLICY_CHECK"`, `"TOOL_ENFORCEMENT"`, `"CORRECTION"`, `"DISPATCH"`).
- **`actor`** (`str`): Agente (`"AGENT"`), Herramienta (`"TOOL_GUARD"`), o Humano (`"SUPERVISOR"`, `"ANALYST"`).
- **`payload`** (`dict/json`): Detalle completo de variables observadas, reglas ejecutadas y resultado.

---

## 3. Diagrama de Transición de Estados

### Ciclo de Vida del Aviso (`ContactNotice`)
```
[EVALUACIÓN AGENTE]
       │
       ▼
[SCHEDULED] ───(Validación de Límites en Herramienta)───► [REJECTED_BY_TOOL] (Bloqueado)
       │ (Cumple límites de política y pago)
       ▼
   [APPROVED]
       │ (Cierre 09:00 / Ejecución 10:00)
       ▼
  [DISPATCHED] ───(Socket SMTP Local)───► [CAPTURED] (Persistido en SQLite)
```

### Ciclo de Vida de la Cuenta (`Account`)
```
[UP_TO_DATE] ──(Deterioro de Señales)──► [AT_RISK (Mod/Alta/Crit)]
     ▲                                                │
     │ (Pago confirmado o en proceso)                 │ (Falta de pago post-vencimiento)
     └────────────────────────────────────────────────┴────────► [OVERDUE]
```
