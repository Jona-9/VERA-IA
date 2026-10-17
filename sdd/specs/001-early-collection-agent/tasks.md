# Tasks: Agente de Cobranza Temprana (Vertical Slice Hackathon)

**Feature**: `001-early-collection-agent`  
**Input**: Plan técnico y especificación (`plan.md`, `spec.md`, `data-model.md`, `contracts/`)  
**Timeline Constraint**: Máximo 3 Sprints para entrega en Hackathon  

---

## 3-Sprint Roadmap Overview

- **Sprint 1: Cimientos de Datos, Modelo de Riesgo y Límites Duros (MVP Core - Fases 1 a 3)**:
  - Entrega del generador dummy reproducible, repositorio SQLite, cálculo de señales a fecha de corte, modelo calibrado (AUC/Brier), validador ToneGuard, herramientas con límites inviolables y servidor SMTP local.
- **Sprint 2: Orquestador del Agente, Ciclo Diario, Cola de Revisión y Auditoría (Fases 4 y 5)**:
  - Entrega de herramientas del agente, investigador de inconsistencias, política para clientes nuevos, corte horario (09:00 / 10:00), cola de revisión reactiva y registro de auditoría inmutable.
- **Sprint 3: Adaptación MAB, Benchmark, Interfaz Streamlit y Ensayo E2E (Fases 6 y 7)**:
  - Entrega de optimización del momento (exploración 10%), comparación contra campaña fija, dashboard interactivo en Streamlit, script `demo.sh` de un solo comando y README de supuestos.

---

## Sprint 1: Cimientos de Datos, Modelo de Riesgo y Límites Duros

### Phase 1: Base y Datos (Setup & Repositorio)

**Purpose**: Inicialización del proyecto, contratos base de configuración y repositorio desacoplado.

- [x] T001 Crear estructura del proyecto y configuración base en `config/politica.yaml`, `config/config.yaml` y `requirements.txt`
- [x] T002 Implementar la interfaz de repositorio abstracto en `src/data/repository.py` y su implementación SQLite en `src/data/sqlite_repo.py` (RF-02)
- [x] T003 Implementar el generador dummy con semilla fija y patrones de clientes (estables, deterioro, crónicos, pagos demorados) en `src/data/generator.py` y `src/cli/generate_data.py` (RF-01)
- [x] T004 [P] Implementar pruebas automatizadas de reproducibilidad e integridad del generador en `tests/unit/test_generator.py`

---

### Phase 2: Riesgo y Señales (User Story 1 - P1)

**Goal**: Extraer señales a fecha de corte sin mirar el futuro, entrenar el modelo calibrado y clasificar bandas con histéresis.  
**Independent Test**: Ejecutar `python -m src.cli.train_model` y verificar que el reporte en `reports/model_evaluation.json` produce `ROC-AUC >= 0.75` y `Brier Score < 0.15` sin data leakage.

- [ ] T005 [P] [US1] Implementar el cálculo estricto de señales de historial y deterioro a fecha de corte en `src/analytics/signals.py` (RF-03)
- [ ] T006 [US1] Implementar el modelo de Regresión Logística calibrado con CalibratedClassifierCV y reporte de métricas en `src/analytics/model.py`, `src/analytics/metrics.py` y `src/cli/train_model.py` (RF-04)
- [ ] T007 [US1] Implementar la clasificación en bandas de riesgo (Baja, Moderada, Alta, Crítica) con margen de histéresis (0.05 / 2 ciclos) en `src/policy/engine.py` (RF-05)
- [ ] T008 [US1] Implementar la verificación y tipificación de calidad de evidencia (Suficiente, Insuficiente, Inconsistente) en `src/policy/engine.py` (RF-06)
- [ ] T009 [P] [US1] Implementar pruebas unitarias de aislamiento temporal de señales para verificar que no se use información posterior a la fecha de corte en `tests/unit/test_signals.py`

---

### Phase 3: Política, Acciones y Límites en Herramienta (User Story 1 - P1)

**Goal**: Garantizar que los límites de seguridad y buen trato residan en el código de las herramientas de acción y capturar correos en SMTP local.  
**Independent Test**: Intentar programar avisos fuera de ventana o a clientes que ya pagaron y verificar que `ScheduleNoticeTool` arroja rechazo determinista sin enviar correo.

