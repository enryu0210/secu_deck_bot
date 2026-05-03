# =====================================================================
# Design Echo — Railway 배포용 Dockerfile
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
COPY bots/design_echo ./bots/design_echo

WORKDIR /app/bots/design_echo
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "design_echo.main"]
