# 06. Chief of Staff — 메타봇 (라우팅 → Council 진화)

> **Phase**: 3 (라우팅) → 5 (Council 모드)
> **주 사용자**: 전원 (진입점)
> **모델**: Claude Sonnet 4.5 (라우팅·종합), Claude Haiku 4.5 (의도 분류)
> **예산**: 월 30,000원 (Phase 3 라우팅 모드만), Council 도입 시 추가 50,000원
> **빌드 기간 추정**: Phase 3 라우팅 4~5일, Phase 5 Council 7~10일

---

## 🎯 미션

Phase 3에서는 **5봇의 단일 진입점** 역할. 사용자가 "어느 봇한테 물어보지?" 고민 안 해도 됨.
Phase 5에서는 **5봇 자율 협업 카운슬** 의장. 복잡한 의사결정 안건을 받아 여러 봇을 소집해 토론.

이 봇은 **두 단계로 진화**한다:

```
Phase 3 (단순 라우팅)        Phase 5 (Council 모드)
───────────────────         ──────────────────────
사용자 → @cos 질문            사용자 → @cos 회의 안건
         ↓                            ↓
       의도 분류                   안건 분석
         ↓                            ↓
       해당 봇으로 위임             5봇 소집·토론·종합
```

---

# 🔵 Phase 3 — 라우팅 모드

## 시나리오

```
대표: @cos 사업계획서 § 3.2 부분만 다시 봐줘

cos:  🎯 Pitch Sharpener의 Customer Voice 페르소나로 연결합니다.
      [Pitch Sharpener 호출 → 결과 전달]

———

개발자: @cos 이 함수에 PII 처리 안전한지 봐줘
       [코드 첨부]

cos:   💻 Code Sentinel(security focus)로 연결합니다.
       [Code Sentinel 호출 → 결과 전달]

———

디자이너: @cos 이 화면 spec 만들어줘
        [이미지]

cos:   🎨 Design Echo로 연결합니다.
       [Design Echo 호출 → 결과 전달]

———

대표: @cos 다음 인터뷰는 누구 잡아야 효과적일까?

cos:  🎙 Interview Companion으로 연결합니다.
      [Interview Companion에 누적 분석 → 답변]
```

## 빌드 스펙

### 라우터 로직

```python
class IntentRouter:
    INTENT_BOT_MAPPING = {
        "pitch_review": "pitch_sharpener",
        "code_review": "code_sentinel",
        "test_generation": "code_sentinel",
        "kisa_check": "code_sentinel",
        "interview_prep": "interview_companion",
        "interview_log": "interview_companion",
        "interview_insight": "interview_companion",
        "design_check": "design_echo",
        "design_spec": "design_echo",
        "copy_review": "design_echo",
        "audit_scan": "argos_self_audit",
        "general_question": "self",  # cos 자체가 답변
    }

    async def classify(self, user_message: str, attachments: list) -> Intent:
        """Haiku로 빠르게 의도 분류 (저비용)"""
        request = LLMRequest(
            task_type=TaskType.ROUTING,
            system=ROUTING_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            user_id=...,
            bot_name="chief_of_staff",
            max_tokens=200,
        )
        response = await self.llm.call(request)
        return self._parse_intent(response)
```

### 봇 간 통신

봇이 **별도 Railway 서비스**라 직접 함수 호출 불가. 두 가지 옵션:

**옵션 A: HTTP 내부 API (권장)**
각 봇이 `/api/invoke` 엔드포인트 노출. cos가 HTTP로 호출.

```python
# 각 봇에 추가
from fastapi import FastAPI

api = FastAPI()

@api.post("/api/invoke")
async def invoke(request: InvokeRequest):
    """다른 봇에서 호출. 사용자 인증은 공유 시크릿."""
    if request.shared_secret != INTERNAL_SECRET:
        raise HTTPException(401)
    result = await reviewer.review(...)
    return result.to_dict()
```

**옵션 B: Postgres 큐 (비동기 적합)**
cos가 작업을 큐에 등록 → 해당 봇이 폴링 → 결과 큐에 응답.
복잡하지만 봇 죽었을 때 복구 가능.

> Phase 3에서는 **옵션 A** 권장. 단순함 우선.

### 슬래시 커맨드 + 자연어

```python
class CosCommands(commands.Cog):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # @cos 멘션 감지
        if self.bot.user not in message.mentions:
            return
        if message.author.bot:
            return

        intent = await self.router.classify(message.content, message.attachments)

        if intent.bot == "self":
            # cos 자체 답변 (일반 질문)
            response = await self.handle_directly(message)
        else:
            # 적절한 봇으로 위임
            response = await self.delegate(intent.bot, message)

        await message.reply(embed=response.to_embed())

    @app_commands.command(description="Council 모드 (Phase 5)")
    async def council(self, interaction, topic: str):
        # Phase 5에서 구현
        ...
```

