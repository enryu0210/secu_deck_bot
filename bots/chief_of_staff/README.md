# Chief of Staff (cos) — Phase 3 라우팅 모드

> **미션**: 5봇 단일 진입점. 사용자가 "어느 봇한테 물어보지?" 고민 안 해도 되게.

## 사용

디스코드 채널에서 멘션:

```
@cos 사업계획서 § 3.2 부분만 다시 봐줘  (텍스트 첨부)
@cos 이 함수 PII 처리 안전한지 봐줘     (코드 첨부)
@cos 이 화면 spec 만들어줘              (이미지 첨부)
@cos 우리 인터뷰 7건에서 가장 빈번한 페인 뭐야?
```

cos 는 의도를 분류해 적절한 봇으로 위임하고, 결과를 자기 스타일로 포장해 답한다.

`/council` 슬래시 커맨드는 Phase 5 (Council 모드) 에서 활성화.

## 아키텍처

```
사용자 메시지
    ↓
@cos 멘션 감지 (commands.py)
    ↓
IntentRouter.classify (Haiku 의도 분류 + 룰 1차)
    ↓
Delegator.invoke   ──HTTP──▶  봇 internal API (/api/invoke)
    ↓
Synthesizer.wrap (cos 톤으로 포장)
    ↓
Discord 임베드 응답
```

cos 자체는 외부 HTTP 서버를 띄우지 않는다. 디스코드 게이트웨이만 연결.

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `DISCORD_BOT_TOKEN_COS` | ✅ | cos 봇 토큰 |
| `ANTHROPIC_API_KEY` | ✅ | Haiku 의도 분류 + Sonnet self 답변 |
| `INTERNAL_API_SECRET` | ✅ | 4봇과 공유. 일치해야 invoke 허용 |
| `BOT_URL_PITCH` | ✅ | `http://pitch-sharpener.railway.internal:8080` |
| `BOT_URL_CODE` | ✅ | code_sentinel internal URL |
| `BOT_URL_INTERVIEW` | ✅ | interview_companion internal URL |
| `BOT_URL_DESIGN` | ✅ | design_echo internal URL |
| `BOT_URL_AUDIT` | ⛔ | argos_self_audit (Stage 6 도입 후) |
| `DISCORD_GUILD_ID` | 선택 | 개발 중 길드 동기화 |
| `COST_MONTHLY_LIMIT_KRW_COS` | 선택 | 기본 30000 |

## 비용

| 동작 | 모델 | 1회 |
|---|---|---|
| 의도 분류 | Haiku | 약 30원 |
| self 답변 | Sonnet | 약 200원 |
| 위임 | (해당 봇 비용) | — |

cos 자체 한도는 30,000원/월로 충분. 위임으로 발생하는 비용은 각 봇의 한도에 누적.

## 로컬 실행

```bash
cd bots/chief_of_staff
uv sync
uv run python -m chief_of_staff.main
```

`.env` 에 위 환경변수 설정 후 실행. 4봇이 같은 머신에서 떠 있어야 invoke 가 동작 (`BOT_URL_*` 를 `http://localhost:<port>` 로).
