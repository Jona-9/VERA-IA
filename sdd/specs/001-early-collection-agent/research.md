# Technical Research & Architecture Decisions: Agente de Cobranza Temprana

**Feature**: `001-early-collection-agent`  
**Date**: 2026-10-17  
**Status**: Approved / Consolidated  

## 1. Contexto y Objetivos Técnicos

El objetivo de esta investigación técnica es consolidar las decisiones de diseño para el vertical slice ejecutable de un agente de cobranza temprana desarrollado en Python 3.11+. La solución debe ser 100% reproducible en un entorno local para la hackathon, cumpliendo con los 12 principios constitucionales de gobernanza (aislamiento de datos personales, determinismo de políticas, límites en herramientas y captura local SMTP).

---

## 2. Decisiones de Arquitectura y Tecnologías

### 2.1. Modelo Analítico de Probabilidad de Atraso (RF-04)

- **Decisión**: Utilizar `scikit-learn` implementando `LogisticRegression(penalty='l2', solver='lbfgs')` envuelto en `CalibratedClassifierCV(method='sigmoid', cv=3)`.
- **Razón**: 
  - La Regresión Logística provee coeficientes interpretables y auditables para cada señal de deterioro (uso de línea, pagos mínimos consecutivos, caída de monto pagado).
  - La calibración mediante el método sigmoide (Platt scaling) o isotónico garantiza que las probabilidades predichas reflejen la frecuencia empírica real de atraso, condición crítica para una asignación justa de bandas de riesgo.
  - La inferencia es instantánea (< 1 ms por cliente) y converge de forma determinista con semilla fija (`random_state=42`), sin requerir aceleradores de hardware (GPU).
- **Métricas de Evaluación**: Discriminación mediante Área Bajo la Curva ROC (ROC-AUC) y calibración mediante Brier Score y Curva de Calibración (Reliability Diagram).
- **Alternativas consideradas**:
  - *LightGBM / XGBoost*: Rechazado para el vertical slice por mayor complejidad de auditoría de hiperparámetros y riesgo de sobreajuste en muestras sintéticas pequeñas.
  - *Scorecard heurístico*: Rechazado porque no produce probabilidades continuas directamente calibradas.

### 2.2. Capa de Persistencia y Repositorio Desacoplado (RF-02)

- **Decisión**: Implementar el patrón repositorio mediante una interfaz abstracta `PortfolioRepository` (`typing.Protocol` o `abc.ABC`), implementada en la demo con `SQLitePortfolioRepository` usando `sqlite3` de la biblioteca estándar de Python.
- **Razón**: 
  - Permite entregar un entorno local autocontenido en un archivo `.db` sin instalación de servidores de bases de datos.
  - Cumple estrictamente con el principio de desacoplamiento de interfaces: la lógica de cálculo de señales y el orquestador dependen exclusivamente del contrato abstracto, permitiendo incorporar un `PostgreSQLRepository` futuro sin modificar una sola línea de lógica de negocio.
  - Soporta consultas temporales indexadas por `cutoff_date` y operaciones de escritura transaccionales para la actualización de casos en cola de revisión.
- **Alternativas consideradas**:
  - *ORM pesado (SQLAlchemy / Tortoise)*: Rechazado para la demo por sobrecarga de abstracción en un vertical slice enfocado en velocidad de ejecución.
  - *Dataframes en memoria (Pickle / Parquet)*: Rechazado porque no permite simular consultas transaccionales ni modificaciones reactivas de registros por el analista.

### 2.3. Límites en Herramientas (Tool-Enforced Boundaries) (RF-11, Principio II)

- **Decisión**: Implementar las herramientas de acción (ej. `ScheduleNoticeTool`, `DispatchEmailTool`) como clases autónomas con validaciones duras codificadas en Python y contratos Pydantic v2.
- **Razón**: 
  - La constitución estipula taxativamente que *los límites viven en las herramientas, no en el prompt del agente*.
  - La herramienta evalúa de manera determinista: (1) si la fecha programada está dentro de la ventana de la banda del cliente, (2) si se superó la cuota máxima acumulada de avisos, (3) si se respeta el intervalo mínimo de días desde el último aviso, y (4) si la obligación ya fue pagada o tiene un pago en proceso.
  - Si alguna validación falla, la herramienta rechaza la operación arrojando un error estructurado (`PolicyRejectionError`), impidiendo físicamente cualquier envío sin importar la directiva del agente.
- **Alternativas consideradas**:
  - *Validación en el prompt del sistema*: Rechazado formalmente por violar el Principio II de la constitución.

### 2.4. Orquestación del Agente y Modo Dual Determinista/LLM (RF-09, RF-10, Principio III y XI)

