@echo off
title Restart Node 3 — The Worker (192.168.254.26)
echo ======================================================
echo    RESTARTING NODE 3 SERVICES (WORKER / OLLAMA)
echo ======================================================

set NODE3_IP=192.168.254.26
set NODE3_USER=server

:: 1. Verify physical host connectivity
echo [*] Pinging Node 3 (%NODE3_IP%)...
ping -n 1 -w 1000 %NODE3_IP% >nul
if %errorlevel% neq 0 (
    echo [!] ERROR: Node 3 is unreachable at %NODE3_IP%. Check laptop power and lid state.
    pause
    exit /b 1
)
echo [+] Node 3 host is reachable.

:: 2. Restart Ollama systemd service. -t gives sudo a terminal so it can ask for your password.
echo [*] Restarting Ollama systemd service (enter your sudo password for %NODE3_USER% if asked)...
ssh -t %NODE3_USER%@%NODE3_IP% "sudo systemctl restart ollama"
if %errorlevel% neq 0 (
    echo [!] The restart command failed; Ollama may still be running the old process.
)

:: 3. Wait for Ollama HTTP API to respond (up to 2 minutes)
echo [*] Waiting for Ollama API to come online on port 11434...
set /a TRIES=0
:wait_ollama
timeout /t 2 /nobreak >nul
set /a TRIES+=1
curl -s --connect-timeout 2 http://%NODE3_IP%:11434/api/tags >nul
if %errorlevel% neq 0 (
    if %TRIES% geq 60 (
        echo [!] Ollama didn't come back within 2 minutes. Check it on Node 3: systemctl status ollama
        pause
        exit /b 1
    )
    echo [...] Waiting for Ollama daemon...
    goto wait_ollama
)
echo [+] Ollama daemon is active!

:: 4. Pre-warm models in RTX 2070 VRAM and keep them loaded: keep_alive -1.
::    The pipeline sends the same keep_alive and num_ctx with every request, so nothing
::    resets the timer or forces a reload. Model names must match WORKER_MODEL and EMBED_MODEL,
::    and num_ctx must match OLLAMA_NUM_CTX, in Z:\workspace\config.py.
echo [*] Pre-warming qwen3.5:9b into VRAM...
curl -s http://%NODE3_IP%:11434/api/generate -d "{\"model\": \"qwen3.5:9b\", \"prompt\": \"warmup\", \"stream\": false, \"think\": false, \"keep_alive\": -1, \"options\": {\"num_ctx\": 8192}}" >nul
echo [+] qwen3.5:9b loaded.

echo [*] Pre-warming qwen3-embedding:0.6b into VRAM...
curl -s http://%NODE3_IP%:11434/api/embed -d "{\"model\": \"qwen3-embedding:0.6b\", \"input\": \"warmup\", \"keep_alive\": -1}" >nul
echo [+] qwen3-embedding:0.6b loaded.

:: 5. Output active model status from Node 3
echo ------------------------------------------------------
echo Active models in RTX 2070 VRAM:
ssh %NODE3_USER%@%NODE3_IP% "ollama ps"
echo ------------------------------------------------------

echo ======================================================
echo    NODE 3 INITIALIZATION COMPLETE
echo ======================================================
timeout /t 5
exit /b 0
