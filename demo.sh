#!/usr/bin/env bash
# Levanta VERAIA con un solo comando: entorno, datos, modelo e interfaz (Streamlit + SMTP local).
# Uso: ./demo.sh            (puerto 8501)    PORT=8600 ./demo.sh
set -euo pipefail
cd "$(dirname "$0")"

pick_python() {
  for candidate in "${PYTHON:-}" python3.13 python3.12 python3.11 python3; do
    [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      echo "$candidate"; return
    fi
  done
  echo "Se necesita Python 3.11 o superior (defina PYTHON=/ruta/a/python)." >&2
  exit 1
}

if [ -f .env ]; then
  set -a; . ./.env; set +a   # credenciales SMTP del envío real (ver .env.example)
fi

if [ ! -d .venv ]; then
  "$(pick_python)" -m venv .venv
fi
.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f data/portfolio_demo.db ]; then
  .venv/bin/python -m src.cli.generate_data --seed 42 --db-path data/portfolio_demo.db
fi
if [ ! -f reports/risk_model.joblib ]; then
  .venv/bin/python -m src.cli.train_model --db data/portfolio_demo.db
fi

echo "VERAIA lista. Abre http://localhost:${PORT:-8501}  (los correos quedan en la bandeja local 127.0.0.1:1025)"
exec .venv/bin/streamlit run src/ui/app.py --server.port "${PORT:-8501}"
