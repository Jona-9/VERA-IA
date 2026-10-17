# Feature Specification: Agente de Cobranza Temprana (Vertical Slice Hackathon)

**Feature Branch**: `001-early-collection-agent`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "Herramienta open source que un agente usa para detectar señales tempranas de deterioro en clientes con obligaciones próximas o vencidas, estimar su probabilidad de atraso y decidir cuándo y con qué tono enviar un aviso por correo. La demo usa datos dummy y se ejecuta localmente."

## Clarifications

### Session 2026-10-17
- Q: ¿Cuáles deben ser los valores por defecto para las ventanas de envío, límites máximos de avisos y separación mínima entre contactos en cada banda de riesgo? (FR-008) → A: Esquema escalonado: **Baja** (0 preventivos; post D+2 a D+5, máx 1, tono neutro), **Moderada** (preventivo D-3 a D-1, máx 1; post D+1 a D+5, máx 1, sep mín 2 días), **Alta** (preventivo D-5 a D-1, máx 2, sep mín 2 días; post D+1 a D+7, máx 2, tono firme, sep 2 días), **Crítica** (preventivo D-7 a D-1, máx 2, sep mín 2 días; post D+1 a D+10, máx 3, tono firme, sep 2 días).
- Q: ¿Qué enfoque algorítmico debe emplearse para el modelo de estimación y calibración de probabilidad de atraso en la cuota próxima? (FR-004) → A: Regresión Logística calibrada con coeficientes explicables por señal y calibración de probabilidades (Isotónica / Platt), optimizada para auditabilidad y reproducibilidad determinista con semilla fija.
- Q: ¿Cómo deben implementarse la captura de correos SMTP y la interfaz web para asegurar una ejecución local inmediata y sin fricciones durante la demo? (FR-015, FR-018) → A: Python nativo puro: servidor SMTP de captura embebido en proceso de fondo local (persistiendo correos en SQLite/memoria sin requerir Docker) e interfaz interactiva en Streamlit integrada con control de simulación, cola de revisión y visualizador de correos capturados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detección Temprana, Evaluación y Aviso Preventivo Protegido (Priority: P1)

Como cliente con obligaciones financieras próximas a vencer, quiero recibir recordatorios respetuosos, oportunos y acordes a mi situación particular, sin sufrir reiteraciones excesivas ni contactos fuera de horario, para mantener mis cuentas al día antes de incurrir en costos de cobranza.

**Why this priority**: Constituye el núcleo del vertical slice de valor (MVP): evaluar señales tempranas antes del atraso, estimar el riesgo, decidir la acción dentro de la política y despachar el aviso bajo salvaguardas inviolables en la herramienta.

**Independent Test**: Puede probarse de principio a fin ejecutando la evaluación sobre clientes simulados con deterioro incipiente y verificando que el aviso generado se redacta con tono preventivo respetuoso, respeta la ventana horaria y queda capturado en el servidor de prueba sin violar los topes máximos de contacto.

**Acceptance Scenarios**:

1. **Given** un cliente con historial puntual que en los últimos 3 períodos incrementa el uso de su línea al 95% y abona únicamente el pago mínimo, **When** el agente ejecuta la evaluación diaria a la fecha de corte previa al vencimiento, **Then** el cliente es clasificado en banda Alta antes de su primer atraso y se programa un aviso respetuoso dentro de la ventana de riesgo Alto.
2. **Given** un cliente en banda Baja sin atrasos previos ni señales de deterioro, **When** se evalúa su cartera en la fecha de corte, **Then** el agente no programa ningún aviso de cobro.
3. **Given** un cliente que ya alcanzó el límite máximo de 2 avisos permitidos para su banda, **When** el agente intenta despachar un tercer aviso, **Then** la herramienta de envío rechaza de forma determinista la acción y no se emite comunicación.
4. **Given** cualquier aviso aprobado para despacho durante la demo, **When** se ejecuta el envío, **Then** el correo es capturado íntegramente en el servidor SMTP de prueba local sin transmitirse a ningún destinatario real.