## Phase 3 비용 예산

| 동작 | 모델 | 비용 |
|---|---|---|
| 의도 분류 | Haiku | 약 30원/회 |
| 위임 (해당 봇 비용) | 봇별 다름 | — |
| 일반 답변 (self) | Sonnet | 약 200원/회 |

월 사용량: 라우팅 200회 × 30원 + 일반 답변 50회 × 200원 = 약 16,000원
+ 위임에 따른 봇별 비용 추가 발생. → cos 자체는 한도 30,000원 충분.

---

# 🟣 Phase 5 — Council 모드

> **전제**: Phase 1~4가 안정 가동 중. 5봇 모두 정상 동작. 10월 출시 후 안정기 진입.

## 시나리오

```
대표: /council
      안건: SSO 기능 추가 vs 시정 조치 보고서 자동 생성, 어느 게 우선?

cos:  🏛 Council #001 시작합니다.

      [참석자 결정]
      안건 분석: 기능 우선순위, 자원 배분 → 주제 다양
      소집: PM, CEO, CCO, QA 시뮬레이터

      [스레드 생성: "🏛 Council #001 — SSO vs 보고서 자동화"]

      ——— [스레드 내부 대화] ———

      [PM]
      범위 비교부터.
      • SSO: 엔터프라이즈 영업 차단 해소, 6주 추정
      • 보고서 자동화: 7건 인터뷰 중 6건 1순위 페인, 4주 추정
      두 안 모두 가치 있으나 동시 진행은 불가.

      [CCO]
      고객 데이터 무게: 보고서 자동화 우세.
      인터뷰 6/7 vs 엔터프라이즈 가설 검증 부족.
      현재 단계에선 기존 고객 신뢰가 더 중요.

      [CEO]
      @PM SSO가 막은 엔터프라이즈 딜의 ARR 규모는?
      그것 없이 6개월 살 수 있나?

      [PM]
      현재 SSO 막힌 딜 2건, 합산 ARR 기대 4,000만원.
      당장의 현금 의존도는 낮음. 6개월 생존 가능.

      [QA]
      보고서 자동화의 위협 모델 우려:
      자동 생성된 보고서가 위탁자 측에 잘못된 정보 전달 시
      Argos 책임 범위 모호. PRD에 disclaimer·검수 단계 필수.

      [CCO]
      @QA 동의. 사람 검수 단계 필수 조건으로 명시 필요.

      [PM]
      @CEO @CCO 합의 흐름 보임. SSO는 7월 이후로 미루고
      보고서 자동화 → P0, 4주 일정.

      [CEO]
      좋습니다. 단, 7월 SSO 미룰 때 영향 받는 딜 2건에는
      개별 커뮤니케이션 + 8월 일정 약속.

      ——— [스레드 종료] ———

cos:  📋 Council #001 결론

      합의 사항:
      • 우선순위 P0: 시정 조치 보고서 자동 생성 (4주)
      • SSO: 7월 이후 (또는 8월)
      • 조건: 자동 보고서에 사람 검수 단계 필수

      Action Items:
      1. PRD 작성 (보고서 자동화) — 대표
      2. SSO 대기 딜 2건 커뮤니케이션 — 대표
      3. QA: 위협 모델 보고서 자동화 영역 보강

      ⚠️ 이 결론은 시뮬레이션입니다.
         실제 결정은 팀 회의로 확정하세요.
```

## Phase 5 빌드 스펙

### LangGraph 기반 워크플로우

```python
from langgraph.graph import StateGraph, END

class CouncilState(TypedDict):
    topic: str
    participants: list[str]
    transcript: list[Statement]
    round: int
    max_rounds: int
    speaking_rights: dict[str, float]  # 봇별 발언 점수
    converged: bool
    final_synthesis: str | None

def build_council_graph():
    g = StateGraph(CouncilState)

    g.add_node("setup", setup_council)         # 참석자 결정
    g.add_node("score_speaking", score_round)  # 봇별 발언 점수
    g.add_node("speak", emit_statements)       # 점수 임계값 이상 봇 발언
    g.add_node("check_converge", check_convergence)
    g.add_node("synthesize", synthesize_final)

    g.set_entry_point("setup")
    g.add_edge("setup", "score_speaking")
    g.add_edge("score_speaking", "speak")
    g.add_conditional_edges(
        "speak",
        check_continue,
        {
            "continue": "score_speaking",
            "converged": "synthesize",
        }
    )
    g.add_edge("synthesize", END)

    return g.compile()
```

