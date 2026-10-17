# Plan de Acción: Transformación hacia la Arquitectura de Agente Constitucional
## VERA-IA · Hackathon Vertical Slice

Este documento define las acciones técnicas concretas para subsanar las 3 grandes grietas arquitectónicas detectadas en la solución y consolidar de manera irrefutable la propuesta de valor:

> **"En la banca, la IA autónoma sin control es una pesadilla regulatoria y de riesgo reputacional. Nadie en un banco pondrá a un LLM libre a decidir cuándo amenazar a un cliente o enviarle mensajes a las 3 de la mañana.**
>
> **Por eso en VERA-IA diseñamos una Arquitectura de Agente Constitucional con Gobernanza Determinista:**
> 1. **El Machine Learning calibrado (Platt scaling)** estima el riesgo sin sesgo ni fuga temporal.
> 2. **Las políticas de buen trato e histéresis** residen en código inviolable dentro de las herramientas de despacho, no en la buena voluntad del prompt.
> 3. **La IA Generativa queda confinada a la redacción y síntesis**, siempre supervisada por guardianes de tono y bajo la regla de oro: *ante la mínima inconsistencia o duda, la IA se detiene y deriva al analista humano*."

---

## 1. Problema 1: El Elefante en la Habitación (La Ilusión Agentic)

### Diagnóstico Crítico
Actualmente, el sistema ejecuta un flujo procedimental clásico en `src/agent/orchestrator.py` con `if/else` estáticos. El LLM está desactivado por defecto (`from_env() -> None`) y solo se usa para rellenar texto cosmético. No hay un ciclo de razonamiento ni uso deliberado de herramientas (*Tool Calling*). Para un evaluador técnico, esto parece un script cron tradicional con marketing de IA.

### Objetivo
Transformar el orquestador en un **Agente ReAct (Reasoning + Acting) con Ejecución de Herramientas**, donde el agente inspeccione el expediente, emita trazas de pensamiento auditables (*Chain of Thought*) y utilice herramientas gobernadas por límites deterministas.

### Tareas Concretas de Implementación

- [ ] **1.1. Exponer la Capa de Herramientas como Tool Protocol**:
  - Envolver las operaciones en herramientas con contrato formal:
    - `QueryAccountSignalsTool(account_id, cutoff_date)`
    - `InvestigatePendingPaymentsTool(account_id)`
    - `EvaluatePolicyComplianceTool(account_id, proposed_action)`
    - `DraftProtectedNoticeTool(account_id, tone)`
    - `ScheduleNoticeTool(account_id, scheduled_date, ...)`
    - `EscalateToReviewQueueTool(account_id, reason, hypothesis)`

- [ ] **1.2. Implementar el Agente de Razonamiento Híbrido (Dual-Engine)**:
  - En `src/agent/agent_loop.py`, implementar un ciclo de razonamiento ReAct:
    - **Modo Offline/Heurístico (Fallback determinista)**: Genera la traza de razonamiento estructurada paso a paso sin requerir API externa.
    - **Modo LLM Activo (OpenAI / Ollama / Gemini)**: El modelo recibe el contexto anonimizado, formula la hipótesis, decide qué herramienta invocar y emite su justificación.
  - Ejemplo de traza de auditoría generada:
    ```json
    {
      "step": 1,
      "thought": "Cliente CUST-02 presenta utilización de 95% y 3 pagos mínimos. Señal de deterioro temprano detectada.",
      "action": "InvestigatePendingPaymentsTool",
      "observation": "Existe un pago pendiente de $950 del 14/10 en proceso de compensación.",
      "thought": "Inconsistencia detectada: el cliente intentó pagar. Prohibido despachar aviso de cobranza bajo Principio II.",
      "action": "EscalateToReviewQueueTool",
      "final_verdict": "Derivado a cola de revisión humana con hipótesis de pago diferido."
    }
    ```

- [ ] **1.3. Visibilizar el Razonamiento del Agente en la UI de Streamlit**:
  - En la vista `src/ui/views/portfolio.py` y `review_queue.py`, agregar un expander colapsable:  
    `st.expander("🧠 Traza de Razonamiento del Agente Constitucional")`  
    mostrando el log de pensamiento y las herramientas que el agente consultó antes de tomar la decisión.

---

## 2. Problema 2: El Sesgo de Confirmación en ML y Simulación

### Diagnóstico Crítico
El simulador (`CustomerBehavior`) genera los pagos con una fórmula lineal fija (`0.88 - 0.9 * delinquency - 0.3 * utilization`). Luego, la Regresión Logística aprende exactamente esa misma combinación lineal, obteniendo métricas artificialmente altas (`AUC = 0.88`). Igualmente, el Multi-Armed Bandit descubre un `REMINDER_LIFT` estático que está quemado en código.

### Objetivo
Dotar al simulador y al modelo de **complejidad estocástica no lineal, arquetipos de clientes y dinámica adaptativa real**, demostrando que el agente aprende y generaliza ante incertidumbre real.

### Tareas Concretas de Implementación

- [ ] **2.1. Introducir Arquetipos de Comportamiento No Lineal en el Simulador**:
  - En `src/simulation/engine.py`, reemplazar la fórmula única por 4 arquetipos con dinámicas realistas:
    1. *El Olvidadizo / Desorganizado*: Solvente, bajo uso de línea, pero con alta dispersión de fechas; reacciona inmediatamente al primer recordatorio preventivo.
    2. *El Estrangulado por Línea*: Utilización > 90%, paga solo mínimos; un recordatorio no adelanta su pago, solo un plan de refinanciamiento.
    3. *El Pagador Quincenal*: Paga estrictamente los días 15 y 30 sin importar cuándo venza la cuota; los recordatorios en otras fechas tienen cero efecto.
    4. *El Disputador / En Aclaración*: Retiene el pago por discrepancia de cobro (gatilla investigación).

