@echo off
REM ====================================================================
REM  ARRANQUE DA SIMULACAO — Monitorizacao HTP-4000
REM ====================================================================
REM  Este ficheiro arranca os processos Python da simulacao, cada um
REM  na sua propria janela. NAO arranca o Mosquitto (broker MQTT) nem
REM  o MySQL — esses tem de estar a correr ANTES de executar este .bat.
REM
REM  Cenario: publisher_normal.py (funcionamento normal, sem alertas)
REM ====================================================================

REM Garante que o diretorio de trabalho e o desta pasta
cd /d "%~dp0"

echo ====================================================================
echo   SIMULACAO HTP-4000 — Arranque
echo ====================================================================
echo.

REM ── Verificacao 1: ficheiro .env ────────────────────────────────────
if not exist ".env" (
    echo [ERRO] Ficheiro .env nao encontrado nesta pasta.
    echo.
    echo    A password do MySQL e lida do ficheiro .env, que nao existe.
    echo    Para criar:
    echo      1. Copia o ficheiro ".env.exemplo" para ".env"
    echo      2. Abre o .env e escreve a tua password:
    echo            MYSQL_PASSWORD=a_tua_password
    echo.
    echo    Depois volta a correr este ficheiro.
    echo.
    pause
    exit /b 1
)
echo [OK] Ficheiro .env encontrado.

REM ── Verificacao 2: Python acessivel ─────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] O comando "python" nao foi encontrado.
    echo    Confirma que o Python 3.11+ esta instalado e no PATH.
    echo.
    pause
    exit /b 1
)
echo [OK] Python encontrado.
echo.

echo A arrancar os processos ^(cada um na sua janela^)...
echo.

REM ── Arranque dos processos, cada um em janela propria ───────────────
REM O "timeout" entre arranques da tempo a cada processo para ligar
REM a base de dados / broker antes do seguinte comecar.

echo   1/5  Subscritor  (grava as leituras na base de dados)
start "DB Subscriber" cmd /k python db_subscriber.py
timeout /t 2 /nobreak >nul

echo   2/5  Alertas     (temperatura e vibracao)
start "Alertas" cmd /k python alertas.py
timeout /t 1 /nobreak >nul

echo   3/5  Anomalias   (corrente, por regime SPC)
start "Anomalias" cmd /k python anomalias.py
timeout /t 1 /nobreak >nul

echo   4/5  Dashboard   (interface web)
start "Dashboard" cmd /k python app.py
timeout /t 3 /nobreak >nul

echo   5/5  Simulador   (publisher_normal — funcionamento normal)
start "Publisher Normal" cmd /k python publisher_normal.py
timeout /t 2 /nobreak >nul

REM ── Abrir o dashboard no browser ────────────────────────────────────
REM Pequena pausa extra para garantir que o Flask ja esta a servir a pagina
echo.
echo A abrir o dashboard no browser...
timeout /t 3 /nobreak >nul
start "" http://localhost:5000

echo.
echo ====================================================================
echo   Todos os processos foram lancados.
echo.
echo   O dashboard foi aberto no browser:
echo       http://localhost:5000
echo   (se nao abriu, abre esse endereco manualmente)
echo.
echo   Para PARAR a simulacao: fecha cada uma das janelas abertas
echo   (ou carrega Ctrl+C dentro de cada uma).
echo ====================================================================
echo.
echo   Esta janela pode ser fechada.
pause
