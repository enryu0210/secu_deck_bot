# 01. Infrastructure — 모노레포 · packages/core · Railway 배포

> **목표**: 모든 봇이 공유할 코어 인프라 구축. 이 단계가 끝나면 새 봇 추가는 1~2일이면 가능.

---

## 1️⃣ 모노레포 구조

```
secu-deck-bots/
├── pyproject.toml                  # uv workspace 루트
├── uv.lock
├── .env.example
├── .gitignore
├── README.md
│
├── packages/
│   └── core/
│       ├── pyproject.toml
│       └── src/sd_core/
│           ├── __init__.py
│           ├── llm/
│           │   ├── __init__.py
│           │   ├── router.py        # 모델 선택·폴백·캐싱
│           │   ├── claude.py        # Anthropic 어댑터
│           │   ├── gemini.py        # Google 어댑터
│           │   ├── openai.py        # OpenAI 어댑터
│           │   └── types.py         # 공통 타입 (Message, ModelChoice 등)
│           ├── discord/
│           │   ├── __init__.py
│           │   ├── base_bot.py      # 모든 봇의 베이스 클래스
│           │   ├── ui.py            # 임베드·버튼·View 헬퍼
│           │   └── thread.py        # 스레드 생성·관리
│           ├── personas/
│           │   ├── __init__.py
│           │   ├── loader.py        # YAML 로더
│           │   └── base.py          # Persona 데이터클래스
│           ├── context/
│           │   ├── __init__.py
│           │   └── argos.py         # Argos_Context.md 로더 + 캐싱
│           ├── tracking/
│           │   ├── __init__.py
│           │   ├── cost.py          # 비용 추적
│           │   └── usage.py         # 사용자별 쿼터
│           ├── storage/
│           │   ├── __init__.py
│           │   └── postgres.py      # Postgres 연결 (Phase 2부터)
│           └── utils/
│               ├── __init__.py
│               ├── logger.py        # 구조화 로깅
│               └── errors.py        # 공통 예외
│
├── bots/
│   ├── pitch_sharpener/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── railway.toml
│   │   ├── personas/                # 봇 고유 페르소나
│   │   └── src/pitch_sharpener/
│   │       ├── main.py              # discord 엔트리
│   │       ├── commands.py
│   │       └── review_engine.py
│   ├── code_sentinel/
│   ├── interview_companion/
│   ├── design_echo/
│   ├── chief_of_staff/
│   └── argos_self_audit/
│
├── shared/
│   └── argos_context/
│       └── Argos_Context.md         # 모든 봇이 참조 (심볼릭 링크 또는 복사)
│
└── docs/
    ├── architecture.md
    ├── adding_new_bot.md
    └── prompt_caching_strategy.md
```

---

## 2️⃣ pyproject.toml (워크스페이스 루트)

```toml
[project]
name = "secu-deck-bots"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["packages/*", "bots/*"]

[tool.uv.sources]
sd-core = { workspace = true }
```

각 봇의 `pyproject.toml`에서 `sd-core`를 워크스페이스 의존성으로 가져옴:

```toml
# bots/pitch_sharpener/pyproject.toml
[project]
name = "pitch-sharpener"
version = "0.1.0"
dependencies = [
    "sd-core",
    "discord.py>=2.4",
    "anthropic>=0.40",
    "python-dotenv",
]
```

---

## 3️⃣ `packages/core` 핵심 모듈

### 3.1 `sd_core/llm/router.py` — 라우팅의 핵심

**책임**:
- 작업 유형별 적합 모델 선택
- 1순위 모델 실패 시 폴백
- Anthropic Prompt Caching 자동 적용
- 호출마다 비용 기록 (cost.py)
- 사용자 쿼터 체크 (usage.py)

```python
# 핵심 인터페이스 (구현은 Claude Code가 작성)
from dataclasses import dataclass
from enum import Enum

class TaskType(str, Enum):
    KOREAN_WRITING = "korean_writing"        # 사업계획서 등
    CODE_REVIEW_SIMPLE = "code_review_simple"
    CODE_REVIEW_COMPLEX = "code_review_complex"
    VISION_DESIGN = "vision_design"
    LARGE_CONTEXT = "large_context"           # 인터뷰 누적
    INSIGHT_EXTRACTION = "insight_extraction"
    ROUTING = "routing"                       # 단순 분류

@dataclass
class LLMRequest:
    task_type: TaskType
    system: str                  # 캐시 대상 (Argos 컨텍스트 등)
    messages: list[dict]
    user_id: str                 # 쿼터 체크용
    bot_name: str                # 비용 추적용
    max_tokens: int = 1024
    temperature: float = 0.7
    images: list[bytes] | None = None

@dataclass
class LLMResponse:
    text: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_krw: float
    fallback_triggered: bool = False

class LLMRouter:
    async def call(self, request: LLMRequest) -> LLMResponse:
        ...
```

**모델 매핑 (router 내부 정책)**:

