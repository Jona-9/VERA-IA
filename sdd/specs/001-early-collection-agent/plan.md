# Implementation Plan: Agente de Cobranza Temprana (Vertical Slice Hackathon)

**Branch**: `001-early-collection-agent` | **Date**: 2026-10-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-early-collection-agent/spec.md`

## Summary

Construcción de un vertical slice ejecutable en Python 3.11+ para un agente de cobranza temprana que monitorea señales de deterioro en clientes antes del primer atraso, calcula probabilidades calibradas de mora, aplica políticas deterministas auditables y despacha avisos respetuosos por correo electrónico. La solución implementa límites duros inviolables en las herramientas de acción, desacopla completamente el acceso a datos mediante el patrón repositorio (SQLite local con miras a PostgreSQL), aísla el entorno de pruebas con un servidor SMTP de captura embebido (`aiosmtpd`), ofrece fallback 100% determinista sin dependencias de APIs externas y proporciona una interfaz visual interactiva en Streamlit para el control diario y la comparación contra campañas tradicionales.

## Technical Context

**Language/Version**: Python 3.11 o superior.  
**Primary Dependencies**: pandas, numpy, scikit-learn, Pydantic v2, PyYAML, Jinja2, aiosmtpd, Streamlit, Plotly, pytest.  
**Storage**: SQLite (`sqlite3` estándar) encapsulado tras la interfaz abstracta `PortfolioRepository`. Desviación declarada: PostgreSQL permanece como adaptador futuro sin tocar la lógica de negocio.  
**Testing**: pytest (pruebas unitarias deterministas de señales, modelo, reglas de política y validaciones duras en herramientas).  
**Target Platform**: Ejecución local en estación de trabajo (macOS / Linux / Windows).  
**Project Type**: CLI y aplicación web interactiva local (Streamlit).  
**Performance Goals**: Ejecución del ciclo analítico diario para una cartera simulada de 100+ clientes en menos de 10 segundos; inferencia por cliente < 1 ms.  
**Constraints**: 100% desconectado y autosuficiente (sin Docker obligatorio ni APIs de pago requeridas), límites de envío inviolables en código de herramientas, captura local SMTP de todos los correos, estricto desacoplamiento de PII frente a LLMs.  
**Scale/Scope**: Cartera sintética de 100+ clientes representativos con 6 períodos de historial mensual generado con semilla fija (`seed=42`).  

## Constitution Check

*GATE: Evaluado y verificado frente a `.specify/memory/constitution.md`.*

| Principio Constitucional | Estado | Mecanismo de Garantía en el Diseño |
|--------------------------|--------|------------------------------------|
| **I. Proporcionalidad** | Cumple | Matriz de políticas graduada: 0 avisos preventivos a riesgo bajo; avisos moderados a riesgo alto/crítico. |
| **II. Límites en Herramientas** | Cumple | `ScheduleNoticeTool` rechaza deterministamente envíos fuera de ventana, exceso de cuota o clientes con pago verificado/en trámite. |
| **III. IA Redacta, No Decide** | Cumple | Orquestador determinista define acción, ventana y tono; LLM solo asiste en redacción sobre plantilla con validación obligatoria. |
| **IV. Integridad Temporal** | Cumple | Todas las consultas del repositorio filtran estrictamente por `cutoff_date`; prohibido lookahead. |
| **V. Medición del Atraso** | Cumple | El cálculo de mora utiliza `actual_payment_date` vs `due_date` (1 día post-vencimiento ya es atraso). |
| **VI. Conservadurismo Operativo** | Cumple | Casos dudosos o con pagos no reflejados derivan a cola de revisión; no se despachan avisos sin revisar. |
| **VII. Trazabilidad Total** | Cumple | Entidad `AuditLogEntry` registra hechos, reglas aplicadas, decisiones y actores en cada evento. |
| **VIII. No Estigmatización** | Cumple | `ToneGuardValidator` veta mención a bandas o calificativos despectivos ("moroso") en mensajes al cliente. |
| **IX. Inmutabilidad de Políticas** | Cumple | El agente no puede auto-modificar el archivo YAML de políticas; requiere firma/aprobación de rol supervisor. |
| **X. Honestidad en Resultados** | Cumple | Interfaz y reportes declaran explícitamente el carácter simulado de los datos y conversiones. |
| **XI. Privacidad Estricta** | Cumple | Cero PII transmitida a LLM; personalización de nombres se realiza localmente en plantilla. Fallback offline por defecto. |
| **XII. Captura SMTP Local** | Cumple | Hilo embebido con `aiosmtpd` capturando todos los correos en SQLite; cero salida a internet. |
| **Reglas de Buen Trato** | Cumple | Separación mínima forzosa (>= 2 días en alto/crítico), tono respetuoso obligatorio y exclusión inmediata por pago. |

## Project Structure

### Documentation (this feature)

```text
specs/001-early-collection-agent/
├── plan.md              # Este plan de implementación
├── research.md          # Investigación técnica y decisiones de arquitectura
├── data-model.md        # Entidades del dominio, atributos y estados
├── quickstart.md        # Guía de ejecución y validación paso a paso
├── contracts/           # Contratos de interfaz y esquemas formales
│   ├── repository_contract.md
│   ├── tools_contract.md
│   ├── policy_schema.yaml
│   └── agent_protocols.md
└── tasks.md             # Tareas de descomposición (a generar por /speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── domain/
│   ├── entities.py          # Modelos Pydantic: Customer, Account, PeriodRecord, SignalSet
│   ├── evaluation.py        # RiskEvaluation, RiskBand, EvidenceQuality
│   ├── notices.py           # ContactNotice, Tone, Channel
│   └── audit.py             # AuditLogEntry
├── data/
│   ├── repository.py        # Protocolo abstracto PortfolioRepository
│   ├── sqlite_repo.py       # Implementación SQLite local con transacciones
│   └── generator.py         # Generador de cartera sintética reproducible con semilla fija
├── analytics/
│   ├── signals.py           # Extracción y cálculo de señales a fecha de corte (sin lookahead)
│   ├── model.py             # LogisticRegression + CalibratedClassifierCV
│   └── metrics.py           # Evaluación de discriminación (ROC-AUC) y calibración (Brier Score)
├── policy/
│   ├── config.py            # Cargador y validador de policy.yaml con Pydantic
│   ├── engine.py            # Motor de reglas deterministas, histéresis y tipificación de evidencia
│   └── bandit.py            # Multi-Armed Bandit epsilon-greedy acotado para elección de día
├── tools/
│   ├── schedule_tool.py     # ScheduleNoticeTool con límites duros en código
│   ├── payments_tool.py     # FetchPendingPaymentsTool
│   └── reevaluate_tool.py   # ReevaluateClientTool
├── agent/
│   ├── orchestrator.py      # Orquestador del ciclo diario y máquina de estados
│   ├── drafter.py           # Redactor dual-mode (Jinja2 determinista + LLM opcional)
│   ├── investigator.py      # Investigador de inconsistencias (reglas deterministas + LLM opcional)
│   └── validator.py         # ToneGuardValidator para verificación ética y léxica
├── mail/
│   ├── server.py            # Servidor aiosmtpd embebido para captura local de correos
│   └── client.py            # Cliente de envío local estándar
├── simulation/
│   ├── engine.py            # Motor de reproducción histórica día a día
│   └── benchmark.py         # Simulación en paralelo de campaña fija por segmento
├── ui/
│   └── app.py               # Aplicación interactiva en Streamlit (dashboard integral)
└── cli/
    ├── generate_data.py     # CLI para generación de base de datos dummy
    ├── train_model.py       # CLI para entrenamiento y reporte de métricas
    └── run_cycle.py         # CLI para ejecución por lotes del ciclo diario