---

### User Story 2 - Cola de Revisión Humana y Corrección Reactiva (Priority: P2)

Como analista de cobranza, quiero visualizar los casos con datos dudosos o inconsistentes ordenados por urgencia y riesgo, y poder ingresar correcciones operativas (como pagos no reflejados) para que el agente reevalúe al cliente de forma inmediata sin necesidad de gestión manual reiterada.

**Why this priority**: Asegura el principio de "ante la duda, el agente no actúa sin supervisión" y permite resolver discrepancias operativas reales (demoras bancarias, reclamos) integrando al analista en el ciclo de decisión.

**Independent Test**: Puede probarse inyectando un caso con pago no reflejado en proceso, verificando que el agente se abstiene de contactar y lo deriva a la cola de revisión; al ingresar el registro de pago corregido desde la interfaz, el agente reevalúa automáticamente al cliente y archiva el aviso pendiente.

**Acceptance Scenarios**:

1. **Given** un cliente con obligación vencida que registra un pago en proceso de acreditación bancaria, **When** el agente analiza el caso, **Then** suspende el envío del aviso, clasifica la evidencia como inconsistente, formula la hipótesis de pago diferido y deriva el expediente a la cola de revisión.
2. **Given** un caso derivado en la cola que no es revisado por el analista antes de la hora límite de cierre (09:00), **When** se ejecuta la ventana de despacho de las 10:00, **Then** el sistema no envía ningún correo y mantiene el caso retenido en la cola.
3. **Given** un expediente en la cola de revisión con inconsistencia de registro, **When** el analista actualiza la fecha real de pago, **Then** el agente ejecuta una reevaluación inmediata con los datos corregidos y actualiza la banda y decisión del cliente.

---

### User Story 3 - Supervisión y Gobernanza de Políticas (Priority: P3)

Como supervisor de cobranza, quiero revisar, aprobar o rechazar de manera formal cualquier modificación a las políticas, ventanas o umbrales de contacto propuesta por el agente, para garantizar que la entidad mantenga en todo momento el control humano y regulatorio sobre las reglas de trato al cliente.

**Why this priority**: Garantiza el cumplimiento del principio constitucional IX ("el agente propone, el supervisor aprueba"), evitando cualquier alteración autónoma o deriva no controlada de políticas.

**Independent Test**: Puede probarse generando una sugerencia de ajuste de umbral por parte del agente analítico y comprobando que ninguna regla operativa cambia hasta que un usuario con rol supervisor registre explícitamente su aprobación.

**Acceptance Scenarios**:

1. **Given** una propuesta de calibración de umbrales generada por el agente, **When** el supervisor accede al panel de políticas, **Then** puede inspeccionar la justificación técnica, el impacto proyectado y aprobar o rechazar el cambio.
2. **Given** un intento del agente o de un proceso automatizado de alterar la configuración de contacto directamente, **When** se procesa la solicitud, **Then** el sistema rechaza la modificación si no cuenta con la firma de aprobación supervisora.

---

### User Story 4 - Comparación de Desempeño y Simulación Histórica (Priority: P4)

Como analista o tomador de decisiones, quiero simular la evolución diaria de una cartera completa y comparar el desempeño del agente adaptativo frente a una campaña fija tradicional, para cuantificar la reducción de contactos innecesarios y la mejora en la anticipación de pagos.

**Why this priority**: Permite evidenciar el valor del agente en una demostración interactiva reproducible (hackathon), facilitando la comprensión visual del comportamiento temporal de la cartera.

**Independent Test**: Puede probarse ejecutando una simulación de 30 días con una semilla fija y contrastando las métricas acumuladas (avisos totales, tasa de pago oportuno, días promedio de anticipación) entre ambas estrategias.