- [ ] T010 [US1] Implementar cargador y validador Pydantic de la política declarativa en `src/policy/config.py` (RF-08)
- [ ] T011 [US1] Implementar la herramienta `ScheduleNoticeTool` con validaciones duras de ventana, cuota, separación y estado de pago en `src/tools/schedule_tool.py` (RF-11)
- [ ] T012 [P] [US1] Implementar el redactor por plantillas Jinja2 y el validador ético/léxico `ToneGuardValidator` en `src/agent/drafter.py`, `src/agent/validator.py` y `src/templates/` (RF-10)
- [ ] T013 [P] [US1] Implementar el servidor SMTP de prueba embebido en hilo local y el cliente de despacho configurable en `src/mail/server.py` y `src/mail/client.py` (RF-15)
- [ ] T014 [P] [US1] Implementar pruebas exhaustivas de límites en herramientas (fuera de ventana, exceso de avisos, separación mínima, pago registrado y pago en proceso) en `tests/unit/test_tool_enforcement.py`

**Checkpoint Sprint 1**: El núcleo analítico y las herramientas de despacho seguro están completamente implementados y probados con pruebas unitarias.

---

## Sprint 2: Orquestador del Agente, Ciclo Diario y Revisión Humana

### Phase 4: Agente y Ciclo Diario (User Story 1 & User Story 3)

**Goal**: Orquestar la evaluación diaria de cartera, investigar inconsistencias y ejecutar el despacho exclusivo de avisos aprobados.  
**Independent Test**: Ejecutar un ciclo diario simulado a las 10:00 con corte de revisión a las 09:00 y verificar que los avisos no aprobados se retienen.

- [ ] T015 [US1] Implementar suite de contratos de herramientas del agente (señales, riesgo, pagos, validación, programación y registro) en `src/tools/`
- [ ] T016 [US1] Implementar el módulo investigador de inconsistencias de pago con modo dual (reglas deterministas + LLM opcional) en `src/agent/investigator.py` (RF-09)
- [ ] T017 [US1] Implementar la política de contingencia para clientes con historial corto (< 3 períodos) con aviso neutro estándar en `src/agent/orchestrator.py` (RF-07)
- [ ] T018 [US1] Implementar el orquestador del ciclo diario con cierre de revisión a las 09:00 y envío restringido a las 10:00 en `src/agent/orchestrator.py` y `src/cli/run_cycle.py` (RF-12)

---

### Phase 5: Revisión Humana y Auditoría (User Story 2 & User Story 3)

**Goal**: Proveer cola de casos dudosos ordenada por urgencia, reevaluación reactiva tras corrección del analista y registro inmutable de auditoría.  
**Independent Test**: Ingresar un pago corregido para un cliente en la cola de revisión y verificar que el agente reevalúa inmediatamente su estado y cancela el aviso pendiente.

- [ ] T019 [US2] Implementar la cola de revisión de casos derivados con ordenamiento prioritario por días al vencimiento y riesgo en `src/domain/evaluation.py` y `src/data/sqlite_repo.py` (RF-13)
- [ ] T020 [US2] Implementar la herramienta de corrección de datos de pago con disparo de reevaluación automática en `src/tools/reevaluate_tool.py` (RF-13)
- [ ] T021 [US2] Implementar el registro inmutable de auditoría para decisiones, reglas aplicadas y correcciones manuales en `src/domain/audit.py` y `src/data/sqlite_repo.py` (RF-14)
- [ ] T022 [P] [US2] Implementar pruebas del caso derivado sin revisar a la hora límite (09:00/10:00) verificando retención forzosa en `tests/integration/test_daily_cycle.py`

**Checkpoint Sprint 2**: El agente orquestador opera de extremo a extremo, maneja excepciones, alimenta la cola de revisión y audita cada decisión.

---

## Sprint 3: Adaptación, Comparación, Interfaz Web y Ensayo E2E

### Phase 6: Adaptación y Comparación de Desempeño (User Story 4 - P4)

**Goal**: Optimizar el momento del aviso con exploración acotada del 10% y comparar la efectividad del agente frente a una campaña tradicional.  
**Independent Test**: Correr una simulación de 30 días y contrastar los avisos emitidos y la tasa de pago oportuno frente al benchmark fijo.