```python
MODEL_POLICY = {
    TaskType.KOREAN_WRITING: [
        ("anthropic", "claude-sonnet-4-5"),
        ("anthropic", "claude-opus-4-5"),  # fallback
    ],
    TaskType.CODE_REVIEW_SIMPLE: [
        ("anthropic", "claude-haiku-4-5"),
        ("anthropic", "claude-sonnet-4-5"),
    ],
    TaskType.CODE_REVIEW_COMPLEX: [
        ("anthropic", "claude-sonnet-4-5"),
    ],
    TaskType.VISION_DESIGN: [
        ("google", "gemini-2.5-flash"),
        ("anthropic", "claude-sonnet-4-5"),
    ],
    TaskType.LARGE_CONTEXT: [
        ("google", "gemini-2.5-flash"),
        ("google", "gemini-2.5-pro"),
    ],
    TaskType.INSIGHT_EXTRACTION: [
        ("anthropic", "claude-sonnet-4-5"),
    ],
    TaskType.ROUTING: [
        ("anthropic", "claude-haiku-4-5"),
        ("openai", "gpt-4.1-mini"),
    ],
}
```

> **중요**: 위 모델 ID는 2026.04 기준 추정. 빌드 시 각 SDK 문서에서 최신 ID로 검증할 것. `anthropic` SDK는 `client.messages.create(model=...)` 호출 전 `client.models.list()`로 검증 가능.

### 3.2 `sd_core/llm/claude.py` — Prompt Caching 핵심

```python
# 핵심 패턴 (의사 코드)
async def call_claude(model: str, system: str, messages: list, **kwargs):
    response = await client.messages.create(
        model=model,
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"}  # 5분 TTL 캐시
            }
        ],
        messages=messages,
        **kwargs
    )
    # response.usage.cache_read_input_tokens 로 캐시 적중 확인
    return response
```

**캐싱 전략**:
- Argos 컨텍스트(약 5,000~10,000 토큰) → 항상 캐시
- 페르소나 카드 → 캐시
- 사용자 메시지 → 캐시 X

### 3.3 `sd_core/context/argos.py` — Argos 컨텍스트 로더

```python
# 핵심 인터페이스
class ArgosContext:
    def __init__(self, path: str = "shared/argos_context/Argos_Context.md"):
        self._path = path
        self._cache: str | None = None
        self._mtime: float | None = None

    def get_full(self) -> str:
        """전체 문서 (자주 안 씀)"""
        ...

    def get_section(self, section_id: str) -> str:
        """특정 섹션만 (예: '제품_핵심_기능', '보안_이슈_요약')"""
        ...

    def get_summary(self, max_tokens: int = 2000) -> str:
        """봇 시스템 프롬프트용 요약 (자주 씀)"""
        ...
```

**중요**: 파일 mtime 추적해서 변경 시 자동 재로드. 봇 재시작 없이 컨텍스트 업데이트 가능.

### 3.4 `sd_core/discord/base_bot.py` — 봇 베이스

```python
import discord
from discord.ext import commands
from sd_core.llm.router import LLMRouter
from sd_core.context.argos import ArgosContext
from sd_core.tracking.cost import CostTracker

class SecuDeckBot(commands.Bot):
    def __init__(self, bot_name: str, *args, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents, *args, **kwargs)

        self.bot_name = bot_name
        self.llm = LLMRouter()
        self.argos = ArgosContext()
        self.cost = CostTracker(bot_name=bot_name)

    async def on_ready(self):
        # 글로벌 슬래시 커맨드 동기화
        await self.tree.sync()
        ...

    async def on_app_command_error(self, interaction, error):
        # 공통 에러 핸들링
        ...
```

### 3.5 `sd_core/personas/loader.py` — 페르소나 시스템

```yaml
# 예시: bots/pitch_sharpener/personas/customer_voice.yaml
id: customer_voice
name: Customer Voice
emoji: 🎤
title: 고객 검증 심사위원

core_lens: 고객 인터뷰·실증 데이터의 부재를 본다

priorities_in_order:
  - 가설마다 인터뷰 인용이 있는가
  - 직접 인용 가능한 발언이 있는가
  - 표본 수가 의미 있는가
  - 부정 사례·반례를 다뤘는가

speaking_style:
  tone: 차분하고 단호
  length: 3-5문장
  signature_questions:
    - "이 가설을 뒷받침할 인터뷰가 몇 건인가요?"
    - "직접 인용할 수 있는 발언이 있나요?"

forbidden:
  - 추상적 칭찬
  - 인터뷰 없이 추측으로 보강하는 것
```

```python
# loader.py 인터페이스
@dataclass
class Persona:
    id: str
    name: str
    emoji: str
    title: str
    core_lens: str
    priorities: list[str]
    speaking_style: dict
    forbidden: list[str]

    def to_system_prompt(self) -> str:
        """페르소나를 LLM 시스템 프롬프트로 변환"""
        ...

class PersonaLoader:
    def load(self, persona_id: str, search_paths: list[str]) -> Persona: ...
    def load_all(self, dir_path: str) -> list[Persona]: ...
```

### 3.6 `sd_core/tracking/cost.py` — 비용 추적

