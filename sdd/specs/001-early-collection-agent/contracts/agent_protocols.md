# Contract: Agent Protocols, LLM Isolation & Deterministic Fallback

**Purpose**: Formalizar las interfaces de asistencia del agente (investigación y redacción) asegurando el principio constitucional de desacoplamiento de PII (Principio XI), el principio de que la IA redacta pero no decide (Principio III) y la capacidad de ejecución 100% desconectada mediante fallback determinista.

---

## 1. Protocolo: `MessageDrafter`

### Contrato de Redacción Controlada
```python
from typing import Protocol, Optional
from pydantic import BaseModel, Field

class DraftContext(BaseModel):
    # ATENCIÓN: No incluye nombres reales, documentos de identidad ni números de tarjeta
    client_reference: str = Field(description="Identificador anonimizado local")
    tone: str = Field(description="'NEUTRAL', 'PREVENTIVE', 'FIRM'")
    days_to_due: int = Field(description="Días para el vencimiento (negativo si ya venció)")
    amount_due: float = Field(description="Monto adeudado en formato numérico")
    due_date_str: str = Field(description="Fecha de vencimiento formateada")
    institution_name: str = Field(default="Entidad Financiera Demo")

class DraftedMessage(BaseModel):
    subject: str
    body_text: str
    used_llm: bool

class MessageDrafter(Protocol):
    def draft(self, context: DraftContext) -> DraftedMessage:
        """Genera un borrador de mensaje adaptado al contexto y tono."""
        ...
```

### Implementaciones:
1. **`LLMMessageDrafter`**:
   - Construye un prompt con pocas muestras (*few-shot*) y directrices estrictas: "Redacta un recordatorio bancario formal. Tono: {tone}. No uses palabras intimidatorias ni menciones bandas de riesgo o morosidad."
   - Conecta a un endpoint compatible (OpenAI / Ollama local).
   - Inyecta únicamente el `DraftContext` anonimizado.
2. **`DeterministicMessageDrafter`**:
   - Utiliza plantillas Jinja2 preaprobadas por tono (`templates/neutral.j2`, `templates/preventive.j2`, `templates/firm.j2`).
   - Se activa por defecto si no existe una API Key configurada o si el endpoint LLM no responde en < 2 segundos.

---

## 2. Validador de Ética y Tono: `ToneGuardValidator`

### Reglas de Validación Pre-Envío
Antes de autorizar un mensaje para programación, el validador inspecciona el texto contra las siguientes restricciones:
1. **Prohibición de Mención de Bandas**: El texto no debe contener términos como `"Banda"`, `"Riesgo Alto"`, `"Score"`, `"Puntuación crediticia"`, ni `"Calificación interna"`.
2. **Prohibición de Lenguaje Ofensivo o Coercitivo**: Búsqueda por lista de exclusión y análisis léxico contra términos estigmatizantes: `"moroso"`, `"deudor rebelde"`, `"demanda"`, `"embargo"`, `"cárcel"`, `"reporte inmediato a centrales"`.
3. **Restricción de Tono Firme en Preventivo**: Si `days_to_due >= 0` (antes del vencimiento), el texto no debe contener apremios de urgencia desmedida.
4. **Comportamiento ante Fallo**: Si la validación detecta cualquier incumplimiento, el texto se descarta y se aplica automáticamente la plantilla estándar correspondiente (`DeterministicMessageDrafter`).

---

## 3. Protocolo: `InconsistencyInvestigator`

### Contrato de Investigación de Hipótesis
```python
from typing import Protocol, List
from pydantic import BaseModel

class InvestigationContext(BaseModel):
    account_id: str
    billed_amount: float
    current_balance: float
    days_past_due: int
    pending_payments: List[dict]
    discrepancy_description: str

class InvestigationResult(BaseModel):
    hypothesis: str
    verified: bool
    recommended_action: str  # 'WAIT_FOR_CLEARING', 'ESCALATE_HUMAN', 'PROCEED'
    explanation: str

class InconsistencyInvestigator(Protocol):
    def investigate(self, context: InvestigationContext) -> InvestigationResult:
        """Formula y evalúa una hipótesis sobre la inconsistencia observada."""
        ...
```

### Implementaciones:
1. **`DeterministicInvestigator`**:
   - Evalúa si existe un pago en `pending_payments` cuyo monto sea $\ge$ pago mínimo y cuya fecha esté dentro de los 2 días de tolerancia.
   - Si se cumple: formula la hipótesis *"Pago en proceso de acreditación bancaria (demora interbancaria de 48h)"*, marcando `verified=True` y recomendando `WAIT_FOR_CLEARING`.
   - Si no se cumple: marca `verified=False` y recomienda `ESCALATE_HUMAN` con el expediente estructurado.
2. **`LLMInconsistencyInvestigator`**:
   - Asiste en la redacción detallada de la nota de derivación para el analista humano, resumiendo los hechos observados.
