# Secu Deck Bots — Claude 작업 가이드

## 진실의 원천
- 스테이지 정의·체크리스트: `docs/planning_docs/99_BUILD_ORDER.md`
- 아키텍처 원칙(LLM 라우팅·캐싱·예산): `docs/planning_docs/00_OVERVIEW.md`
- 봇별 빌드 가이드: `docs/planning_docs/02~07_*.md`

## 봇 추가 시 표준 패턴
- 새 봇은 `bots/<name>/`에 생성 — `pyproject.toml` / `Dockerfile` / `railway.toml` / `README.md` / `src/<name>/{__init__,main,commands,ui}.py` 필수
- 모든 봇은 `SecuDeckBot`(packages/core/src/sd_core/discord/base_bot.py) 인스턴스화 — 상속 X, 직접 사용
- LLM 호출은 `bot.llm.call(LLMRequest(...))` 만. anthropic/google-genai/openai SDK 직접 호출 금지
- main.py에서 `_BOT_ROOT = Path(__file__).resolve().parents[2]` 로 sibling 디렉토리(prompts/data/migrations) 접근
- 환경변수: `DISCORD_BOT_TOKEN_<SUFFIX>` + `COST_MONTHLY_LIMIT_KRW_<SUFFIX>` — suffix는 `packages/core/src/sd_core/tracking/cost.py`의 `suffix_map`에 등록
- 새 TaskType 추가 시 `packages/core/src/sd_core/llm/router.py`의 `MODEL_POLICY` 매핑 동시 갱신
- cos 위임 가능한 새 (bot, action) 추가 시 5곳 동시 갱신: 봇 `internal_handlers.py` 핸들러 + 봇 `main.py` 의 `api.register` + cos `intent_router.ROUTABLE_ACTIONS` + cos `synthesizer._ACTION_INTRO` + cos `delegator._build_payload` 액션 분기
- 모든 봇 main.py 는 `await bot.start_with_backoff(token)` 사용 — 직접 `bot.start()` 금지. 부팅 단계 Discord 429 시 컨테이너 안에서 60초 sleep 으로 Railway 재시작 폭주 차단 (base_bot 헬퍼)
- 슬래시 전용 봇은 base_bot 기본 intents 그대로 — Privileged Intent (`message_content` 등) 가 필요한 봇만 main.py 에서 `intents = discord.Intents.default(); intents.message_content = True` 구성 후 `SecuDeckBot(intents=...)` 주입. base_bot 기본은 OFF (Developer Portal 미활성화 시 부팅 실패 방지)
- cos 가 다른 봇 호출 시 base URL 은 `BOT_URL_<SUFFIX>` 환경변수 (suffix 는 cost.py 와 동일) — `INTERNAL_API_SECRET` 은 5봇 공통값

## 자주 밟는 함정
- YAML sequence에서 `- "문구" (괄호 주석)` 형식은 파싱 에러 — 주석은 따옴표 안에 넣거나 별도 키로 분리
- Sonnet의 JSON 응답이 ```json 코드블록에 감싸일 수 있음 — 파싱 전 codeblock 제거 + 첫 `{`/마지막 `}` 추출 폴백 필수 (예: `interview_logger._safe_json_parse`)
- Anthropic prompt caching은 system 프롬프트 ≥ ~200자일 때만 자동 적용 — 짧으면 베이스 프롬프트·DS 카탈로그·Argos 컨텍스트와 합쳐 길이 확보
- YAML/프롬프트는 mtime 감지로 봇 재시작 없이 재로드되도록 작성 (`ArgosContext`, `_HypothesisRepo`, `DesignSystem` 참고)
- Postgres 의존 코드는 항상 `DATABASE_URL` 없을 때 in-memory 폴백 — 봇은 부팅 가능해야 함
- discord.py 2.x 의 `bot.add_cog()` 는 awaitable — Cog 를 쓰는 install_commands 는 `async def`, `bot.tree.add_command` 만 쓰는 헬퍼는 동기여도 됨
- 라우팅·인트로처럼 결과가 정적 텍스트인 경로는 LLM 호출 금지 — 카탈로그 기반 템플릿이 비용·지연 둘 다 유리 (cos `synthesizer.make_delegation_intro` 참고)
- Railway 는 한 푸시에 모노레포 모든 봇 재배포 — 한 봇 crash-loop 가 같은 클러스터 다른 봇들의 Discord 글로벌 429 까지 동시에 끌어올림. 사고 발견 시 영향 봇을 먼저 Pause 해 재시작 폭주를 끊을 것

## 검증
- uv 미설치 환경: `python -c "import ast; [ast.parse(open(f).read()) for f in glob('...')]"` 로 syntax 검증
- YAML: `python -X utf8 -c "import yaml; yaml.safe_load(open(p, encoding='utf-8').read())"` (PowerShell 한글 깨짐 회피)
- 봇 main.py 직접 실행 검증은 의존 SDK 모두 필요해 비추천 — AST + YAML 검증만으로 충분

## Windows / PowerShell 메모
- 한글 출력 깨질 때 `python -X utf8`
- 새 파일 생성 시 git이 LF→CRLF 경고 — 무해, 무시

## 커밋
- 워크트리에 무관한 변경(`.env.example` 삭제 등)이 있으면 `git add -A` 대신 작업 파일만 명시 add
- 코어 패키지/봇별로 단일 커밋 (혼합 변경 시 prefix 분리: `feat(core):`, `feat(pitch):` 등)
