@echo off
title Atlas POS - Agente de Impresion
cd /d "%~dp0"
cls

echo.
echo ============================================================
echo   ATLAS ONE
echo   Agente Local de Impresion
echo ============================================================
echo.
echo   ATLAS ONE - AGENTE LOCAL DE IMPRESION
echo   Conectando tu computadora con tu impresora
echo.
echo ------------------------------------------------------------
echo   Este agente permite que tu computadora se comunique con
echo   tu impresora de tickets.
echo.
echo   Atlas One POS podra enviar tickets desde el
echo   navegador hacia la impresora termica conectada a esta PC.
echo ------------------------------------------------------------
echo.
echo   Servidor local     https://127.0.0.1:9100
echo   Estado             https://127.0.0.1:9100/health
echo   Diagnostico        https://127.0.0.1:9100/diagnostics
echo   Version            3.0.0
echo   Modo               Puente local seguro HTTPS
echo.
echo ------------------------------------------------------------
echo.

set "AGENT_DIR=%~dp0"
set "CORE_DIR=%AGENT_DIR%core"

echo [INICIO]  Iniciando agente de impresion...
powershell -ExecutionPolicy RemoteSigned -Command "Get-ChildItem -Path '%AGENT_DIR%' -Recurse | Unblock-File" >nul 2>&1

set "PYTHON_CMD="
python --version >nul 2>&1
if %errorlevel% equ 0 set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    py --version >nul 2>&1
    if %errorlevel% equ 0 set "PYTHON_CMD=py"
)
if not defined PYTHON_CMD (
    python3 --version >nul 2>&1
    if %errorlevel% equ 0 set "PYTHON_CMD=python3"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python no encontrado. Descarga Python 3.10+ desde https://python.org
    echo         Marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
echo [OK]      Python detectado correctamente.

echo [INFO]    Liberando puerto 9100...
powershell -ExecutionPolicy RemoteSigned -Command "$pids = (Get-NetTCPConnection -LocalPort 9100 -ErrorAction SilentlyContinue).OwningProcess | Sort -Unique; foreach ($p in $pids) { if ($p -gt 0) { try { Stop-Process -Id $p -Force -ErrorAction Stop; Write-Host '  killed PID' $p } catch {} } }"
timeout /t 2 /nobreak >nul

set "VENV_DIR=%CORE_DIR%\venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO]    Preparando entorno local...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear venv.
        pause
        exit /b 1
    )
)
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "PIP=%VENV_DIR%\Scripts\pip.exe"

echo [INFO]    Instalando dependencias...
"%PIP%" install --upgrade pip -q
"%PIP%" install -r "%CORE_DIR%\requirements.txt" -q
if %errorlevel% neq 0 (
    echo [ERROR] Fallo instalacion. Revisa conexion a internet.
    pause
    exit /b 1
)

echo [INFO]    Registrando componentes de Windows (pywin32)...
"%PYTHON%" -m pywin32_postinstall -install >nul 2>&1
if %errorlevel% neq 0 (
    "%PYTHON%" "%VENV_DIR%\Scripts\pywin32_postinstall.py" -install >nul 2>&1
)

echo [INFO]    Conectando esta PC con la impresora...
echo [INFO]    Iniciando servidor local seguro...
echo.
echo [LISTO]   El agente de impresion esta funcionando.
echo [LISTO]   Tu computadora ya puede enviar tickets a la impresora.
echo.
echo [NOTA]    No cierres esta ventana.
echo [NOTA]    Puedes minimizarla mientras usas el punto de venta.
echo [NOTA]    Primera vez: abre https://127.0.0.1:9100/health
echo.

:loop
"%PYTHON%" "%CORE_DIR%\main.py"
echo.
echo [AVISO]   El agente se detuvo. Reiniciando en 5s... (Ctrl+C para salir)
timeout /t 5 /nobreak >nul
goto loop