**Acceptance Scenarios**:

1. **Given** una cartera de prueba generada con semilla fija, **When** se reproduce el paso diario del tiempo, **Then** la interfaz refleja día a día los estados de cliente, decisiones tomadas, correos capturados y métricas acumuladas.
2. **Given** la ejecución simultánea de la estrategia del agente y la campaña fija sobre la misma cartera, **When** concluye el ciclo de evaluación, **Then** el sistema genera una gráfica comparativa mostrando volumen de avisos, pagos anticipados y anticipación promedio.

---

### Edge Cases

- **Pago registrado justo antes de la hora de envío**: Si un cliente abona su obligación durante la ventana de revisión (entre las 09:00 y las 10:00) o mientras se procesa la cola, la herramienta de despacho consulta el estado en tiempo real y cancela el envío de forma inmediata.
- **Historial crediticio corto (< 3 períodos)**: Si un cliente no cuenta con al menos 3 cuotas históricas evaluables, el sistema clasifica su evidencia como insuficiente y aplica la política por defecto: recordatorio neutro estándar sin tono firme ni escalamiento.
- **Zona de histéresis y oscilación de bandas**: Para evitar fluctuaciones erráticas entre bandas por variaciones mínimas de probabilidad, el cliente debe superar el umbral de corte por un margen estricto de al menos 0.05 o sostener la nueva banda durante dos ciclos consecutivos antes de consolidar el cambio.
- **Fallo de validación en redacción generativa**: Si el texto generado por el modelo de lenguaje incluye lenguaje apremiante, menciones a la banda de riesgo interna o no respeta la plantilla autorizada, el validador rechaza el texto y aplica de manera automática la plantilla preaprobada de contingencia con tono neutro.
- **Días no hábiles y feriados**: Si una fecha de contacto programada coincide con sábado, domingo o día feriado, la herramienta adelanta el aviso al día hábil inmediatamente anterior.
- **Exploración controlada del momento óptimo**: La adaptación del día de envío dentro de la ventana autorizada mantiene siempre un 10% de exploración aleatoria controlada para evitar estancamiento en óptimos locales, garantizando que jamás se seleccione una fecha fuera de los límites de la ventana.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 [Datos dummy reproducibles]**: El sistema DEBE generar conjuntos de datos de prueba reproducibles mediante semilla fija, conteniendo perfiles de clientes estables, clientes con deterioro progresivo previo al atraso, moras ocasionales y crónicas, pagos con demora de acreditación, inconsistencias de registro y clientes nuevos.
- **FR-002 [Acceso a datos por interfaz de repositorio]**: El sistema DEBE acceder a la información de clientes mediante una interfaz desacoplada de repositorio que reciba la fecha de corte y retorne el historial por período (vencimiento, fecha real de pago, fecha contable, saldo, límite, pago mínimo, correo electrónico y habilitación de contacto). Para la demo, el repositorio DEBE implementarse sobre almacenamiento local embebido (SQLite) preparado para intercambio futuro con bases relacionales cliente-servidor (PostgreSQL) sin alterar la lógica de negocio.
- **FR-003 [Cálculo riguroso de señales a fecha de corte]**: El sistema DEBE calcular, exclusivamente con datos disponibles a la fecha de corte, señales de comportamiento histórico (días de atraso, recurrencia y tendencia) y señales de deterioro temprano (porcentaje de uso de línea, sostenimiento de pagos mínimos durante al menos 3 períodos consecutivos y caída del monto pagado respecto al facturado). Queda estrictamente prohibido el uso de información posterior a la fecha de corte.
- **FR-004 [Estimación y calibración de probabilidad de atraso]**: El sistema DEBE estimar la probabilidad de atraso en la cuota subsiguiente mediante un modelo de Regresión Logística calibrada (método de Platt o Regresión Isotónica) con coeficientes explicables por señal, generando reportes con métricas de capacidad de discriminación (AUC) y error de calibración (Brier Score).
- **FR-005 [Clasificación en bandas de riesgo con histéresis]**: El sistema DEBE segmentar la probabilidad en cuatro bandas internas (Baja, Moderada, Alta, Crítica) con umbrales configurables. El cambio de banda DEBE exigir una diferencia superior a 0.05 sobre el corte o la permanencia en la nueva banda durante dos ciclos consecutivos. La banda asignada NO DEBE comunicarse al cliente ni guardarse como una etiqueta de mora identitaria permanente.
- **FR-006 [Verificación y tipificación de evidencia]**: El sistema DEBE clasificar formalmente la evidencia de cada caso en suficiente, insuficiente (< 3 períodos de historial o datos faltantes) o inconsistente (pagos no reflejados o discrepancias de registro) mediante reglas deterministas.
- **FR-007 [Política de contingencia por evidencia insuficiente]**: Para clientes con evidencia insuficiente, el sistema DEBE aplicar una política restrictiva consistente en un recordatorio por correo con redacción estándar y tono neutro, quedando prohibido el uso de tono firme o escalamiento.
- **FR-008 [Configuración declarativa de políticas]**: Las ventanas de contacto, la cuota máxima de avisos y la separación temporal mínima por banda DEBEN residir en archivos de configuración declarativos. Los valores iniciales por defecto son:
  - **Banda Baja**: 0 avisos preventivos; post-vencimiento en ventana D+2 a D+5 (máximo 1 aviso, tono neutro).
  - **Banda Moderada**: Preventivo en ventana D-3 a D-1 (máximo 1 aviso, tono preventivo); post-vencimiento en ventana D+1 a D+5 (máximo 1 aviso, tono neutro, separación mínima de 2 días).
  - **Banda Alta**: Preventivo en ventana D-5 a D-1 (máximo 2 avisos, tono preventivo, separación mínima de 2 días); post-vencimiento en ventana D+1 a D+7 (máximo 2 avisos, tono firme, separación mínima de 2 días).
  - **Banda Crítica**: Preventivo en ventana D-7 a D-1 (máximo 2 avisos, tono preventivo, separación mínima de 2 días); post-vencimiento en ventana D+1 a D+10 (máximo 3 avisos, tono firme, separación mínima de 2 días).
