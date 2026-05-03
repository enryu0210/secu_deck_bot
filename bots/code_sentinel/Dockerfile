# =====================================================================
# Code Sentinel — Railway 배포용 Dockerfile
# =====================================================================

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv==0.4.30

COPY pyproject.toml uv.lock* ./
COPY packages/core ./packages/core
COPY shared ./shared
COPY bots/code_sentinel ./bots/code_sentinel

WORKDIR /app/bots/code_sentinel
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "code_sentinel.main"]
