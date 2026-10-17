<!--
# Sync Impact Report
- Version change: Unversioned template -> 1.0.0
- List of modified principles:
  - Template placeholders replaced with 12 Core Non-Negotiable Principles:
    - I. Proporcionalidad del Contacto
    - II. Límites Duros en Herramientas (Tool-Enforced Boundaries)
    - III. IA Generativa Redacta, No Decide
    - IV. Integridad Temporal y Prohibición de Fuga del Futuro
    - V. Medición Rigurosa del Atraso
    - VI. Conservadurismo Operativo y Derivación Ante la Duda
    - VII. Trazabilidad y Explicabilidad Total
    - VIII. Evaluación Puntual y Cero Estigmatización
    - IX. Inmutabilidad de Políticas por el Agente (Aprobación Supervisora)
    - X. Honestidad en Resultados y Simulación de Demo
    - XI. Privacidad Estricta y Desacoplamiento de Datos Personales
    - XII. Seguridad de Demo y Aislamiento de Entorno (Captura SMTP)
- Added sections:
  - Reglas de Buen Trato (No Negociables)
  - Principios de Ingeniería y Arquitectura
  - Restricciones y Alcance de la Demo
  - Governance
- Removed sections: Template placeholder sections replaced
- Follow-up TODOs: None
-->

# VERAIA Constitution

## Core Principles

### I. Proporcionalidad del Contacto
La anticipación y la intensidad del contacto DEBEN ser estrictamente proporcionales al nivel de
riesgo estimado del cliente. Un cliente clasificado con riesgo bajo NO DEBE ser objeto de
contactos reiterados ni de recordatorios excesivamente anticipados que constituyan hostigamiento.
*Razón*: Proteger la relación comercial y la tranquilidad del cliente, focalizando la atención
operativa donde existe un riesgo real de deterioro.

### II. Límites Duros en Herramientas (Tool-Enforced Boundaries)
Las restricciones operativas y límites de seguridad DEBEN residir de forma inviolable en el código
y contratos de las herramientas de acción, NUNCA exclusivamente en las instrucciones o prompts
del agente. Ninguna herramienta de despacho PODRÁ enviar avisos fuera de las ventanas horarias
autorizadas, por encima de la cuota máxima permitida de avisos, ni a clientes con obligaciones
pagadas o con pagos en proceso de validación, sin importar la decisión o razonamiento del agente.
*Razón*: El razonamiento del modelo de lenguaje puede alucinar o degradarse; las herramientas
constituyen la barrera determinista e infranqueable de protección.

### III. IA Generativa Redacta, No Decide
La decisión de contactar, la ventana de envío y la selección de tono DEBEN ser gobernadas
taxativamente por reglas deterministas y políticas auditables. El modelo de lenguaje (LLM) actúa
única y exclusivamente como redactor dentro de una plantilla controlada. Toda salida generada
DEBE superar una validación formal (de contenido y tono) antes de ser enviada.
*Razón*: Garantizar predictibilidad, equidad de trato y apego estricto a las políticas sin sesgos
o variabilidad no deseada en decisiones clave.

### IV. Integridad Temporal y Prohibición de Fuga del Futuro
Toda inferencia, cómputo de señales y decisión del agente DEBE sustentarse única y exclusivamente
en información fehacientemente disponible a la fecha de corte evaluada. Queda terminantemente
PROHIBIDO el uso de información futura (*lookahead bias* / fuga de datos del futuro), tanto en
la ejecución en tiempo real como en las evaluaciones retrospectivas y pruebas analíticas.
*Razón*: Prevenir evaluaciones ficticias y garantizar que el desempeño evaluado refleje fielmente
las condiciones operativas reales.

### V. Medición Rigurosa del Atraso
El atraso DEBE calcularse a partir de la fecha efectiva y real en que se realiza el pago, y no a
partir de la fecha contable o administrativa de registro en el sistema. Todo día calendario sin
pago posterior a la fecha de vencimiento pactada DEBE ser computado de inmediato como atraso.
*Razón*: Evitar distorsiones analíticas y reflejar con total precisión el comportamiento temporal
del cliente.