- **Decisión**: Diseñar un orquestador híbrido (`CollectionAgentOrchestrator`) con arquitectura en dos capas:
  1. *Capa de Control Determinista*: Aplica las reglas de negocio, histéresis de bandas (0.05 de margen o 2 ciclos), clasificación de evidencia y verificación de pagos.
  2. *Capa de Asistencia Adaptativa (Dual-Mode)*: Para la investigación de hipótesis (RF-09) y redacción de textos (RF-10), se define una interfaz `MessageDrafter` e `InconsistencyInvestigator`.
     - Si hay credenciales de LLM configuradas (OpenAI, Anthropic o proveedor local compatible con OpenAI API como Ollama), invoca el modelo para enriquecer el análisis.
     - Si no hay credenciales (modo offline/demo por defecto), se activan automáticamente los adaptadores deterministas (`DeterministicDrafter` con Jinja2 y `DeterministicInvestigator`), asegurando que la demo funcione 100% desconectada sin fricción.
- **Razón**: 
  - Preserva la privacidad: jamás se transmiten PII (nombres, documentos o números de cuenta) al LLM. El LLM solo recibe un contexto anonimizado con el tono requerido y variables estructurales.
  - Asegura robustez operativa en el hackathon ante cortes de red o falta de saldo en APIs de pago.
  - Las salidas del redactor siempre pasan por un validador léxico y de tono (`ToneGuardValidator`); si falla, se utiliza la plantilla preaprobada de contingencia.

### 2.5. Captura SMTP Local Embebida (RF-15, Principio XII)

- **Decisión**: Utilizar la biblioteca `aiosmtpd` en un hilo daemon secundario de Python que escuche en `127.0.0.1:1025` y persista los correos recibidos en una tabla SQLite (`captured_emails`).
- **Razón**: 
  - Cumple el Principio XII: ningún correo sale a destinatarios reales en la demo.
  - Elimina la necesidad de dependencias externas como Docker, Mailpit o MailHog instalados en el sistema operativo del evaluador.
  - Los correos capturados están inmediatamente disponibles para consulta en tiempo real desde la base de datos local y visualizables en la UI de Streamlit.
- **Alternativas consideradas**:
  - *Mock directo a nivel de función (sin socket)*: Rechazado porque no prueba la integración real del cliente SMTP estándar (`smtplib`).
  - *Mailpit con Docker*: Rechazado porque exige que el usuario tenga Docker instalado y activo en su máquina.

### 2.6. Interfaz de Usuario y Tablero de Control (RF-18)

- **Decisión**: Desarrollar la interfaz web interactiva en **Streamlit**.
- **Razón**: 
  - Permite crear una experiencia visual completa en Python puro: control de avance diario de la simulación histórica (día por día), tabla de cartera con bandas y alertas, vista de expediente del cliente, cola de revisión con formulario de corrección de pagos, visualizador de correos capturados y gráficos interactivos (comparación de avisos y anticipación de pagos con `plotly` o `altair`).
  - Integración directa con el estado de la aplicación (`st.session_state`) y el repositorio SQLite local.
- **Alternativas consideradas**:
  - *FastAPI + React/Vite*: Rechazado para el alcance del hackathon por requerir un toolchain dual (Node.js + Python) y mayor complejidad de despliegue local.

### 2.7. Optimización Adaptativa Acotada del Momento de Contacto (RF-16)

- **Decisión**: Implementar un algoritmo Multi-Armed Bandit $\epsilon$-greedy acotado ($\epsilon = 0.10$).
- **Razón**: 
  - Los "brazos" son los días específicos dentro de la ventana autorizada de la banda (ej. en ventana D-5 a D-1, los días posibles son 5, 4, 3, 2 o 1 días antes del vencimiento).
  - La recompensa se define como el pago efectivo recibido antes de la fecha límite tras enviar el aviso.
  - Con 90% de probabilidad elige el día con mayor tasa histórica de pago; con 10% explora aleatoriamente otro día *estrictamente dentro de la ventana*.
  - Por construcción algorítmica, ningún brazo fuera de la ventana es generado ni seleccionado.

---

## 3. Resumen de Decisiones Técnicas

| Componente | Tecnología Seleccionada | Justificación Principal |
|------------|-------------------------|--------------------------|
| **Lenguaje** | Python 3.11+ | Compatibilidad estándar con tipado estricto y ecosistema analítico. |
| **Modelado de Riesgo** | `scikit-learn` LogisticRegression + CalibratedClassifierCV | Explicabilidad de coeficientes, calibración de probabilidad y reproducibilidad. |
| **Persistencia** | `sqlite3` + Repository Pattern | Cero configuración, portable a PostgreSQL en producción. |
| **Validación y Esquemas** | Pydantic v2 + PyYAML | Tipado robusto para políticas declarativas y contratos de herramientas. |
| **Redacción de Mensajes** | Jinja2 + LLM Dual-Mode (Fallback determinista) | Privacidad estricta (sin PII enviada a LLM) y ejecución 100% offline. |
| **Captura SMTP** | `aiosmtpd` en hilo local | Aislamiento seguro de pruebas sin Docker. |
| **Interfaz Web** | Streamlit | Dashboard interactivo integral en un solo lenguaje. |
| **Pruebas** | pytest | Pruebas unitarias deterministas y de contrato de herramientas. |
