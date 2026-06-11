@echo off
REM Quantum Potential AI - launcher para Windows
REM Crea venv si no existe, instala deps, arranca Streamlit.

setlocal
cd /d "%~dp0"

REM 1) Verificar Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en PATH.
    echo Instalalo desde https://www.python.org/downloads/ y volve a correr.
    pause
    exit /b 1
)

REM 2) Crear venv si no existe
if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creando entorno virtual .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear .venv
        pause
        exit /b 1
    )
)

REM 3) Activar venv
call ".venv\Scripts\activate.bat"

REM 4) Instalar/actualizar dependencias si requirements cambio
if not exist ".venv\.deps_installed" (
    echo [setup] Instalando dependencias por primera vez...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion de requirements.
        pause
        exit /b 1
    )
    echo done > .venv\.deps_installed
)

REM 5) Cargar .env si existe
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
)

REM 6) Arrancar Streamlit
echo [run] Abriendo http://localhost:8501 ...
python -m streamlit run app.py
endlocal
