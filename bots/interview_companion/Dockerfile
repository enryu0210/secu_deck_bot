# =====================================================================
# Interview Companion — Railway 배포용 Dockerfile
# ---------------------------------------------------------------------
# pitch_sharpener / code_sentinel 와 동일 패턴.
# Railway 의 Watch Paths 를 bots/interview_companion/** + packages/core/**
# 로 잡으면 다른 봇 변경 시 본 봇 재빌드 X.
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
COPY bots/interview_companion ./bots/interview_companion

WORKDIR /app/bots/interview_companion
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "interview_companion.main"]
