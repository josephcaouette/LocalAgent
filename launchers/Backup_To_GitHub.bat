@echo off
setlocal
title Backup Cluster to GitHub
echo ======================================================
echo          BACKING UP THE CLUSTER TO GITHUB
echo ======================================================
set NODE2=server@192.168.254.25

:: 1. Copy the Desktop launchers and the WSL settings onto Node 2 so they are backed up too.
::    Uses scp, so it works even when the Z: drive isn't connected.
echo [*] Copying launchers to Node 2...
scp -q -o BatchMode=yes "%~dp0Launch_GUI.bat" "%~dp0Reset_Cluster.bat" "%~dp0Restart_Node2_Blackboard.bat" "%~dp0Restart_Node3_Worker.bat" "%~dp0Backup_To_GitHub.bat" %NODE2%:/mnt/blackboard/launchers/
scp -q -o BatchMode=yes "%USERPROFILE%\.wslconfig" %NODE2%:/mnt/blackboard/launchers/wslconfig.txt
:: The Agent Cluster window's code and settings live on C: so it works without Z:; back them up too.
ssh -o BatchMode=yes %NODE2% "mkdir -p /mnt/blackboard/launchers/cluster_launcher"
scp -q -o BatchMode=yes "C:\AI\cluster_launcher\cluster_launcher.py" "C:\AI\cluster_launcher\launcher_settings.json" %NODE2%:/mnt/blackboard/launchers/cluster_launcher/
:: The cluster-ops skill (Claude Code instructions and test scripts for this cluster).
if exist "%USERPROFILE%\.claude\skills\cluster-ops\SKILL.md" scp -q -r -o BatchMode=yes "%USERPROFILE%\.claude\skills\cluster-ops" %NODE2%:/mnt/blackboard/launchers/

:: 2. First run only: ask which GitHub repository to back up to.
set "REPO_URL="
ssh -o BatchMode=yes %NODE2% "git -C /mnt/blackboard remote get-url origin" >nul 2>&1
if errorlevel 1 (
    echo.
    echo First-time setup. Paste the address of your private GitHub repository,
    echo for example https://github.com/yourname/agent-cluster
    set /p REPO_URL=Repository address:
)

:: 3. Export memory, commit and push. This part runs on Node 2.
echo [*] Committing and pushing on Node 2...
ssh -o BatchMode=yes %NODE2% "bash /mnt/blackboard/launchers/backup_node2.sh %REPO_URL%"
echo.
pause
