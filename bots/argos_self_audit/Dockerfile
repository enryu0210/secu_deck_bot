# =====================================================================
# Argos Self-Audit — Railway 배포용 Dockerfile
# =====================================================================
# 옵션 B (LLM 0회) 라 anthropic SDK 미설치, 대신 git CLI 가 필요해서
# `git` 패키지를 추가로 설치한다 — repo_scanner 가 ARGOS_REPO_URL 을
# 매 일일 스캔 직전에 clone/pull 하기 때문.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv==0.4.30

COPY pyproject.toml uv.lock* ./
COPY packages/core ./packages/core
COPY shared ./shared
COPY bots/argos_self_audit ./bots/argos_self_audit

WORKDIR /app/bots/argos_self_audit
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "argos_self_audit.main"]
