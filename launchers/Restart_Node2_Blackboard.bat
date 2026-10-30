@echo off
title Restart Node 2 — The Blackboard (192.168.254.25)
echo ======================================================
echo    RESTARTING NODE 2 SERVICES (BLACKBOARD / DOCKER)
echo ======================================================

set NODE2_IP=192.168.254.25
set NODE2_USER=server

:: 1. Verify physical host connectivity
echo [*] Pinging Node 2 (%NODE2_IP%)...
ping -n 1 -w 1000 %NODE2_IP% >nul
if %errorlevel% neq 0 (
    echo [!] ERROR: Node 2 is unreachable at %NODE2_IP%. Check power and Ethernet.
    pause
    exit /b 1
)
echo [+] Node 2 host is reachable.

:: 2. Restart Docker Compose stack: Redis, Qdrant and the dashboard.
::    The pkill stops a dashboard left over from the old nohup setup, if any.
::    Test runs use throwaway containers, so there is no sandbox service any more.
echo [*] Restarting Docker Compose stack (Redis, Qdrant, Dashboard)...
ssh %NODE2_USER%@%NODE2_IP% "pkill -f '^python3 /mnt/blackboard/workspace/agent_dashboard.py'; cd /mnt/blackboard/docker && docker compose down --remove-orphans && docker compose up -d"
if %errorlevel% neq 0 (
    echo [!] Warning: Docker compose restart encountered an error.
) else (
    echo [+] Docker containers restarted successfully.
)

:: 3. The telemetry dashboard is the "dashboard" service in docker-compose.yml
echo [*] Dashboard container status:
ssh %NODE2_USER%@%NODE2_IP% "docker ps --filter name=blackboard-dashboard --format '{{.Names}}: {{.Status}}'"

:: 4. Health check all services
echo [*] Waiting 3 seconds for sockets to bind...
timeout /t 3 /nobreak >nul

echo [*] Probing Qdrant (port 6333)...
curl -s --connect-timeout 2 http://%NODE2_IP%:6333/dashboard >nul
if %errorlevel% equ 0 (echo [+] Qdrant is ONLINE.) else (echo [!] Qdrant failed to respond.)

echo [*] Probing Telemetry Dashboard (port 8080)...
curl -s --connect-timeout 2 http://%NODE2_IP%:8080 >nul
if %errorlevel% equ 0 (echo [+] Dashboard is ONLINE.) else (echo [!] Dashboard failed to respond.)

:: 5. Refresh Windows drive Z: mount
echo [*] Verifying network drive Z: mapping...
if not exist "Z:\" (
    echo [*] Mounting Z: workspace share...
    net use Z: \\%NODE2_IP%\blackboard /persistent:yes 2>nul
)
if exist "Z:\" (
    echo [+] Drive Z: is connected.
) else (
    echo [!] Warning: Drive Z: could not be mounted. Check Samba service on Node 2.
)

echo ======================================================
echo    NODE 2 INITIALIZATION COMPLETE
echo ======================================================
timeout /t 5
exit /b 0