tests/
├── unit/
│   ├── test_signals.py          # Pruebas de cálculo de señales a fecha de corte
│   ├── test_model.py            # Pruebas de calibración y discriminación del modelo
│   ├── test_policy_engine.py    # Pruebas de reglas de negocio e histéresis
│   ├── test_tool_enforcement.py  # Pruebas de rechazo determinista en herramientas
│   └── test_tone_validator.py   # Pruebas de exclusión de bandas y lenguaje indebido
├── integration/
│   ├── test_sqlite_repository.py# Pruebas de consultas temporales en SQLite
│   ├── test_smtp_capture.py     # Pruebas de recepción física en socket aiosmtpd
│   └── test_daily_cycle.py      # Pruebas del ciclo diario y cierre de revisión
└── e2e/
    └── test_full_simulation.py  # Prueba de ciclo completo de principio a fin
```

**Structure Decision**: Se adopta una arquitectura modular en Python con separación limpia de responsabilidades (`domain`, `data`, `analytics`, `policy`, `tools`, `agent`, `mail`, `simulation`, `ui`, `cli`), permitiendo pruebas unitarias exhaustivas y desacople total entre el almacenamiento relacional, las políticas y el orquestador del agente.

## Complexity Tracking

| Patrón / Elemento | Justificación Técnica | Alternativa Simple Rechazada y Razón |
|-------------------|-----------------------|--------------------------------------|
| **Patrón Repositorio (`PortfolioRepository`)** | Requisito explícito RF-02: permite operar con SQLite local en la demo mientras se garantiza la incorporación futura de PostgreSQL sin alterar el dominio. | Conexiones SQL directas en el orquestador: Rechazado porque acopla la lógica de negocio a dialectos específicos de base de datos. |
| **Doble Modo en Redacción e Investigación (`Dual-Mode`)** | Requisito de demo local 100% desconectada y principio constitucional de privacidad (sin envío forzoso de datos a servicios externos). | Exigir suscripción a API comercial de LLM: Rechazado porque rompería la restricción de autosuficiencia y reproducibilidad local. |
| **Límites Duros en Código de Herramientas** | Principio Constitucional II: garantiza que ni siquiera un agente alucinando pueda saltarse ventanas, topes de avisos o contactar a quien ya pagó. | Validación por instrucciones en el prompt del agente: Rechazado formalmente por inseguro y no determinista. |