### VI. Conservadurismo Operativo y Derivación Ante la Duda
Ante señales inconsistentes, falta de información suficiente, anomalías o cualquier estado de duda,
el agente NO DEBE ejecutar acciones de contacto automáticas. En su lugar, DEBE investigar, posponer
el contacto o derivar el caso a revisión humana. Ningún aviso puede despacharse sin una
aprobación o respaldo inequívoco de las políticas establecidas.
*Razón*: Minimizar el riesgo de falsos positivos en el contacto que afecten negativamente la
experiencia de clientes en situaciones atípicas.

### VII. Trazabilidad y Explicabilidad Total
Toda decisión o abstención de contacto DEBE quedar registrada de forma auditable, estructurada y
persistente. El registro DEBE documentar con precisión: (1) las señales y datos observados,
(2) la regla o política específica aplicada y (3) la decisión ejecutada junto con su justificación.
*Razón*: Asegurar rendición de cuentas, auditabilidad regulatoria y permitir la depuración
continua del sistema.

### VIII. Evaluación Puntual y Cero Estigmatización
El nivel de riesgo DEBE ser tratado como una estimación contextual y puntual del momento presente,
NUNCA como una etiqueta fija o condición identitaria del cliente. Queda estrictamente PROHIBIDO
clasificar peyorativamente a un cliente como "moroso", así como revelar o comunicar la banda de
riesgo, score o categorización interna al cliente en cualquier comunicación.
*Razón*: Respetar la dignidad del cliente y mantener un tono profesional orientado a la
resolución de la obligación.

### IX. Inmutabilidad de Políticas por el Agente (Aprobación Supervisora)
El agente NO TIENE autorización para modificar sus propias políticas de decisión, umbrales de
riesgo, ventanas operativas ni reglas de buen trato. El agente PODRÁ proponer sugerencias o
ajustes analíticos, pero la aprobación y modificación DEBEN recaer exclusivamente en una persona
con rol supervisor debidamente acreditada.
*Razón*: Evitar la deriva de alineación y mantener el control humano sobre las reglas de negocio.

### X. Honestidad en Resultados y Simulación de Demo
Todos los datos de clientes, respuestas a comunicaciones y revisiones humanas generadas durante la
demo son de naturaleza simulada. Ningún resultado, tasa de contacto o métrica derivada de la demo
DEBE presentarse o interpretarse como prueba de efectividad o rendimiento en entornos reales de
producción.
*Razón*: Garantizar transparencia técnica y evitar falsas expectativas sobre la calibración del
sistema en condiciones no productivas.

### XI. Privacidad Estricta y Desacoplamiento de Datos Personales
Queda terminantemente PROHIBIDO utilizar variables personales sensibles (edad, género, estado
civil, origen étnico o datos análogos) o sustitutos indirectos (*proxies*) en los modelos y reglas.
Los datos personales identificables (PII) NUNCA DEBEN enviarse a proveedores externos de modelos
de lenguaje; la personalización de nombres o montos DEBE realizarse inyectando variables locales en
la plantilla previamente redactada y validada. El sistema DEBE ofrecer y soportar una opción de
modelo de lenguaje de ejecución local.
*Razón*: Cumplir con los más altos estándares de privacidad, gobernanza de datos y soberanía
operativa sin depender de nubes propietarias.

### XII. Seguridad de Demo y Aislamiento de Entorno (Captura SMTP)
Ningún correo electrónico generado en el contexto de la demo DEBE ser despachado a destinatarios o
servidores de correo reales. La totalidad de los mensajes salientes DEBE ser capturada localmente
mediante un servidor SMTP de prueba o emulador de buzón de desarrollo.
*Razón*: Prevenir incidentes de fuga de información o envíos accidentales a clientes durante
fases de prueba y demostración.

## Reglas de Buen Trato (No Negociables)

- **Control de Frecuencia y Cadencia**: Ningún cliente DEBE recibir contactos excesivos. El
  sistema DEBE respetar de manera obligatoria la cuota máxima de avisos por cliente y ciclo, así
  como la separación temporal mínima estipulada entre comunicaciones sucesivas.