### 발언권 알고리즘

```python
class SpeakingRightCalculator:
    async def score(
        self,
        bot_persona: Persona,
        topic: str,
        transcript: list[Statement],
    ) -> SpeakingScore:
        """
        각 봇이 매 라운드마다 자기 점수를 계산:
        - 안건 적합성 (0-10): 내 영역에 가까운가
        - 시급성 (0-10): 지금 발언이 필요한가
        - 호명됨 (boolean): @멘션됐으면 무조건 발언

        합계 12+ 또는 호명 시 발언.
        """
        request = LLMRequest(
            task_type=TaskType.ROUTING,
            system=f"You are {bot_persona.name}. Score your urgency to speak.",
            messages=[{"role": "user", "content": f"Topic: {topic}\nTranscript: {transcript}"}],
            ...
            max_tokens=100,
        )
        ...
```

### 종료 조건

```python
class ConvergenceChecker:
    def is_converged(self, state: CouncilState) -> bool:
        # 1. 하드 리밋
        if state["round"] >= state["max_rounds"]:  # 5
            return True
        if len(state["transcript"]) >= 15:
            return True

        # 2. 합의 종료 (마지막 2발언이 동의 톤)
        if self._is_agreement_tone(state["transcript"][-2:]):
            return True

        # 3. 수렴 종료 (반복 의견)
        if self._is_repetitive(state["transcript"][-3:]):
            return True

        return False
```

### Council 비용 예산

| 단계 | 모델 | 1회 비용 |
|---|---|---|
| 안건 분석·참석자 결정 | Sonnet | 약 400원 |
| 봇별 발언권 점수 (라운드당 5봇) | Haiku × 5 | 약 150원 |
| 봇 발언 (라운드당 평균 3봇) | Sonnet × 3 | 약 1,500원 |
| 평균 4 라운드 | | 약 6,600원 |
| 종합 | Sonnet | 약 800원 |
| **총 1회 Council** | | **약 7,000~10,000원** |

월 사용 시뮬레이션: 5~8회 Council = 35,000~80,000원.
→ 따로 한도 50,000원 배정. 풀 카운슬은 **주 1~2회**로 제한 권장.

---

## ⚠️ Phase 5 주의사항

### 1. "회의처럼 보이지만 회의가 아니다"
봇들이 토론하면 사람들이 결론을 진지하게 받아들임. 마지막에 항상:
"이 결론은 시뮬레이션입니다. 실제 결정은 팀 회의로 확정하세요."

### 2. 페르소나 일관성
같은 봇이 회의마다 다른 가치관으로 말하면 시뮬레이터로서 가치 0.
→ 페르소나 카드(`personas/*.yaml`)를 시스템 프롬프트에 매번 포함.
→ 봇별 "장기 메모" (이전 회의에서 한 발언)를 Postgres에 저장해 일관성 유지.

### 3. 무한 루프 위험
LangGraph 노드 실행 횟수 하드캡. 토큰 예산 초과 시 강제 종료 후 현재까지로 종합.

### 4. 비용 폭발
Council 1회 = 일반 질의 50회 비용. **`/council` 커맨드는 명시적 호출만**, `@cos` 멘션으로는 절대 트리거되지 않게.

---

## ✅ Phase 3 완료 체크리스트

- [ ] `IntentRouter` 의도 분류 정확도 90% 이상 (50개 테스트 메시지)
- [ ] 5개 봇에 `/api/invoke` 엔드포인트 추가
- [ ] 공유 시크릿 인증 동작
- [ ] cos가 5개 봇 모두 호출 가능
- [ ] 봇 응답 cos에서 적절한 임베드로 표시
- [ ] 일반 질문(self) cos가 직접 답변
- [ ] 응답 시간: 라우팅 < 5초, 위임 + 봇 응답 < 1분

## ✅ Phase 5 완료 체크리스트

- [ ] LangGraph 워크플로우 정상 실행
- [ ] 발언권 알고리즘: 봇이 적절히 발언/침묵
- [ ] 종료 조건 3종 모두 동작 (하드/합의/수렴)
- [ ] 페르소나 일관성: 같은 봇 5회 회의 결과 가치관 비교 시 안정
- [ ] Council 1회 비용 < 10,000원 실측
- [ ] 사용자가 `/council end`로 강제 종료 가능
- [ ] 결론에 면책 항상 포함

---

다음 문서: `07_ARGOS_SELF_AUDIT.md`
