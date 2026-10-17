# Plan de Acción: Arquitectura de Agente Constitucional con Gobernanza Determinista
## VERA · Solución para Cobranza Temprana

Este documento consolida la arquitectura técnica, corrige las desviaciones detectadas y establece la hoja de ruta para consolidar de manera irrefutable la propuesta de valor institucional:

> **"En la banca, la IA autónoma sin control es una pesadilla regulatoria y de riesgo reputacional. Nadie en un banco pondrá a un LLM libre a decidir cuándo exigir un cobro a un cliente o enviarle mensajes a horas indebidas.**
>
> **Por eso en VERA diseñamos una Arquitectura de Agente Constitucional con Gobernanza Determinista:**
> 1. **Machine Learning calibrado (Platt scaling)** que estima el riesgo de impago sin sesgo ni fuga temporal.
> 2. **Políticas de buen trato e histéresis** codificadas en reglas matemáticas inviolables dentro de las herramientas de despacho, no en la buena voluntad del prompt.
> 3. **IA Generativa confinada a redacción asistida y síntesis explicativa**, operando a través de OpenRouter (`openai/gpt-4o-mini`), siempre supervisada por ToneGuard y bajo la regla de oro: *ante la mínima inconsistencia o duda, la IA se detiene y deriva al analista humano*."

---

## 0. Stack Tecnológico de VERA

La solución opera bajo una arquitectura desacoplada de alto rendimiento:
* **Frontend:** Single Page Application (SPA) construida en **React 19 + Vite + TypeScript + Tailwind CSS** (`frontend/`).
  * Vistas principales: **Hoy** (`TodayView.tsx`), **Por revisar** (`ReviewQueueView.tsx`), **Notificaciones** (`NoticesView.tsx`), **Clientes** (`PortfolioView.tsx`) y **Dashboard** (`DashboardView.tsx`).
* **Backend API:** **FastAPI (Python 3.12)** asíncrono (`src/api/main.py`) con validación estricta de esquemas Pydantic V2.
* **Motor LLM:** **OpenRouter API** (`https://openrouter.ai/api/v1`) utilizando el modelo `openai/gpt-4o-mini`.
  * Integración activa mediante `src/agent/llm.py` y credenciales centralizadas en `.env`.
* **Persistencia y Simulación:** SQLite3 relacional transaccional (`data/portfolio_demo.db`), scikit-learn para riesgo y servidor SMTP local honeypot (`127.0.0.1:1025`).

---

## 1. Problema 1: Traspasar la "Ilusión Agentic" a un Agente ReAct Dual

### Diagnóstico Crítico
El sistema anterior ejecutaba un flujo procedimental simple. Para consolidar el valor del hackathon, el agente debe formular hipótesis explícitas, emitir trazas de pensamiento auditables (*Chain of Thought*) y utilizar herramientas gobernadas por límites deterministas.

### Objetivo
Consolidar el **Agente ReAct (Reasoning + Acting) Dual-Engine**, donde el agente inspeccione el expediente, emita trazas de pensamiento auditables y utilice herramientas gobernadas por límites deterministas.

### Tareas de Implementación
- [x] **1.1. Conexión de IA Generativa mediante OpenRouter**:
  - Implementado cliente `LLMClient` en `src/agent/llm.py` con autodetección de proveedor OpenRouter, autenticación por Bearer Token y cabeceras institucionales (`X-Title: VERA`, `HTTP-Referer`).
  - Clave de API activa configurada en `.env` (`VERAIA_LLM_API_KEY`) con proveedor OpenRouter y modelo `openai/gpt-4o-mini`.
- [x] **1.2. Herramientas de Dominio con Contratos Estrictos (Tool Protocol)**:
  - `ScheduleNoticeTool` (`src/tools/schedule_tool.py`): Control inviolable de topes de contacto, ventanas permitidas y separación entre avisos.
  - `ReevaluateClientTool` (`src/tools/reevaluate_tool.py`): Reevaluación inmediata tras corrección humana de pagos en trámite con anulación reactiva de avisos aprobados.
  - `ToneGuardValidator` (`src/agent/validator.py`): Salvaguarda léxica y ética contra términos despectivos o mención de bandas de riesgo internas.
