#!/usr/bin/env bash
# Quantum Potential AI - launcher portable (Git Bash / WSL / Linux / macOS)
# Reinstala el proyecto solo si pyproject.toml cambia (hash SHA256).
set -euo pipefail

cd "$(dirname "$0")"

echo "==============================================="
echo "  Quantum Potential AI - visor (sin API)"
echo "==============================================="
echo
echo "  Nota: el flujo principal es el CLI 'python -m qpot' manejado por tu"
echo "  agente (Claude Code / ChatGPT / Codex). Ver AGENTS.md."
echo "  Esto solo abre el visor humano (mover parametros, resolver, exportar)."
echo

# 1) Verificar Python
if command -v python3 >/dev/null 2>&1; then
  PY=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
  PY=$(command -v python)
else
  echo "[ERROR] Python no esta instalado." >&2
  echo "Instalalo desde https://www.python.org/downloads/" >&2
  exit 1
fi
echo "[info] $($PY --version 2>&1)"

# 2) Crear venv si no existe
if [ ! -d ".venv" ]; then
  echo "[setup] Creando entorno virtual .venv ..."
  "$PY" -m venv .venv
fi

# 3) Activar venv (compat Git Bash + POSIX)
if [ -f ".venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 4) Detectar cambios en requirements.txt via SHA256
hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"
  fi
}
REQ_HASH_FILE=".venv/.requirements.sha256"
REQ_HASH_CUR=$(hash_file pyproject.toml)
REQ_HASH_OLD=$(cat "$REQ_HASH_FILE" 2>/dev/null || true)

if [ "$REQ_HASH_CUR" != "$REQ_HASH_OLD" ]; then
  echo "[setup] pyproject.toml cambio o es primera vez - instalando proyecto..."
  python -m pip install --upgrade pip
  if ! python -m pip install -e .; then
    echo
    echo "[ERROR] Fallo pip install -e ." >&2
    exit 1
  fi
  echo "$REQ_HASH_CUR" > "$REQ_HASH_FILE"
  echo "[setup] Deps instaladas OK."
else
  echo "[info] Proyecto ya instalado (pyproject.toml sin cambios)."
fi

# 5) Entorno listo - abrir visualizador local
echo
echo "[ok] Entorno listo (sin API paga)."
echo
echo "  Abriendo visualizador local en Streamlit:"
echo
echo "     http://localhost:8501"
echo
echo "  El agente puede seguir usando el CLI qpot sobre la misma sesion."
echo
python -m streamlit run app.py
