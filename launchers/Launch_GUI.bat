@echo off
title Cluster Orchestrator Launcher
echo ======================================================
echo       STARTING CLUSTER AGENT PIPELINE AND GUI
echo ======================================================

:: ---- vLLM settings ----
:: Model: Qwen3.8-27B, Aug 2026, 4-bit build by Red Hat AI. Only 16 of its 64 layers keep a
:: full KV cache, so context is cheap. 16384 leaves room for 3+ requests at once, which best-of-N
:: candidates need (20480 fits but leaves room for only one). Speculative decoding uses the
:: model's own MTP head to draft 2 tokens per step: about 104 tok/s, versus 27 for the old setup.
:: Memory: vLLM refuses to start if free VRAM is below VLLM_GPU_UTIL x 24 GB. WSL leaves about
:: 22.45 GiB free: 0.92 is the tested default, 0.93 is the most that starts. If startup ever reports too little free
:: memory, set VLLM_GPU_UTIL=0.90 and VLLM_CTX=12288.
:: More context instead of speed: remove --no-enable-prefix-caching and both --speculative-config
:: options, then set VLLM_CTX=32768 and VLLM_GPU_UTIL=0.90, for about 55 tok/s.
:: Old model: VLLM_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct-AWQ, VLLM_CTX=12288 and
:: VLLM_EXTRA=--kv-cache-dtype fp8 --attention-backend TRITON_ATTN --max-num-seqs 8
:: FlashInfer cannot build its kernels in this WSL setup because the installed nvcc is too old
:: for one of its flags, so the Triton attention backend is used. It supports the fp8 KV cache.
:: CUDA graphs are on, meaning no --enforce-eager. The first start compiles for a minute or two
:: and later starts reuse the cache. If startup ever fails, add --enforce-eager to VLLM_EXTRA.
set "VLLM_MODEL=RedHatAI/Qwen3.8-27B-INT4"
set "VLLM_CTX=16384"
set "VLLM_GPU_UTIL=0.92"
set "VLLM_EXTRA=--kv-cache-dtype fp8 --attention-backend TRITON_ATTN --max-num-seqs 8 --language-model-only --reasoning-parser qwen3 --no-enable-prefix-caching --speculative-config.method mtp --speculative-config.num_speculative_tokens 2"

:: 1. Check if vLLM API is already running on port 8001
echo [*] Testing vLLM API on port 8001...
curl -s --connect-timeout 2 http://localhost:8001/v1/models | findstr "max_model_len" >nul
if %errorlevel% equ 0 (
    echo [+] vLLM is already active and healthy on port 8001.
    goto launch_gui
)

:: 2. Clean up any orphaned sockets on port 8001 as root before launching
echo [*] Cleaning up any orphaned vLLM processes on port 8001...
wsl -u root bash -c "fuser -k -9 8001/tcp >/dev/null 2>&1; pkill -9 -f vllm >/dev/null 2>&1"

:: 3. Launch vLLM in a dedicated PowerShell window. Output is also saved to ~/vllm_last.log in WSL.
echo [*] Launching vLLM in a dedicated PowerShell window...
start "vLLM Engine - Qwen3.8 27B (RTX 4090)" powershell -NoExit -Command "wsl bash -c 'source ~/vllm_env/bin/activate && env VLLM_USE_FLASHINFER_SAMPLER=0 PYTHONUNBUFFERED=1 vllm serve %VLLM_MODEL% --host 0.0.0.0 --port 8001 --max-model-len %VLLM_CTX% --gpu-memory-utilization %VLLM_GPU_UTIL% %VLLM_EXTRA% 2>&1 | tee ~/vllm_last.log'"

:: 4. Poll until weights are loaded into the RTX 4090, giving up after 15 minutes
echo [*] Waiting for vLLM to finish loading weights into RTX 4090...
set /a WAITED=0
:wait_vllm
timeout /t 5 /nobreak >nul
set /a WAITED+=5
curl -s --connect-timeout 2 http://localhost:8001/v1/models | findstr "max_model_len" >nul
if %errorlevel% equ 0 goto vllm_ready
if %WAITED% geq 900 (
    echo [!] vLLM did not come up within 15 minutes. Check the vLLM window, or ~/vllm_last.log in WSL.
    pause
    exit /b 1
)
echo [...] Still warming up vLLM engine... %WAITED%s
goto wait_vllm
:vllm_ready
echo [+] vLLM is online and ready!

:launch_gui
:: 5. Ensure network drive Z: is mounted
if not exist "Z:\" (
    echo [*] Mounting Z: workspace share from Node 2...
    net use Z: \\192.168.254.25\blackboard /persistent:yes 2>nul
)

:: 6. Launch Agent Control GUI
echo [*] Launching Agent Control GUI...
call "C:\AI\venvs\agent_brain\Scripts\activate.bat"
start "" python "Z:\workspace\agent_gui.py"

exit
