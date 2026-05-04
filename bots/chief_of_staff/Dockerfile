# =====================================================================
# Chief of Staff — Railway 배포용 Dockerfile (Phase 3 라우팅 모드)
# ---------------------------------------------------------------------
# 모노레포라 워크스페이스 루트의 packages/core 를 함께 복사.
# cos 는 자체적으로 외부 HTTP 서버를 띄우지 않는다 (다른 봇을 *호출* 만 함).
# =====================================================================

FROM python:3.12-slim

WORKDIR /app

# uv 설치
RUN pip install --no-cache-dir uv==0.4.30

# 워크스페이스 메타 + 코어
COPY pyproject.toml uv.lock* ./
COPY packages/core ./packages/core
COPY shared ./shared

# 봇 본체 복사
COPY bots/chief_of_staff ./bots/chief_of_staff

WORKDIR /app/bots/chief_of_staff
RUN uv sync --no-dev

CMD ["uv", "run", "python", "-m", "chief_of_staff.main"]
