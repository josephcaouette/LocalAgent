@echo off
setlocal EnableDelayedExpansion
title Hard Reset Cluster Pipeline
echo ======================================================
echo       HARD RESETTING CLUSTER PIPELINE AND GUI
echo ======================================================

:: 1. Stop only the agent GUI and pipeline, using the PID files they write.
::    This no longer kills every python.exe on the machine.
echo [*] Stopping the agent GUI and pipeline...
for %%F in ("%TEMP%\agent_gui.pid" "%TEMP%\agent_pipeline.pid") do (
    if exist "%%~F" (
        set "PID="
        set /p PID=<"%%~F"
        if defined PID (
            tasklist /FI "PID eq !PID!" /NH 2>nul | findstr /I "python" >nul
            if !errorlevel! equ 0 (
                echo     Stopping PID !PID!
                taskkill /F /T /PID !PID! >nul 2>&1
            )
        )
        del "%%~F" >nul 2>&1
    )
)

:: 2. Ensure network drive Z: is connected
if not exist "Z:\" (
    echo [*] Mounting Z: workspace share...
    net use Z: \\192.168.254.25\blackboard /persistent:yes 2>nul
)

:: 3. Clear the latest-run record in Redis on Node 2 (.25). Settings come from Z:\workspace\config.py.
echo [*] Clearing active workflow state in Redis...
call "C:\AI\venvs\agent_brain\Scripts\activate.bat"
python -c "import sys; sys.path.insert(0, r'Z:\workspace'); import config; config.get_redis().delete(config.LATEST_KEY); print('[+] Redis keys reset.')" 2>nul

:: 4. Relaunch GUI using whichever launcher exists
echo [*] Relaunching GUI...
if exist "%~dp0Launch_GUI.bat" (
    start "" "%~dp0Launch_GUI.bat"
)

exit
