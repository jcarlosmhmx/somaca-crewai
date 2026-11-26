#!/usr/bin/env bash
# Instala dependencias, corre pruebas, levanta API + GUI y toma capturas de una corrida real.
# Uso (desde la raíz del repo, con .venv de Python 3.11/3.12):
#   bash scripts/demo_local.sh            # corrida en vivo con el LLM de .env
#   bash scripts/demo_local.sh --replay   # modo respaldo
# Puertos (por si 8000/8501 ya están ocupados por otro proyecto): API_PORT=8010 UI_PORT=8510
set -euo pipefail
cd "$(dirname "$0")/.."
API_PORT="${API_PORT:-8010}"
UI_PORT="${UI_PORT:-8510}"
for p in "$API_PORT" "$UI_PORT"; do
  if lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "El puerto $p ya está en uso. Ciérralo o usa otro: API_PORT=8020 UI_PORT=8520 bash scripts/demo_local.sh"; exit 1
  fi
done
source .venv/bin/activate
pip install -q -r requirements.txt playwright
python -m playwright install chromium
python -m pytest -q
mkdir -p logs
export SOMACA_API="http://localhost:$API_PORT" SOMACA_UI="http://localhost:$UI_PORT"
uvicorn api.main:app --port "$API_PORT" > logs/api_demo.log 2>&1 &
API_PID=$!
streamlit run ui/app.py --server.port "$UI_PORT" --server.headless true > logs/ui_demo.log 2>&1 &
UI_PID=$!
trap 'kill $API_PID $UI_PID 2>/dev/null || true' EXIT
sleep 8
curl -sf "$SOMACA_API/salud" || { echo "La API no respondió; revisa logs/api_demo.log"; exit 1; }
echo
python scripts/capturas.py "$@"