```python
# 핵심 기능
class CostTracker:
    def __init__(self, bot_name: str):
        self.bot_name = bot_name

    async def record(
        self,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> float:
        """비용 계산 (KRW) + DB 기록 + 한도 체크. 한도 초과 시 예외 발생."""
        ...

    async def monthly_total(self) -> float:
        """이번 달 봇 총 사용 비용"""
        ...

    async def user_today(self, user_id: str) -> float:
        """사용자 오늘 사용 비용"""
        ...
```

**가격표** (2026.04 기준 추정, 실제 빌드 시 검증):

```python
PRICING_PER_1M_TOKENS_USD = {
    "claude-sonnet-4-5":  {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "claude-haiku-4-5":   {"input": 1.00, "output": 5.00,  "cache_read": 0.10},
    "claude-opus-4-5":    {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "gemini-2.5-flash":   {"input": 0.30, "output": 2.50,  "cache_read": 0.075},
    "gemini-2.5-pro":     {"input": 1.25, "output": 10.00, "cache_read": 0.31},
    "gpt-4.1-mini":       {"input": 0.40, "output": 1.60,  "cache_read": 0.10},
}
USD_TO_KRW = 1380  # 빌드 시점 환율로 업데이트
```

---

## 4️⃣ Dockerfile 템플릿

각 봇 `Dockerfile`은 동일 패턴:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# 워크스페이스 전체 복사 (core 의존성 때문에)
COPY pyproject.toml uv.lock ./
COPY packages/core ./packages/core
COPY bots/pitch_sharpener ./bots/pitch_sharpener
COPY shared ./shared

# 봇 디렉토리에서 install
WORKDIR /app/bots/pitch_sharpener
RUN uv sync --frozen

CMD ["uv", "run", "python", "-m", "pitch_sharpener.main"]
```

> 봇별로 `bots/<bot_name>` 부분만 바꾸면 됨.

---

## 5️⃣ Railway 배포 설정

### 5.1 `railway.toml` (각 봇 디렉토리)

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "bots/pitch_sharpener/Dockerfile"
buildCommand = ""

[deploy]
startCommand = "uv run python -m pitch_sharpener.main"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[deploy.healthcheck]
# 봇은 healthcheck endpoint를 노출하지 않으므로 생략
```

### 5.2 환경 변수 (Railway 대시보드에서 설정)

각 봇 서비스마다:

```
DISCORD_BOT_TOKEN=...                # 봇별 다름
DISCORD_GUILD_ID=...                 # Secu Deck 서버 ID (전 봇 공통)
ANTHROPIC_API_KEY=...                # 전 봇 공통
GOOGLE_API_KEY=...                   # 전 봇 공통
OPENAI_API_KEY=...                   # 전 봇 공통
DATABASE_URL=...                     # Railway Postgres 자동 주입
LOG_LEVEL=INFO
COST_MONTHLY_LIMIT_KRW=50000         # 봇별 다르게 설정
```

### 5.3 Postgres 추가 (Phase 2부터)

Railway 대시보드 → "+ New" → Postgres 추가 → 자동으로 `DATABASE_URL` 주입.
초기 마이그레이션:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS llm_calls (
    id SERIAL PRIMARY KEY,
    bot_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT,
    output_tokens INT,
    cached_tokens INT,
    cost_krw NUMERIC(10, 4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_llm_calls_bot_time ON llm_calls(bot_name, created_at);
CREATE INDEX idx_llm_calls_user_time ON llm_calls(user_id, created_at);
```

---

## 6️⃣ 개발 워크플로우

### 로컬 개발

```bash
# 1. 워크스페이스 install
uv sync

# 2. 특정 봇 실행
cd bots/pitch_sharpener
uv run python -m pitch_sharpener.main

# 3. 코어 변경 후 봇에서 즉시 반영 (workspace 의존성)
# 별도 reinstall 불필요
```

### 테스트

```bash
# 봇별 테스트
uv run pytest bots/pitch_sharpener/tests
# 코어 테스트
uv run pytest packages/core/tests
```

### 배포

Railway는 GitHub 자동 연동. `main` 브랜치 push 시 봇별 서비스가 각자 빌드·재배포.

> **모노레포 빌드 최적화**: Railway가 봇 디렉토리 변경만 감지하도록 `Watch Paths`에 `bots/<bot_name>/**`, `packages/core/**`, `shared/**` 설정.

---

## ✅ 인프라 완료 체크리스트

Claude Code가 이 단계 완료 시 확인할 것:

- [ ] uv workspace 구성됨, `uv sync` 성공
- [ ] `packages/core/src/sd_core` 모든 모듈 import 가능
- [ ] `LLMRouter` 단위 테스트 통과 (mock 기반)
- [ ] `ArgosContext.get_summary()` 호출 시 정상 반환
- [ ] `PersonaLoader.load()` YAML 파싱 정상
- [ ] Dockerfile로 빌드 성공
- [ ] Railway에 더미 봇 1개 배포되어 "Bot online" 메시지 출력 확인
- [ ] Postgres 마이그레이션 적용, `llm_calls` 테이블 존재

---

다음 문서: `02_PITCH_SHARPENER.md`
