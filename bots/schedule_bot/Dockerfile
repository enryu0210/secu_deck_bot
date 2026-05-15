# =====================================================================
# Schedule Bot — Railway 배포용 Dockerfile
# =====================================================================
# SQLite 파일 영속을 위해 Railway Volume 을 /app/data 에 마운트 권장.
# (SCHEDULE_DB_PATH=/app/data/schedules.db)

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv==0.4.30

COPY pyproject.toml uv.lock* ./
COPY packages/core ./packages/core
COPY shared ./shared
COPY bots/schedule_bot ./bots/schedule_bot

WORKDIR /app/bots/schedule_bot
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "schedule_bot.main"]
