# Plan de Trabajo y Reparto de Responsabilidades (Equipo de 5)
## VERAIA - Agente de Cobranza Temprana (Hackathon Vertical Slice)

Este documento detalla la distribución operativa, dependencias, contratos de entrada/salida y lineamientos de integración para que los **5 integrantes del equipo** puedan desarrollar de manera paralela e independiente sin bloquearse.

---

## 0. Prerrequisito Base Compartido (Contratos Comunes)

Para que ningún integrante se bloquee, todos los módulos consumen las entidades base definidas en:
- **Archivo central**: `src/domain/entities.py`
- **Especificación de referencia**: [`sdd/specs/001-early-collection-agent/data-model.md`](sdd/specs/001-early-collection-agent/data-model.md) y [`sdd/specs/001-early-collection-agent/contracts/`](sdd/specs/001-early-collection-agent/contracts/)

### Nombres y Tipos Inmutables que Todo el Equipo Debe Respetar:
1. **Identificadores**: `customer_id` (`str`), `account_id` (`str`), `record_id` (`str`), `evaluation_id` (`str`), `notice_id` (`str`).
2. **Fechas**: 
   - `due_date` (`date`): Fecha de vencimiento pactada.
   - `cutoff_date` (`date`): Fecha de corte en que se evalúa la cartera.
   - `actual_payment_date` (`date | None`): Fecha efectiva del pago (para medir mora real).
   - `recorded_payment_date` (`date | None`): Fecha de registro contable.
3. **Bandas de Riesgo**: Exactamente `"BAJA"`, `"MODERADA"`, `"ALTA"`, `"CRITICA"`.
4. **Tonos de Aviso**: Exactamente `"NEUTRAL"`, `"PREVENTIVE"`, `"FIRM"`.
5. **Calidad de Evidencia**: Exactamente `"SUFFICIENT"`, `"INSUFFICIENT"`, `"INCONSISTENT"`.
6. **Estados del Aviso**: `"SCHEDULED"`, `"APPROVED"`, `"REJECTED"`, `"DISPATCHED"`, `"CAPTURED"`.

---

## 1. Distribución por Integrante

```
========================================================================================
[Dev 1: Persistencia]  ──► data/portfolio_demo.db & SQLiteRepository
[Dev 2: Data Science]  ──► Señales a fecha de corte & Modelo Calibrado (AUC/Brier)
[Dev 3: Gobernanza]    ──► Motor de Bandas/Histéresis & ScheduleNoticeTool (Límites)
[Dev 4: Comunicaciones]──► Servidor SMTP aiosmtpd & Validador ToneGuard + Jinja2
[Dev 5: UI & Orquest.] ──► Interfaz Streamlit, Cola de Revisión & Simulación MAB
========================================================================================
```

---

### Integrante 1: Persistencia, Repositorio y Generador Dummy
- **Rol**: Ingeniero de Datos / Backend
- **Rama Git**: `feature/data-repository`
- **Tareas asignadas**: `T002`, `T003`, `T004`, apoyo en `T021` (Auditoría)

#### Carpetas y Archivos a su Cargo:
```text
src/data/
├── repository.py        # Protocolo abstracto PortfolioRepository
├── sqlite_repo.py       # Implementación SQLite local con transacciones
└── generator.py         # Generador de clientes con semilla fija (seed=42)
src/cli/
└── generate_data.py     # CLI: python -m src.cli.generate_data --seed 42
tests/
├── unit/test_generator.py
└── integration/test_sqlite_repository.py
```

#### Responsabilidades Específicas:
1. Implementar el generador con semilla fija (`seed=42`) reproduciendo perfiles estables, deterioro incipiente (uso 95% y pagos mínimos sostenidos), moras crónicas e inconsistencias de pago demorado.
2. Implementar `SQLitePortfolioRepository` asegurando que las consultas de historial filtren estrictamente por `cutoff_date` (Principio IV de la Constitución: Prohibido mirar al futuro).
3. Implementar métodos para consultar pagos en tránsito y actualizar registros corregidos desde la cola de revisión.

#### ¿Cómo trabajar sin bloquearse?:
- Trabaja directamente con la especificación de [`sdd/specs/001-early-collection-agent/contracts/repository_contract.md`](sdd/specs/001-early-collection-agent/contracts/repository_contract.md).
- Su entregable es el archivo de base de datos listo: `data/portfolio_demo.db`.

---

### Integrante 2: Machine Learning, Señales y Evaluación de Riesgo
- **Rol**: Data Scientist / ML Engineer
- **Rama Git**: `feature/risk-model`
- **Tareas asignadas**: `T005`, `T006`, `T009`