- [ ] **2.2. Robustecer el Entrenamiento de Machine Learning**:
  - En `src/analytics/signals.py`, incluir interacciones no lineales:
    - Ratio de aceleración del uso de saldo en los últimos 60 días.
    - Volatilidad de los montos abonados ($\sigma_{\text{paid}} / \mu_{\text{billed}}$).
  - En `src/cli/train_model.py`, evaluar la calibración con validación cruzada estratificada sobre datos con ruido Gaussiano y perturbaciones de estacionalidad.

- [ ] **2.3. Dinamizar el Multi-Armed Bandit**:
  - En `src/policy/bandit.py`, permitir que el reward considere no solo si pagó, sino la **eficiencia del contacto**:
    $$\text{Reward} = \mathbb{I}(\text{pago}) \times \left(1 + \frac{\text{días de anticipación}}{10}\right) - \text{costo de contacto}$$
  - El Bandit debe segmentar el aprendizaje por banda de riesgo (Bandit contextual simple), evitando converger a un valor idéntico para todos los clientes.

---

## 3. Problema 3: ToneGuard (De Regex Simple a Guardrail Híbrido)

### Diagnóstico Crítico
`ToneGuardValidator` depende únicamente de listas regex de palabras prohibidas (`"moroso"`, `"cárcel"`). Una amenaza pasivo-agresiva sin palabras clave explícitas (*"Sabemos dónde trabajas y tus colegas se enterarán si no pagas"*) pasa el filtro como válida (`PASSED`).

### Objetivo
Construir un **Guardrail de Tono en 2 Fases (Híbrido)**: una barrera determinista rápida (Regex / Léxica) combinada con una verificación semántica contextual (Heurística de Urgencia Sintáctica o LLM Evaluator).

### Tareas Concretas de Implementación

- [ ] **3.1. Fase 1 - Reglas Léxicas Expandidas y Normalizadas**:
  - Mantener en `src/agent/validator.py` el filtro determinista instantáneo (O(1)) para violaciones obvias:
    - Términos internos: `"Banda Alta"`, `"Score"`, `"Probabilidad de mora"`.
    - Términos despectivos directos.

- [ ] **3.2. Fase 2 - Análisis Semántico y Detección Pasivo-Agresiva**:
  - Implementar `SemanticToneEvaluator`:
    - **Modo Ligero (sin dependencias externas)**: Análisis de polaridad y patrones sintácticos de coerción indirecta:
      - Condicionales de advertencia (*"si no realiza...", "evite que tengamos que..."*).
      - Menciones a terceros (*"familiares", "empleador", "referencias"*).
      - Signos de exclamación reiterados o imperativos de urgencia en fechas no vencidas.
    - **Modo LLM / Small Model (opcional)**: Prompt estricto de clasificación *zero-shot* que categoriza el mensaje en: `[RESPECTFUL, NEUTRAL, URGENT, COERCIVE, THREATENING]`. Si clasifica en `COERCIVE` o `THREATENING`, bloquea el despacho.

- [ ] **3.3. Fallback Seguro y Determinista**:
  - Si cualquiera de las dos fases detecta riesgo o si el evaluador falla por timeout, el sistema sustituye inmediatamente el texto por la plantilla preaprobada `src/templates/neutral.j2`.
  - Registrar la violación en la pista de auditoría (`AuditLogEntry`) con el fragmento sospechoso tipificado.

- [ ] **3.4. Pruebas Unitarias de Ataques Adversarios**:
  - Agregar en `tests/unit/test_tone_validator.py` casos de prueba explícitos con lenguaje pasivo-agresivo e insinuaciones indirectas para certificar que el nuevo validador los capture.

---

## 4. Cronograma de Ejecución Rápida (Sprints de 2 Horas)

| Bloque | Foco Principal | Entregable Clave |
| :--- | :--- | :--- |
| **Hora 1 - 2** | **Guardrail de Tono (ToneGuard v2)** | Detección semántica pasivo-agresiva + tests unitarios adversarios. |
| **Hora 3 - 4** | **Complejidad de Simulación y Arquetipos** | 4 arquetipos de clientes en `CustomerBehavior` + señales no lineales. |
| **Hora 5 - 6** | **Traza de Razonamiento del Agente (ReAct)** | Log auditable de pensamiento y herramientas visibles en la UI de Streamlit. |
| **Hora 7** | **Alineación del Pitch y Demo Final** | Ensayo del pitch bajo la narrativa del Agente Constitucional. |

---

## 5. El Guión Definitivo para el Jurado

Cuando presentes el proyecto, utiliza esta estructura narrativa:

1. **El Problema Real de la Banca**:
   *"La cobranza tradicional quema dinero disparando mensajes automáticos a ciegas, mientras que la IA generativa sin control asusta a los bancos por riesgo de alucinación y demandas legales."*
2. **La Solución: VERA-IA**:
   *"No creamos un chatbot que habla sin control. Diseñamos un Agente Constitucional donde la inteligencia predictiva detecta el riesgo antes del atraso, pero el poder de acción está restringido por límites matemáticos e inviolables en el software."*
3. **La Demo en Vivo**:
   - Mostrar a un cliente puntual que empieza a pagar mínimos (detección temprana).
   - Mostrar la traza de razonamiento del agente investigando un pago en trámite.
   - Mostrar cómo ToneGuard neutraliza un intento de mensaje apremiante.
   - Mostrar la cola de supervisión humana: *el humano tiene la última palabra*.
4. **Cierre Contundente**:
   *"VERA-IA no reemplaza al equipo de cobranza; le da superpoderes analíticos con la tranquilidad de que ninguna regla de negocio o regulación bancaria puede ser violada."*
