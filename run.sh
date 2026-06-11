#!/usr/bin/env bash
# Quantum Potential AI - launcher portable (Git Bash / WSL / Linux / macOS)
set -euo pipefail

cd "$(dirname "$0")"

# 1) Verificar Python
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] Python no esta instalado." >&2
  echo "Instalalo desde https://www.python.org/downloads/" >&2
  exit 1
fi
PY=$(command -v python3 || command -v python)

# 2) Crear venv si no existe
if [ ! -d ".venv" ]; then
  echo "[setup] Creando entorno virtual .venv..."
  "$PY" -m venv .venv
fi

# 3) Activar venv (compat Git Bash + POSIX)
if [ -f ".venv/Scripts/activate" ]; then
  # Windows (Git Bash)
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 4) Instalar deps si es la primera vez
if [ ! -f ".venv/.deps_installed" ]; then
  echo "[setup] Instalando dependencias..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch .venv/.deps_installed
fi

# 5) Cargar .env si existe
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# 6) Arrancar Streamlit
echo "[run] Abriendo http://localhost:8501 ..."
exec python -m streamlit run app.py