- [ ] T023 [US4] Implementar el algoritmo Multi-Armed Bandit $\epsilon$-greedy ($\epsilon=0.10$) acotado a la ventana autorizada en `src/policy/bandit.py` (RF-16)
- [ ] T024 [P] [US4] Implementar el motor de campaña fija tradicional por segmento para contraste analítico en `src/simulation/benchmark.py` (RF-17)
- [ ] T025 [US4] Implementar el cálculo y reporte de métricas comparativas (volumen de avisos, pagos anticipados, días promedio) en `src/simulation/benchmark.py` (RF-17)
- [ ] T026 [US4] Implementar el motor de reproducción histórica paso a paso día por día en `src/simulation/engine.py` (RF-19)

---

### Phase 7: Interfaz Visual, Ensayo y Entrega Final

**Goal**: Presentar la experiencia completa en Streamlit, ensayar la demo local con un solo comando y documentar supuestos.  
**Independent Test**: Ejecutar `./demo.sh`, interactuar con todas las pestañas de la UI y validar que ningún correo sale al exterior.

- [ ] T027 [US1] Implementar vista de cartera interactiva y expediente detallado por cliente en `src/ui/app.py` y `src/ui/views/portfolio.py` (RF-18)
- [ ] T028 [US2] Implementar panel visual de la cola de revisión con formulario de corrección y bandeja de correos SMTP capturados en `src/ui/views/review_queue.py` y `src/ui/views/captured_inbox.py` (RF-18)
- [ ] T029 [US4] Implementar visualización gráfica de comparación de estrategias (agente vs. campaña fija) en `src/ui/views/benchmark_view.py` (RF-18)
- [ ] T030 Ensayo completo del guion de demo reproducible con un solo comando en `demo.sh`
- [ ] T031 Documentar en el `README.md` los supuestos declarados, advertencia de datos simulados y guía de evaluación para jurados

---

## Dependencies & Execution Order

### Dependencias entre Fases y Sprints
```
[Phase 1: Setup & Data] (Sprint 1)
        │
        ▼
[Phase 2: Riesgo & Señales] (Sprint 1)
        │
        ▼
[Phase 3: Política & Herramientas] (Sprint 1) ──► Checkpoint MVP Core
        │
        ▼
[Phase 4: Agente & Ciclo Diario] (Sprint 2)
        │
        ▼
[Phase 5: Revisión & Auditoría] (Sprint 2)   ──► Checkpoint Flujo Operativo
        │
        ▼
[Phase 6: Adaptación & Benchmark] (Sprint 3)
        │
        ▼
[Phase 7: Interfaz & Ensayo Final] (Sprint 3) ──► Demo Lista Hackathon
```

---

## Oportunidades de Ejecución en Paralelo

### Sprint 1:
- `T004` (Pruebas del generador) puede ejecutarse en paralelo una vez generado `T003`.
- `T005` (Señales) y `T010` (Configuración de política) operan en módulos desacoplados.
- `T012` (Jinja2 Drafter + ToneGuard) y `T013` (Servidor SMTP aiosmtpd) pueden desarrollarse simultáneamente.
- `T014` (Pruebas de límites de herramientas) puede ejecutarse en paralelo con la estabilización de `T011`.

### Sprint 2:
- `T016` (Investigador) y `T017` (Política clientes nuevos) pueden abordarse en paralelo antes de la integración final en `T018`.
- `T021` (Auditoría) y `T022` (Pruebas de retención de no revisados) pueden desarrollarse de forma concurrente con `T019`.

### Sprint 3:
- `T024` (Benchmark campaña fija) y `T023` (Bandit de adaptación) son independientes.
- Las vistas de la interfaz (`T027`, `T028`, `T029`) pueden desarrollarse en componentes desacoplados dentro de `src/ui/views/`.

---

## Estrategia de Implementación y Criterios de Aceptación por Sprint

1. **Sprint 1 (MVP Core)**:
   - *Criterio de éxito*: `pytest tests/unit/` corre al 100%. El generador crea `portfolio_demo.db`, el modelo calcula probabilidades calibradas y `ScheduleNoticeTool` bloquea deterministamente cualquier intento indebido de contacto.
2. **Sprint 2 (Operación y Supervisión)**:
   - *Criterio de éxito*: Se ejecuta `python -m src.cli.run_cycle`. Los clientes dudosos van a la cola de revisión, los aprobados se despachan al socket SMTP local y las correcciones del analista provocan reevaluación inmediata.
3. **Sprint 3 (Demostración y Hackathon Ready)**:
   - *Criterio de éxito*: Ejecutar `./demo.sh`. Se abre el dashboard en Streamlit mostrando la cartera viva, la cola de revisión interactiva, la bandeja de correos capturados y el gráfico de efectividad frente a la campaña tradicional.