- [ ] **1.3. Ciclo de Razonamiento ReAct Híbrido (`src/agent/agent_loop.py`)**:
  - **Modo Determinista Offline**: Generación de traza estructurada con derivación de hipótesis en caso de desconexión.
  - **Modo LLM Activo (OpenRouter)**: El LLM recibe contexto 100% anonimizado (sin nombres ni identificadores de cuenta), sintetiza los hallazgos y formula la hipótesis para el analista.
  - Ejemplo de traza de auditoría generada:
    ```json
    {
      "step": 1,
      "thought": "Cliente presenta utilización de 95% y 3 pagos mínimos sostenidos. Señal de deterioro temprano detectada.",
      "action": "InvestigatePendingPaymentsTool",
      "observation": "Existe un pago pendiente de $256,14 reportado hace 2 días en proceso de compensación.",
      "thought": "Inconsistencia detectada: el cliente ya emitió su pago. Prohibido despachar aviso preventivo bajo Principio II.",
      "action": "EscalateToReviewQueueTool",
      "final_verdict": "Derivado a cola de revisión humana con hipótesis de pago en trámite."
    }
    ```
- [x] **1.4. Visualización de Razonamiento en la UI (React + TypeScript)**:
  - En [`ReviewQueueView.tsx`](file:///Users/jonatl9/Desktop/VERAIA/frontend/src/views/ReviewQueueView.tsx), [`TodayView.tsx`](file:///Users/jonatl9/Desktop/VERAIA/frontend/src/views/TodayView.tsx) y [`DashboardView.tsx`](file:///Users/jonatl9/Desktop/VERAIA/frontend/src/views/DashboardView.tsx) se visualizan:
    - Estado de cada caso (`Pendiente hoy` vs `Arrastrado de ayer`).
    - Contexto consolidado del cliente (saldo, límite, utilización, riesgo).
    - **Por qué debe ser aprobado manualmente**: Justificación basada en la política bancaria.
    - Hipótesis preliminar formulada por el agente.

---

## 2. Problema 2: Complejidad Estocástica y Arquetipos en Simulación

### Diagnóstico Crítico
El simulador original utilizaba fórmulas lineales que facilitaban un aprendizaje predecible. Es necesario dotar al entorno de comportamiento de clientes con incertidumbre y patrones realistas.

### Objetivo
Dotar al simulador y al modelo de **arquetipos no lineales y dinámica adaptativa real**, demostrando que el agente aprende y generaliza ante escenarios no homogéneos.

### Tareas de Implementación
- [ ] **2.1. Arquetipos de Comportamiento en `src/simulation/engine.py`**:
  1. *El Olvidadizo / Desorganizado*: Solvente, bajo uso de línea; responde favorablemente y adelanta su pago al recibir el recordatorio.
  2. *El Estrangulado Financiero*: Utilización > 90%, abona mínimos; insensible a recordatorios de cobro y requiere propuesta de refinanciamiento.
  3. *El Pagador de Fin de Quincena*: Paga en fechas fijas laborales sin importar cuándo venza la cuota.
  4. *El Caso en Discrepancia*: Reporta pago por transferencia o reclamo no reflejado, gatillando derivación humana.
- [ ] **2.2. Robustecer Entrenamiento de Machine Learning (`src/analytics/signals.py`)**:
  - Incorporar variables derivadas no lineales: aceleración de consumo de línea y volatilidad de montos abonados ($\sigma_{\text{paid}} / \mu_{\text{billed}}$).
  - Mantener calibración de probabilidades con Platt Scaling (Scikit-Learn).
- [x] **2.3. Multi-Armed Bandit ε-Greedy Contextual (`src/policy/bandit.py`)**:
  - Aprendizaje por refuerzo para seleccionar el mejor día de envío dentro de la ventana autorizada de política, penalizando contactos innecesarios.

---

## 3. Problema 3: Guardrail de Tono en 2 Fases (ToneGuard v2)

### Diagnóstico Crítico
El validador léxico por expresiones regulares previene palabras despectivas directas (`"moroso"`, `"cárcel"`), pero requiere una segunda fase semántica para evitar presiones pasivo-agresivas sutiles o tonos apremiantes no justificados.

### Objetivo
Construir un **Guardrail de Tono Híbrido en 2 Fases**: barrera determinista ultra-rápida (O(1)) combinada con verificación semántica contextual asistida por OpenRouter o heurística sintáctica.

### Tareas de Implementación
- [x] **3.1. Fase 1 - Barrera Determinista y Ética (`src/agent/validator.py`)**:
  - Detección estricta de fuga de datos internos: `"Banda Alta"`, `"Score"`, `"Probabilidad"`.
  - Prohibición de calificativos humillantes o coercitivos directos.
- [ ] **3.2. Fase 2 - Análisis Semántico y Coerción Indirecta (`SemanticToneEvaluator`)**:
  - Verificación de patrones condicionales amenazantes (*"evite que tengamos que reportarlo"*, menciones a terceros o empleadores).
  - Clasificación rápida mediante LLM OpenRouter (`openai/gpt-4o-mini`) en categorías: `[RESPECTFUL, NEUTRAL, URGENT, COERCIVE, THREATENING]`.
- [x] **3.3. Fallback Seguro a Plantillas Inmutables**:
  - Si el LLM o el validador detectan cualquier anomalía o timeout, el sistema sustituye el mensaje en el acto por la plantilla neutra Jinja2 preaprobada (`src/templates/neutral.j2`), registrando la auditoría inmutable.

---

## 4. Estado de Implementación y Checklist Técnico

| Componente | Estado | Detalle |
| :--- | :---: | :--- |
| **Frontend React 19 + Vite + TypeScript** |  Completado | Totalmente operativo en `frontend/` con Tailwind, Navbar VERA y SPA sin parpadeos. |
| **Backend FastAPI REST** |  Completado | Endpoints en `src/api/main.py` integrando simulación, cartera, revisión y dashboard. |
| **Integración OpenRouter LLM** |  Completado | Clave `sk-or-v1-...` configurada en `.env`, cliente `LLMClient` probado y funcionando. |
| **Vista Dashboard Unificada** |  Completado | KPI de resolución IA (90%) vs humana (10%), casos pendientes y benchmark comparativo. |
| **Arrastre Automático (Carry-over)** |  Completado | Casos no revisados pasan automáticamente a la cola del día siguiente como `Arrastrado de ayer`. |
| **Eliminación de Horas Fijas** |  Completado | Todo el sistema unificado bajo conceptos de jornada diaria (`revisión hoy`, `despacho de avisos`). |
| **Arquetipos No Lineales de Simulación** | ⏳ Próximo paso | Enriquecimiento de `CustomerBehavior` en `src/simulation/engine.py`. |
| **ToneGuard Fase 2 (Semántico con LLM)** | ⏳ Próximo paso | Evaluación semántica zero-shot usando el cliente OpenRouter. |

---

## 5. El Guión Definitivo para el Jurado

1. **El Problema Real de la Banca**:
   *"La cobranza tradicional quema dinero disparando mensajes automáticos a ciegas, mientras que la IA generativa sin control asusta a los bancos por riesgo de alucinación y demandas legales."*
2. **La Solución: VERA**:
   *"No creamos un chatbot que habla sin control. Diseñamos un Agente Constitucional donde la inteligencia predictiva detecta el riesgo antes del atraso, pero el poder de acción está restringido por límites matemáticos e inviolables en el software."*
3. **La Demo en Vivo**:
   - Mostrar el **Dashboard**: 90% resuelto de forma 100% autónoma por la IA y 10% derivado a analista con justificación bancaria explícita.
   - Mostrar a un cliente puntual con pagos mínimos consecutivos (detección temprana de deterioro).
   - Mostrar la hipótesis formulada con OpenRouter al investigar un pago en trámite.
   - Mostrar el arrastre automático de casos a la cola del siguiente día cuando el analista no interviene hoy.
   - Demostrar el rechazo ético de ToneGuard y el bloqueo de avisos no permitidos por política.
4. **Cierre Contundente**:
   *"VERA no reemplaza al equipo de cobranza; le da superpoderes analíticos con la tranquilidad de que ninguna regla de negocio o regulación bancaria puede ser violada."*
