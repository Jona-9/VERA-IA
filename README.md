# VERAIA · Agente de cobranza temprana

Demo de un agente que avisa a tiempo, con buen trato y dentro de límites que el código hace cumplir.
Evalúa una cartera simulada cada día, decide a quién avisar y cuándo, deriva a una persona lo dudoso y
envía los recordatorios a un servidor de correo local. **Todos los datos son simulados** y ningún correo
sale de este equipo.

## Cómo correrlo

```bash
./demo.sh            # http://localhost:8501   (PORT=8600 ./demo.sh para otro puerto)
```

`demo.sh` crea el entorno virtual (Python 3.11+), instala dependencias, genera la cartera con
`seed=42`, entrena el modelo si falta y abre la interfaz. El servidor SMTP de captura arranca solo en
`127.0.0.1:1025`.

### Envío real de correos (opcional)

Por defecto los avisos solo llegan a la bandeja de captura local. Para enviarlos de verdad por SMTP:
copia `.env.example` a `.env`, completa host, usuario, clave y remitente, y corre `./demo.sh` (carga `.env`).
Con `VERAIA_MAIL_REDIRECT_TO` todos los avisos van a esa dirección de prueba (el cliente original queda en el
asunto y en la cabecera `X-VERAIA-Original-Recipient`). Escribir a los correos de la cartera exige
`VERAIA_MAIL_ALLOW_REAL_RECIPIENTS=1`; sin ninguna de las dos variables, el arranque falla. Si el proveedor
rechaza un aviso, ese aviso queda `REJECTED` con el motivo y el resto del despacho continúa.

Otros comandos útiles:

```bash
python -m src.cli.run_cycle --date 2026-10-15 --days 3 --auto-review   # ciclo diario sin interfaz
pytest tests/                                                           # pruebas
```

## Guía de evaluación (5 minutos)

La barra superior controla el día simulado. Cada día tiene dos momentos: a las 09:00 cierra la revisión
y a las 10:00 salen los avisos aprobados.

1. **Hoy** muestra las decisiones que esperan revisión antes de las 09:00 y lo que el agente hace solo.
2. **Por revisar**: abre un caso de pago en proceso, confirma el pago y pulsa *Reevaluar*. El caso se
   resuelve, se audita la corrección y el agente decide de nuevo en el acto (si había un aviso aprobado, se anula).
3. **Cerrar revisión y enviar a las 10:00**: los avisos de cuentas con casos sin revisar quedan retenidos.
4. **Notificaciones → Bandeja de correos**: los correos que llegaron al socket SMTP local, con el nombre
   inyectado en local y sin mencionar bandas, puntuaciones ni adjetivos despectivos (ToneGuard).
5. **Clientes**: abre un expediente (señales, historial, avisos, auditoría) y usa *Intentar programar un
   aviso hoy* para ver a `ScheduleNoticeTool` rechazar con un código (`ERR_MAX_NOTICES_EXCEEDED`,
   `ERR_MIN_SEPARATION_VIOLATED`, `ERR_OUTSIDE_WINDOW`…) lo que rompe la política.
6. **Efectividad**: compara al agente con una campaña fija por segmento sobre los mismos clientes simulados.
7. Pasa varios días con *Pasar al día siguiente* para ver pagos simulados, avisos posteriores al vencimiento
   y casos de avisos agotados.

## Qué hace cada pieza

| Pieza | Dónde |
|---|---|
| Ciclo diario (09:00 corte, 10:00 despacho) | `src/agent/orchestrator.py`, `src/cli/run_cycle.py` |
| Reevaluación tras corrección de pago | `src/tools/reevaluate_tool.py` |
| Bandit ε-greedy (ε = 10 %) del día de envío, solo dentro de la ventana autorizada | `src/policy/bandit.py` |
| Reproducción histórica día por día | `src/simulation/engine.py` |
| Campaña fija y comparación | `src/simulation/benchmark.py` |
| Interfaz | `src/ui/` (`app.py`, `services.py`, `theme.py`, `views/`) |

El orquestador no decide qué está permitido: usa `src/policy/engine.py` (bandas, histéresis, calidad de
evidencia) y `ScheduleNoticeTool` (ventana, tope de avisos, separación, tono, pago hecho o en trámite).
La interfaz y el diseño siguen `propose-design/` ("Hoy · Cobranza temprana").

## Supuestos declarados

- **Datos simulados.** Cartera sintética reproducible (`seed=42`, 60 clientes, corte 2026-10-15). Nada es real.
- **Respuesta de los clientes simulada.** Cada cliente tiene una fecha natural de pago derivada de su
  historial y un sorteo semillado; un recordatorio preventivo puede adelantarla (más probable a 2 días del
  vencimiento) y uno posterior al vencimiento puede acortar el atraso. Estas probabilidades son supuestos
  del simulador (`REMINDER_LIFT`, `POST_DUE_RESPONSE` en `src/simulation/engine.py`), no evidencia.
- **Un pago simulado cancela el saldo.** Así la cuenta pasa a `PAID` y la herramienta bloquea nuevos avisos.
- **Revisión humana simulada en el benchmark.** En la interfaz la haces tú; en el benchmark un analista
  simulado confirma los pagos en trámite.
- **Un pago en proceso abre un caso de confirmación**, además de suspender el contacto: el agente formula
  la hipótesis y una persona confirma la acreditación.
- **Historial corto (< 3 períodos)**: aviso neutro estándar y banda no inferior a MODERADA (RF-07).
- **Avisos agotados**: si un cliente sigue sin pagar tras el último aviso permitido, el caso pasa a una persona.
- **Aprendizaje del bandit en memoria**: se reinicia al reiniciar la demo.
- **Sin LLM por defecto.** Las plantillas Jinja2 redactan los avisos; un LLM solo interviene si se configura
  por entorno, y nunca recibe datos personales.

## Resultados del benchmark (21 días, semilla 42)

| | Agente | Campaña fija |
|---|---|---|
| Avisos enviados | 57 | 84 |
| Avisos a riesgo bajo/moderado | 15 | 28 (−46 % con el agente) |
| Pagos antes del vencimiento | 21 | 26 |
| Pago a tiempo | 63 % | 67 % |
| Anticipación media (pagaron a tiempo) | 1,0 días | 1,2 días |
| Avisos a clientes con pago en trámite | 0 | 0 |

El agente cumple la meta de reducir al menos un 25 % los avisos a riesgo bajo y moderado (SC-003) y logra
resultados de pago comparables con un 32 % menos de avisos. **No alcanza la meta de 1,5 días de anticipación (SC-004)**
en esta simulación: la campaña fija avisa a todos antes del vencimiento y el simulador premia ese contacto.
Las cifras dependen de los supuestos de arriba y cambian si se modifican.

## Limitaciones

- El modelo de riesgo (otro integrante) separa casi todo en riesgo bajo o crítico; las bandas intermedias
  casi no se ven en la demo.
- Las cuentas tienen un solo vencimiento: no hay ciclos de facturación posteriores.
- La interfaz es de un solo analista y sin autenticación.
