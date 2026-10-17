# Quickstart & Validation Guide: Agente de Cobranza Temprana

**Feature**: `001-early-collection-agent`  
**Date**: 2026-10-17  
**Status**: Ready for Validation  

Esta guía describe los pasos para inicializar el entorno, generar los datos de prueba reproducibles, entrenar el modelo calibrado, ejecutar la simulación diaria y validar el vertical slice mediante la interfaz de Streamlit y las pruebas automatizadas.

---

## 1. Prerrequisitos

- **Python**: Versión 3.11 o superior instalada localmente (`python3 --version`).
- **Sistema Operativo**: macOS, Linux o Windows (WSL2 recomendado en Windows).
- **Entorno aislado**: `venv` o `conda`.
- **Cero dependencias externas**: No se requiere Docker, bases de datos remotas ni claves de API de pago obligatorias.

---

## 2. Instalación y Configuración del Entorno

```bash
# 1. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias del proyecto
pip install -r requirements.txt
```

### Contenido de Referencia de `requirements.txt`
```text
pandas>=2.2.0
numpy>=1.26.0
scikit-learn>=1.4.0
pydantic>=2.6.0
pyyaml>=6.0.1
jinja2>=3.1.3
aiosmtpd>=1.4.5
streamlit>=1.32.0
plotly>=5.19.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## 3. Guía de Ejecución y Validación Paso a Paso

### Paso 1: Generación de Datos Dummy Reproducibles (RF-01)
Genera la base de datos SQLite con una semilla pseudoaleatoria fija (`seed=42`) para garantizar perfiles de prueba idénticos (estables, deterioro incipiente, moras crónicas, inconsistencias de pago):
```bash
python -m src.cli.generate_data --seed 42 --output data/portfolio_demo.db
```
*Resultado Esperado*: Se genera el archivo `data/portfolio_demo.db` con tablas indexadas y un conjunto equilibrado de 100+ clientes y su historial de 6 cuotas.

### Paso 2: Entrenamiento y Reporte del Modelo Calibrado (RF-04)
Entrena la Regresión Logística calibrada con Platt scaling y genera las métricas de evaluación:
```bash
python -m src.cli.train_model --db data/portfolio_demo.db --output-metrics reports/model_evaluation.json
```
*Resultado Esperado*: Se imprime y guarda el reporte con `ROC-AUC >= 0.75` y `Brier Score < 0.15`.

### Paso 3: Ejecución de la Suite de Pruebas Unitarias y de Límites (pytest)
Verifica que las reglas de decisión y los límites duros en herramientas rechacen contactos indebidos:
```bash
pytest tests/ -v
```
*Resultado Esperado*: 100% de pruebas aprobadas, incluyendo:
- `test_tool_rejects_already_paid_customer`
- `test_tool_rejects_outside_window`
- `test_tool_rejects_max_notices_exceeded`
- `test_early_deterioration_escalates_to_high_risk_before_due`
- `test_unreviewed_cases_are_not_dispatched`

### Paso 4: Lanzamiento de la Interfaz Interactiva de Demostración (Streamlit) (RF-18)
Inicia la aplicación visual, la cual automáticamente levanta el servidor de captura SMTP local en segundo plano (`aiosmtpd` en `localhost:1025`):
```bash
streamlit run src/ui/app.py
```
*Resultado Esperado*: Se abre el navegador en `http://localhost:8501`.

---

## 4. Escenarios de Aceptación para Probar en la Demo

1. **Escenario Deterioro Temprano (Cliente con Uso 95% y Mínimos)**:
   - En la UI, filtrar el cliente con señal de deterioro.
   - Observar que su banda sube a **Alta** a pesar de estar al día.
   - Avanzar la simulación al día de la ventana preventiva (D-3): verificar que se programa un aviso con tono preventivo respetuoso.
2. **Escenario Límite Duro en Herramienta (Tope de Avisos)**:
   - Forzar en la UI un intento de programar un 3er aviso para un cliente en banda Alta (máximo permitido: 2).
   - Comprobar que la herramienta arroja un rechazo explícito (`ERR_MAX_NOTICES_EXCEEDED`) y el correo no se programa.
3. **Escenario Pago en Tránsito y Cola de Revisión**:
   - Observar un cliente con pago diferido: el agente lo marca como `INCONSISTENT` y formula la hipótesis de acreditación pendiente.
   - Entrar a la pestaña **Cola de Revisión**, ingresar la confirmación del pago y hacer clic en **Reevaluar**.
   - Comprobar que el caso se resuelve de inmediato y el aviso programado se cancela.
4. **Escenario Bandeja de Captura SMTP**:
   - Ir a la pestaña **Correos Capturados** de la interfaz.
   - Inspeccionar los mensajes recibidos físicamente por el socket SMTP local, verificando que el 100% de ellos respetó las reglas de buen trato y no mencionó bandas internas.
5. **Escenario Comparación contra Campaña Fija**:
   - Ver el gráfico comparativo en la pestaña **Efectividad y Métricas**: constatar la reducción de contactos en clientes de riesgo bajo y la anticipación media de pagos.