- **FR-009 [Investigación autónoma de inconsistencias]**: Ante inconsistencias o sospechas de pagos no reflejados, el agente DEBE consultar registros de transacciones en trámite y anomalías de registro, formular una hipótesis explicativa y verificarla. Si se resuelve favorablemente, reevalúa al cliente; si persiste la duda, DEBE derivar el caso con su expediente documentado a revisión humana.
- **FR-010 [Redacción parametrizada y validación de mensajes]**: La redacción de avisos DEBE basarse en plantillas estructuradas con inyección local de variables del cliente, impidiendo la salida de datos personales identificables (PII) a servicios externos. Todo mensaje generado DEBE someterse a un validador que verifique la ausencia de lenguaje amenazante/coercitivo, la no inclusión de bandas o scores de riesgo y el cumplimiento de las reglas de buen trato. Si el mensaje no supera la validación, el sistema DEBE sustituirlo automáticamente por la plantilla estándar neutral correspondiente.
- **FR-011 [Límites inviolables en la herramienta de envío]**: La herramienta responsable del despacho de avisos DEBE validar y rechazar de forma determinista cualquier intento de envío que ocurra fuera de la ventana horaria/calendario permitida, supere el máximo de avisos por ciclo, viole la separación mínima requerida o corresponda a un cliente con pago registrado o en proceso de verificación, con independencia de la instrucción emitida por el agente.
- **FR-012 [Ciclo de ejecución diaria y hora de corte]**: El sistema DEBE operar con una rutina diaria donde la revisión humana cierre a una hora determinada (ej. 09:00) y el despacho se ejecute a una hora fija (ej. 10:00), enviando únicamente los avisos que cuenten con aprobación de política o confirmación expresa del analista. Los casos derivados pendientes de revisión NO DEBEN ser despachados.
- **FR-013 [Gestión de cola de revisión priorizada]**: La interfaz DEBE presentar la cola de casos derivados ordenados por urgencia (días faltantes para el vencimiento) y nivel de riesgo, permitiendo al analista ingresar correcciones de datos y desencadenar la reevaluación inmediata del expediente por parte del agente.
- **FR-014 [Pista de auditoría y registro inmutable de decisiones]**: El sistema DEBE persistir por cada cliente y ciclo de evaluación un registro auditable que detalle: hechos observados a la fecha de corte, regla o política aplicada, decisión tomada, contenido del aviso emitido y autor de cualquier intervención manual.
- **FR-015 [Aislamiento de comunicaciones por captura SMTP]**: El despacho de correos DEBE operar sobre un servicio SMTP configurable por entorno. En la demo, el sistema DEBE levantar un servidor SMTP de prueba embebido en proceso de fondo (Python nativo), capturando y persistiendo el 100% de los correos emitidos en almacenamiento local (SQLite/memoria) sin emitir paquetes a redes externas ni requerir Docker.
- **FR-016 [Optimización adaptativa acotada del momento de contacto]**: Dentro de la ventana autorizada para cada banda, el agente DEBE seleccionar el día de contacto óptimo con base en la tasa observada de pago oportuno por alternativa, incorporando una tasa mínima de exploración aleatoria del 10% y garantizando que jamás se seleccione un momento exterior a la ventana.
- **FR-017 [Módulo de evaluación comparativa de efectividad]**: El sistema DEBE ejecutar en paralelo sobre la misma cartera la estrategia del agente frente a una campaña tradicional fija por segmento, computando y comparando: volumen total de avisos emitidos, porcentaje de pagos anticipados y promedio de días de anticipación de pago.
- **FR-018 [Interfaz visual de control y demostración]**: El sistema DEBE proveer una aplicación web interactiva en **Streamlit** que se ejecute localmente y consolide: panel de estado de cartera y decisiones diarias, vista de expediente por cliente, cola interactiva de revisión humana con corrección de datos, visor de la bandeja de correos SMTP capturados y visualización gráfica comparativa de estrategias.
- **FR-019 [Motor de reproducción y simulación histórica]**: El sistema DEBE permitir avanzar temporalmente día a día una simulación histórica, ejecutando el ciclo analítico, registrando decisiones y actualizando el estado de la cartera en cada jornada.