- **Tono Respetuoso y No Coercitivo**: Las comunicaciones DEBEN ser redactadas en un tono cortés,
  profesional y constructivo. Queda estrictamente PROHIBIDO el uso de lenguaje amenazante,
  coercitivo, apremiante o engañoso.
- **Restricción Exclusiva del Tono Firme**: El tono firme DEBE reservarse única y exclusivamente
  para comunicaciones posteriores al vencimiento de la obligación, aplicable únicamente a clientes
  en banda de riesgo alta o crítica y siempre que exista evidencia fáctica suficiente documentada.
- **Reserva Total de la Clasificación Interna**: Los mensajes remitidos al cliente NUNCA DEBEN
  contener menciones, códigos ni referencias a bandas de riesgo, scores o clasificaciones internas.
- **Cese Inmediato por Pago**: Queda taxativamente PROHIBIDO contactar a clientes que hayan
  completado el pago de su obligación o que cuenten con un pago en proceso de verificación.

## Principios de Ingeniería y Arquitectura

- **Separación entre Lógica Determinista y Razonamiento Flexible**: Lo que deba ser auditable,
  estable y verificable DEBE resolverse mediante reglas explícitas o modelos cuantitativos medibles.
  El razonamiento flexible del agente DEBE reservarse únicamente para donde aporta valor
  diferencial: análisis de casos atípicos o dudosos, selección del momento óptimo dentro de la
  ventana autorizada y redacción adaptativa del mensaje.
- **Aislamiento de Fronteras Mediante Interfaces**: Todas las interacciones con el entorno externo
  (bases de datos, despacho de correos, proveedores de modelos de lenguaje) DEBEN encapsularse
  detrás de interfaces o adaptadores desacoplados, permitiendo sustituir o alternar
  implementaciones sin alterar la política de negocio central.
- **Configuración Explícita y Supuestos Declarados**: Cada parámetro de negocio y umbral operativo
  DEBE ser configurable externamente y contar con un valor por defecto explícitamente documentado
  como supuesto de diseño.
- **Canal Explícito Modelado**: El canal de comunicación DEBE modelarse formalmente como un
  concepto de primera clase en la arquitectura, restringido en esta etapa a un único valor:
  correo electrónico (`email`).

## Restricciones y Alcance de la Demo

- **Ejecución Local y Autosuficiente**: El sistema DEBE ejecutarse íntegramente en un entorno local,
  sin requerir suscripciones a servicios comerciales de pago ni dependencias externas obligatorias.
- **Datos Dummy Sintéticos y Reproducibles**: Los conjuntos de datos de prueba DEBEN ser generados
  mediante scripts reproducibles con semilla fija (*fixed seed*), asegurando la consistencia de
  escenarios en sucesivas ejecuciones.
- **Flujo Completo E2E como Hito Previo**: El ciclo completo de la demo (ingesta sintética,
  detección de señales, evaluación de riesgo, orquestación, redacción y captura en SMTP) DEBE
  ejecutarse con éxito de principio a fin antes de incorporar cualquier función o extensión adicional.

## Governance

- **Supremacía de la Constitución**: Esta constitución rige todas las decisiones de diseño,
  desarrollo, prueba e implementación en el proyecto. Ninguna instrucción o prompt operativo puede
  prevalecer sobre los principios aquí establecidos.
- **Procedimiento de Enmienda**: Toda enmienda a la constitución requiere documentación del cambio,
  justificación de la necesidad y aprobación formal por el rol supervisor. Cualquier modificación
  debe acompañarse de su correspondiente actualización de versión.
- **Política de Versionamiento Semántico**:
  - `MAJOR`: Modificación, eliminación o flexibilización de principios no negociables o reglas de
    buen trato.
  - `MINOR`: Incorporación de nuevos principios, reglas adicionales o ampliación material de
    directrices operativas.
  - `PATCH`: Ajustes de redacción, corrección de erratas o aclaraciones no semánticas.
- **Verificación en Revisiones y PRs**: Toda contribución o Pull Request DEBE ser verificada
  contra esta constitución. Cambios que vulneren los límites duros o la privacidad serán rechazados.

**Version**: 1.0.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-17