#### Carpetas y Archivos a su Cargo:
```text
src/analytics/
├── signals.py           # Extracción y cálculo de señales a fecha de corte
├── model.py             # LogisticRegression envuelta en CalibratedClassifierCV
└── metrics.py           # Reporte de discriminación (ROC-AUC) y calibración (Brier Score)
src/cli/
└── train_model.py       # CLI: python -m src.cli.train_model --db ...
tests/
├── unit/test_signals.py # Prueba crítica: no-lookahead (aislamiento temporal)
└── unit/test_model.py   # Prueba de calibración y ROC-AUC >= 0.75
```

#### Responsabilidades Específicas:
1. Calcular a `cutoff_date`: ratio de uso de línea, conteo de pagos mínimos sostenidos ($\ge 3$), caída porcentual en el monto pagado respecto a lo facturado y métricas de atraso histórico.
2. Entrenar y calibrar el modelo probabilístico con `scikit-learn` utilizando `LogisticRegression(solver='lbfgs')` y `CalibratedClassifierCV(method='sigmoid', cv=3)`.
3. Exportar el reporte en `reports/model_evaluation.json` asegurando reproducibilidad determinista (`random_state=42`).

#### ¿Cómo trabajar sin bloquearse?:
- No necesita esperar la base de datos de Dev 1: puede crear un fixture en `tests/conftest.py` con un DataFrame sintético en memoria para probar las funciones de cálculo de señales y ajuste del modelo.

---

### Integrante 3: Políticas de Contacto y Límites en Herramientas
- **Rol**: Ingeniero de Seguridad y Reglas de Negocio
- **Rama Git**: `feature/policy-tools`
- **Tareas asignadas**: `T007`, `T008`, `T010`, `T011`, `T014`

#### Carpetas y Archivos a su Cargo:
```text
src/policy/
├── config.py            # Cargador y validador de config/politica.yaml
└── engine.py            # Reglas de clasificación, histéresis (0.05 / 2 ciclos) y evidencia
src/tools/
└── schedule_tool.py     # ScheduleNoticeTool con validaciones deterministas duras
tests/
├── unit/test_policy_engine.py
└── unit/test_tool_enforcement.py
```

#### Responsabilidades Específicas:
1. Implementar la carga y tipado estricto de `config/politica.yaml` con Pydantic.
2. Implementar las reglas de histéresis: el cambio de banda exige superar el umbral por $0.05$ o sostenerse $2$ ciclos consecutivos en la nueva banda.
3. Implementar la herramienta `ScheduleNoticeTool` cumpliendo el **Principio Constitucional II**:
   - Bloquear deterministamente cualquier intento de enviar fuera de la ventana.
   - Bloquear si se supera el máximo de avisos por ciclo para la banda.
   - Bloquear si no se respeta la separación mínima de días.
   - Bloquear de inmediato si el cliente ya pagó o tiene un pago en proceso.

#### ¿Cómo trabajar sin bloquearse?:
- Trabaja con [`sdd/specs/001-early-collection-agent/contracts/tools_contract.md`](sdd/specs/001-early-collection-agent/contracts/tools_contract.md) y [`config/politica.yaml`](config/politica.yaml).
- Valida su código con tests unitarios simulando llamadas a la herramienta con diccionarios y objetos mock.

---

### Integrante 4: Mensajería, ToneGuard y Servidor SMTP Local
- **Rol**: Ingeniero de Comunicaciones e IA
- **Rama Git**: `feature/mail-toneguard`
- **Tareas asignadas**: `T012`, `T013`, `T016`

#### Carpetas y Archivos a su Cargo:
```text
src/agent/
├── drafter.py           # MessageDrafter dual (Jinja2 local + LLM opcional)
├── validator.py         # ToneGuardValidator (verificación ética y léxica)
└── investigator.py      # InconsistencyInvestigator (análisis de pagos en trámite)
src/templates/
├── neutral.j2           # Plantilla tono neutro
├── preventive.j2        # Plantilla tono preventivo
└── firm.j2              # Plantilla tono firme
src/mail/
├── server.py            # Servidor aiosmtpd embebido en hilo local daemon
└── client.py            # Cliente de envío smtplib a localhost:1025
tests/
├── unit/test_tone_validator.py
└── integration/test_smtp_capture.py
```

#### Responsabilidades Específicas:
1. Implementar `ToneGuardValidator`: vetar estrictamente menciones a bandas internas (`"Banda Alta"`, `"Score"`), adjetivos despectivos (`"moroso"`) y amenazas. Si falla, aplicar fallback a plantilla neutra estándar.
2. Implementar `aiosmtpd` escuchando en `127.0.0.1:1025` y guardando los correos recibidos en memoria/SQLite, garantizando el **Principio XII** (cero correos a destinatarios reales).
3. Implementar la investigación de pagos demorados: contrastar montos y fechas para formular la hipótesis de pago diferido antes de derivar a revisión.