### Key Entities

- **Cliente**: Representa al titular de una obligación financiera. Atributos conceptuales: identificador único, nombre/referencia de contacto local, dirección de correo electrónico, indicador de contacto habilitado.
- **Obligación / Cuenta**: Instrumento crediticio asociado al cliente. Atributos conceptuales: saldo adeudado, límite de crédito asignado, pago mínimo requerido, fecha de vencimiento pactada, estado de cumplimiento.
- **Historial de Período**: Registro periódico del comportamiento de la cuenta a la fecha de corte. Atributos conceptuales: monto facturado, fecha efectiva de pago, fecha de registro administrativo, monto efectivamente pagado, días de atraso acumulados.
- **Señales de Deterioro**: Conjunto de indicadores calculados a la fecha de corte. Atributos: ratio de utilización de línea, conteo de pagos mínimos consecutivos, variación porcentual del pago respecto a lo facturado, métricas de recurrencia y tendencia de atraso.
- **Evaluación y Decisión**: Registro de juicio emitido por el agente para un cliente en una fecha específica. Atributos: probabilidad estimada de atraso, banda asignada (Baja, Moderada, Alta, Crítica), calidad de evidencia (Suficiente, Insuficiente, Inconsistente), acción decidida (No contactar, Programar aviso, Investigar, Derivar), justificación y regla aplicada.
- **Aviso de Cobranza**: Mensaje elaborado para ser remitido al cliente. Atributos: canal (exclusivamente correo electrónico), plantilla utilizada, variables inyectadas, tono asignado (Neutro, Preventivo, Firme), estado de validación sintáctica/ética, fecha y hora programada, estado de envío (Programado, Aprobado, Rechazado por herramienta, Enviado, Capturado).
- **Expediente en Cola de Revisión**: Caso derivado para supervisión humana. Atributos: cliente asociado, motivo de derivación, hipótesis del agente, datos en conflicto, estado de resolución, acciones de corrección aplicadas.
- **Política de Contacto**: Reglas gobernantes del ciclo de vida de cobro. Atributos: ventana de contacto (días pre/post vencimiento), cuota máxima de avisos permitidos, intervalo de separación mínima entre contactos, tono autorizado por banda.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 [Prevención de contactos indebidos]**: El 100% de los intentos de contactar a clientes que hayan completado su pago, que mantengan pagos en trámite o que infrinjan los topes y ventanas de la política son interceptados y bloqueados por la herramienta sin llegar a emitirse.
- **SC-002 [Eficacia en detección temprana]**: Al menos el 80% de los clientes simulados que desarrollan un patrón de deterioro progresivo (uso de línea > 90% y pagos mínimos sostenidos) son identificados y escalados a banda de riesgo Alta o Crítica antes de acumular su primer día de atraso formal.
- **SC-003 [Reducción de contactos superfluos]**: La estrategia adaptativa del agente reduce en al menos un 25% el volumen total de avisos emitidos hacia clientes de riesgo bajo y moderado en comparación con una campaña fija tradicional sobre la misma cartera.
- **SC-004 [Anticipación efectiva del pago]**: La estrategia del agente logra una anticipación promedio en la fecha de pago de al menos 1.5 días antes del vencimiento en los clientes que reciben recordatorios preventivos.
- **SC-005 [Cumplimiento estricto de privacidad y buen trato]**: El 100% de los mensajes de correo despachados superan la validación ética previa, garantizando cero menciones a bandas internas, cero adjetivos peyorativos ("moroso") y cero fuga de datos personales sensibles a servicios externos.
- **SC-006 [Aislamiento seguro de pruebas]**: El 100% de las comunicaciones emitidas durante la ejecución de la demo son capturadas en el entorno local de prueba sin registrarse salidas hacia servidores de correo en internet.
- **SC-007 [Rendimiento en ejecución de ciclo local]**: El ciclo completo de evaluación diaria para una cartera simulada de al menos 100 clientes se completa en menos de 10 segundos en una estación de trabajo local convencional.

## Assumptions

- **Horarios operativos del ciclo**: El cierre diario de la cola de revisión se asume fijado a las 09:00 y la ventana de despacho de correos aprobados se asume a las 10:00 (ambos en la zona horaria local del sistema).
- **Ventanas y calendario hábil**: Las ventanas de contacto se definen en días calendario, pero los envíos no se realizan en fines de semana ni feriados oficiales; en dichos casos, la herramienta anticipa la acción al día hábil inmediatamente anterior.
- **Demora estándar de reflejo bancario**: Se establece un supuesto de 2 días hábiles como plazo uniforme para la acreditación bancaria y reflejo contable de pagos entre diferentes entidades.
- **Capacidad operativa de revisión humana**: Se asume una capacidad de atención del analista de hasta el 20% de los clientes evaluados en la cartera diaria.
- **Canal de contacto unificado**: El canal de contacto se modela de manera explícita y exclusiva como correo electrónico (`email`).
- **Validez de resultados**: Los resultados y tasas de conversión obtenidos en la demo evidencian el funcionamiento y la coherencia del mecanismo técnico, sin constituir proyecciones de efectividad comercial en entornos productivos reales.
