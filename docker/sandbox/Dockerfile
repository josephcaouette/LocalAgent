# Image for the pipeline's throwaway per-run test containers, and for the dashboard service.
# Rebuild after editing:   cd /mnt/blackboard/docker && docker compose build
# Keep the package list in sync with SANDBOX_PACKAGES in Z:\workspace\config.py.
FROM python:3.11-slim
RUN pip install --no-cache-dir requests redis psutil PyYAML
