# =====================================================================
# Pitch Sharpener — Railway 배포용 Dockerfile
# ---------------------------------------------------------------------
# 모노레포라 워크스페이스 루트의 packages/core 를 함께 복사.
# Railway 의 Watch Paths 설정으로 빌드 트리거를 봇 단위로 분리하면
# 다른 봇 변경 시 본 봇이 재빌드되지 않는다.
# =====================================================================

FROM python:3.12-slim

# 시스템 패키지 (PDF 파싱·빌드 도구)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# uv 설치
RUN pip install --no-cache-dir uv==0.4.30

# 워크스페이스 메타 + 코어
COPY pyproject.toml uv.lock* ./
COPY packages/core ./packages/core
COPY shared ./shared

# 봇 본체 복사
COPY bots/pitch_sharpener ./bots/pitch_sharpener

# 봇 디렉토리에서 install. --frozen 은 uv.lock 이 있을 때만 의미 있음.
WORKDIR /app/bots/pitch_sharpener
RUN uv sync --no-dev

# 봇은 stdout 으로 로그 출력만 하면 충분 (헬스체크 endpoint 없음)
CMD ["uv", "run", "python", "-m", "pitch_sharpener.main"]