#### ¿Cómo trabajar sin bloquearse?:
- Es el módulo más desacoplado. Solo requiere Python puro, `jinja2`, `aiosmtpd` y expresiones regulares / lógica léxica. Puede enviar y recibir correos de prueba en local inmediatamente.

---

### Integrante 5: Interfaz Web Streamlit, Simulación y Orquestación
- **Rol**: Full-Stack / Demo Lead
- **Rama Git**: `feature/ui-simulation`
- **Tareas asignadas**: `T018`, `T020`, `T023`, `T024`, `T025`, `T026`, `T027`, `T028`, `T029`, `T030`, `T031`

#### Carpetas y Archivos a su Cargo:
```text
src/ui/
├── app.py               # Punto de entrada Streamlit (st.navigation o tabs)
└── views/
    ├── portfolio.py     # Vista de cartera y expediente de cliente
    ├── review_queue.py  # Cola de revisión interactiva con formulario de corrección
    ├── captured_inbox.py# Visualizador de correos capturados en SMTP
    └── benchmark_view.py# Gráficas de efectividad (Agente vs Campaña Tradicional)
src/policy/
└── bandit.py            # Multi-Armed Bandit epsilon-greedy (10% exploración)
src/simulation/
├── engine.py            # Motor de reproducción histórica día por día
└── benchmark.py         # Motor de campaña fija por segmento
demo.sh                  # Script de ejecución en un solo comando
README.md                # Documentación de supuestos y guía de evaluación
```

#### Responsabilidades Específicas:
1. Diseñar el dashboard en Streamlit que integre: control de avance diario de simulación, tabla de cartera con alertas de riesgo, expediente del cliente, cola de revisión humana y visor de correos capturados.
2. Implementar el benchmark de campaña fija tradicional para comparar: volumen de avisos enviados, pagos anticipados logrados y días promedio de anticipación.
3. Crear el script `demo.sh` para levantar la solución con un único comando.

#### ¿Cómo trabajar sin bloquearse?:
- Puede iniciar maquetando los componentes de Streamlit con datos mock (DataFrames estáticos de prueba). Una vez que Dev 1 y Dev 3 entreguen sus módulos, conecta las vistas a las funciones reales.

---

## 2. Matriz de Dependencias y Puntos de Integración

```
DÍA 1 (Horas 1 a 4) ─────────────────────────────────────────────────────────
  Base común: src/domain/entities.py (¡Desbloqueo inmediato!)
  ├─ Dev 1 monta generador de datos y SQLite repo
  ├─ Dev 2 monta extracción de señales y pipeline scikit-learn
  ├─ Dev 3 monta reglas de política y validaciones de ScheduleNoticeTool
  ├─ Dev 4 levanta el socket SMTP local y ToneGuardValidator
  └─ Dev 5 maqueta la navegación y vistas en Streamlit con datos mock

DÍA 1 (Horas 5 a 8) ─────────────────────────────────────────────────────────
  Integración intermedia:
  ├─ Dev 2 corre modelo sobre datos generados por Dev 1.
  ├─ Dev 3 y Dev 4 integran ScheduleNoticeTool con el cliente SMTP local.
  └─ Dev 5 conecta la tabla de Streamlit al SQLiteRepository de Dev 1.

DÍA 2 (Horas 9 a 12) ────────────────────────────────────────────────────────
  Cierre de ciclo y ensayo final:
  ├─ Orquestador completo del ciclo diario (corte 09:00 / despacho 10:00).
  ├─ Cola de revisión interactiva con reevaluación reactiva.
  ├─ Simulación temporal histórica paso a paso.
  └─ Ensayo general con demo.sh y verificación de cero errores en pytest.
```

---

## 3. Guía de Trabajo con Git para Evitar Conflictos

1. **Crear ramas a partir de `main`**:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/<mi-modulo>
   ```
2. **Commits frecuentes y descriptivos**:
   - `feat(data): implement sqlite repository for cutoff queries`
   - `feat(risk): implement logistic regression with calibrated cv`
   - `feat(policy): implement hard limits in schedule notice tool`
   - `feat(mail): setup embedded aiosmtpd server`
   - `feat(ui): create portfolio view in streamlit`
3. **No modificar archivos fuera de tu módulo asignado** sin coordinar con el responsable del archivo.
4. **Al terminar tu módulo**:
   - Ejecutar pruebas locales: `pytest tests/`
   - Crear Pull Request hacia `main`.
