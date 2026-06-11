@echo off
REM Quantum Potential AI - launcher para Windows
REM Crea venv si no existe, reinstala deps solo si requirements.txt cambio,
REM arranca Streamlit y deja la ventana abierta si hay error.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ===============================================
echo   Quantum Potential AI - launcher
echo ===============================================
echo.

REM ----------------------------------------------------------------
REM 1) Verificar Python real (no el stub de Microsoft Store)
REM ----------------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en PATH.
    echo Descargalo desde https://www.python.org/downloads/
    echo IMPORTANTE: durante la instalacion marca "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

REM Detectar el stub de Python de Microsoft Store (causa muy comun de "no pasa nada")
python -c "import sys; sys.exit(0)" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] El "python" que esta en PATH parece ser el stub de Microsoft Store.
    echo Instala Python real desde https://www.python.org/downloads/
    echo y desactivar el alias en: Configuracion - Apps - Alias de ejecucion de aplicaciones
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo [info] %PYVER%

REM ----------------------------------------------------------------
REM 2) Crear venv si no existe
REM ----------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creando entorno virtual .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el venv.
        pause
        exit /b 1
    )
)

REM ----------------------------------------------------------------
REM 3) Activar venv
REM ----------------------------------------------------------------
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] No se pudo activar el venv.
    pause
    exit /b 1
)

REM ----------------------------------------------------------------
REM 4) Detectar cambios en requirements.txt via SHA256
REM    Reinstala solo si el hash es distinto al guardado.
REM ----------------------------------------------------------------
set "REQ_HASH_FILE=.venv\.requirements.sha256"
set "REQ_HASH_CUR="
for /f "skip=1 tokens=*" %%h in ('certutil -hashfile requirements.txt SHA256 ^| findstr /v ":"') do (
    if not defined REQ_HASH_CUR set "REQ_HASH_CUR=%%h"
)
set "REQ_HASH_OLD="
if exist "%REQ_HASH_FILE%" (
    for /f "usebackq tokens=*" %%h in ("%REQ_HASH_FILE%") do set "REQ_HASH_OLD=%%h"
)

if not "%REQ_HASH_CUR%"=="%REQ_HASH_OLD%" (
    echo [setup] requirements.txt cambio o es primera vez - instalando deps...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Fallo "pip install -r requirements.txt".
        echo Revisa el mensaje arriba. Causas tipicas:
        echo   - sin conexion a internet
        echo   - falta compilador C/C++ para algun paquete
        echo   - version de Python incompatible (recomendado 3.10+)
        echo.
        pause
        exit /b 1
    )
    > "%REQ_HASH_FILE%" echo %REQ_HASH_CUR%
    echo [setup] Deps instaladas OK.
) else (
    echo [info] Deps ya instaladas (requirements.txt sin cambios).
)

REM ----------------------------------------------------------------
REM 5) Verificar que streamlit existe en el venv
REM ----------------------------------------------------------------
python -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Streamlit no quedo instalado en el venv.
    echo Borra la carpeta .venv y volve a correr run.bat.
    pause
    exit /b 1
)

REM ----------------------------------------------------------------
REM 6) Arrancar Streamlit
REM ----------------------------------------------------------------
echo.
echo [run] Arrancando Streamlit en http://localhost:8501 ...
echo       Si no abre el navegador solo, pega esa URL a mano.
echo       Para detener: Ctrl+C en esta ventana.
echo.
python -m streamlit run app.py
set "ST_EXIT=%errorlevel%"

if not "%ST_EXIT%"=="0" (
    echo.
    echo [ERROR] Streamlit termino con codigo %ST_EXIT%.
    echo Revisa el mensaje arriba.
    pause
)

endlocal
