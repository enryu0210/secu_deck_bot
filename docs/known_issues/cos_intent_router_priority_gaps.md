# cos `intent_router.py` 룰베이스 우선순위 갭 — 후속 조치 리스트

작성일: 2026-05-15
상태: **분석만 완료, 수정 미적용** (다음 작업 세션에서 처리)
관련 커밋: `a2f6bf1` (`fix(cos): schedule 라우팅 — '등록'이 날짜 패턴에 가려져 search 로 오라우팅되던 갭`)

## 배경

`bots/chief_of_staff/src/chief_of_staff/intent_router.py` 의 `_classify_by_rules` 는 정규식 매치를 위에서 아래로 순차 평가한다. **더 구체적인 의도가 더 일반적인 패턴 뒤에 배치돼 있으면**, 일반 패턴이 먼저 매치돼 잘못된 액션으로 라우팅되는 사고가 반복적으로 발생함.

이번 커밋에서 고친 케이스: `"6월 19일 ... 일정 등록해줘"` 가 `_DATE_KR_RE` 에 먼저 잡혀 `schedule_search` 로 떨어지던 문제. 같은 클래스의 갭을 미리 탐색해 둠.

전체 코드베이스에서 자연어 기반 키워드 분류기는 cos `intent_router.py` 단 하나 (다른 봇은 슬래시 명령 기반). 따라서 이 파일에 집중.

---

## High priority — 사용자 의도와 다른 액션으로 직행하는 케이스

### 1. 코드 첨부 + KISA/컴플라이언스 키워드 → `code_review` (의도는 `code_kisa`)
- **위치**: `intent_router.py:285~307`
- **재현**: 사용자가 `.py` 파일을 첨부하면서 "이 코드 KISA·개인정보보호법 정합성 점검해줘" 라고 보냄.
- **현재 흐름**: 
  - L285 `_KISA_HINTS` 매치 시도 → `has_ext(_CODE_EXTS)` 가 True 라 분기 스킵 (KISA 룰은 코드 첨부 없을 때만)
  - L296 `has_ext(_CODE_EXTS)` 매치 → `code_review` 반환
- **사용자 의도**: `code_sentinel.code_kisa` (KISA 조항 정합성)
- **제안 수정안**: 
  - 코드 첨부 분기 진입 직전(L296 이전)에 `if _KISA_HINTS.search(text)` 별도 분기 추가 → `code_sentinel.code_kisa` 로 라우팅.
  - 또는 `code_review` 의 `params` 에 `focus="kisa"` 옵션을 추가하고 핸들러에서 분기.
  - 단, `code_kisa` 는 카탈로그상 `feature_description` 필수라 코드 첨부 + 이 액션은 어색함 → 차라리 LLM 위임(`return None`)이 안전.
- **우선순위 근거**: KISA 의도가 명백한데 일반 `code_review` 로 가버리면 사용자 컴플라이언스 점검 의도가 무시됨.

### 2. PDF/DOCX 첨부 + 페르소나 ID 명시 → `pitch_quick` (의도는 `pitch_focus`)
- **위치**: `intent_router.py:310~317`
- **재현**: 사용자가 `.pdf` 첨부하면서 "이 사업계획서 `customer_voice` 페르소나로 깊이 봐줘" 라고 보냄.
- **현재 흐름**: 
  - L310 `has_ext(_PITCH_DOC_EXTS)` 매치 → `pitch_quick` 반환 (`confidence=0.6`)
- **사용자 의도**: `pitch_sharpener.pitch_focus` (단일 페르소나 깊이 리뷰)
- **제안 수정안**:
  - 문서 첨부 분기 안에서 페르소나 ID 키워드 (`customer_voice`, `data_skeptic`, `pricing_analyst`, `competitor_hunter`, `tech_differentiator`, `budget_reality`) 매치 시 `pitch_focus` 로 보내고 `params.persona_id` 채움.
  - 또는 "깊이/페르소나/심층" 같은 강한 키워드 검출 시 룰 포기(`return None`)하고 LLM 위임.
- **우선순위 근거**: `confidence=0.6` 으로 낮춰져 있어 cos 가 "맞나요?" 톤으로 안내하긴 하지만, 라우팅 자체가 부정확하면 사용자 경험이 나쁨.

---

## Medium priority — LLM 위임 안전망이 있어 사고 가능성 낮음

### 3. 인터뷰 키워드 + 일정 등록 의도 → 일정 분기 통째 스킵
- **위치**: `intent_router.py:342` (`_SCHEDULE_HINTS.search(text) and not _INTERVIEW_HINTS.search(text)`)
- **재현**: "다음 주 화요일 김OO 고객 인터뷰 일정 잡아줘"
- **현재 흐름**: 
  - `_INTERVIEW_HINTS` 가 `_SCHEDULE_HINTS` 보다 우선 → 일정 분기 통째 스킵
  - L407 `_INTERVIEW_HINTS` 매치 → `return None` → LLM 위임
- **사용자 의도**: `schedule_bot.schedule_register` (일정 등록)
- **잠재 위험**: LLM 이 메시지 톤에 따라 `interview_companion.interview_prep` 으로 보낼 수 있음 (그쪽 액션의 필수 필드 `name/role/company/company_size` 가 모자라 사용자에게 "정보 부족" 안내 → UX 나쁨).
- **제안 수정안**: 
  - "인터뷰 + 일정" 동시 매치 시 LLM 위임은 유지하되, 시스템 프롬프트에서 "일정 키워드가 함께 있으면 schedule_bot 을 우선" 같은 가이드 추가.
  - 또는 룰베이스에서 `_SCHEDULE_REGISTER_HINTS` 매치까지 함께 있으면 인터뷰 무시하고 `schedule_register` LLM 위임.

### 4. 브랜치 SNAPSHOT vs DIFF 키워드 충돌 → SNAPSHOT 우선
- **위치**: `intent_router.py:251~268`
- **재현**: "develop 브랜치 전체 변경사항 리뷰해줘"
- **현재 흐름**: 
  - L251 `_BRANCH_FULL_HINTS` 매치 ("전체") → `code_branch_snapshot` (비용 큼)
  - L260 `_BRANCH_DIFF_HINTS` ("변경사항") 는 평가도 안 됨
- **사용자 의도**: 모호. "전체 변경사항"은 보통 diff 의 모든 파일을 의미할 때가 많음.
- **현재 주석 (L238)**: "명시적 키워드 충돌 시 SNAPSHOT 우선 — 사용자가 명확히 적은 표현이므로." → **의도된 동작이긴 한데**, "전체 변경사항" 같은 모호한 한국어 표현이 비용 큰 snapshot 으로 가버려 예상치 못한 비용 발생 가능.
- **제안 수정안**: 
  - DIFF 키워드와 FULL 키워드가 동시에 매치되면 우선순위를 뒤집어 DIFF 로 (사용자 의도 모호 시 안전·저비용 default).
  - 또는 충돌 시 LLM 위임(`return None`).

### 5. 일정 키워드 + 일반 날짜 표현 → 무조건 `schedule_search`
- **위치**: `intent_router.py:362~390`
- **재현**: "3월 1일 휴일이 일정에 반영되나?" / "12월 31일까지 일정 마이그레이션 가능?"
- **현재 흐름**: `_SCHEDULE_HINTS` ("일정") + `_DATE_KR_RE` ("3월 1일") 매치 → `schedule_search` 로 직행
- **사용자 의도**: 일정 조회가 아닌 일반 질문/메타 질문일 수 있음
- **제안 수정안**: 의도 단어 ("알려줘/뭐 있어/조회/봐줘" 등) 가 함께 있을 때만 `schedule_search` 매핑. 그 외엔 LLM 위임.
- **우선순위 근거**: 룰베이스 한계라 LLM 위임 안전망이 가장 무난.

---

## Low priority — 룰 정확도 개선 여지 (실 사고 보고 없음)

### 6. `_AUDIT_SCAN_HINTS` 의 "전체 점검" 너무 일반적
- **위치**: `intent_router.py:139~142`, 적용은 L223~230
- **재현**: 첨부 없이 "이번 분기 전체 점검 일정 좀 잡자"
- **현재 흐름**: `_AUDIT_SCAN_HINTS` 매치 → 코드/이미지 첨부 없으므로 `argos_self_audit.audit_scan` 으로 직행
- **잠재 위험**: 컨텍스트와 무관한 메시지가 Argos 레포 스캔으로 빠짐. LLM 비용 0 이라 실 비용은 적지만 사용자 혼란.
- **제안 수정안**: "점검" 단독은 약한 신호 → "전체 스캔/repo 스캔/argos 점검" 같이 Argos·repo 컨텍스트가 함께일 때만 매치.

### 7. `_SCHEDULE_TODAY_HINTS` 의 `today` 영문 매치 폭
- **위치**: `intent_router.py:146`
- **재현**: 영문 메시지에서 today 가 일정 의미가 아닌 일반 부사로 쓰일 때.
- **잠재 위험**: 한국어 사용자 위주라 실 사고 가능성 낮음.
- **제안 수정안**: 보류. 실 사고 보고 후 처리.

### 8. `_SCHEDULE_HINTS` 단독 "스케줄" + 컨텍스트 부족
- **위치**: `intent_router.py:145`
- **재현**: "이거 작업 스케줄링 어떻게 잡지?" (자연어, 일정 조회/등록 의도 아님)
- **현재 흐름**: 일정 키워드 매치 + 액션 키워드 미매치 → `return None` → LLM 위임. 안전망 동작 OK.
- **결론**: 갭 아님. 안전망 동작 검증 차원에서 기록만 유지.

---

## 다음 작업 시 권장 순서

1. **#1 (코드+KISA)** 부터 — 의도가 명백하고 수정 한 줄로 끝남.
2. **#2 (페르소나)** — 페르소나 ID 리스트가 카탈로그에 이미 명시돼 있어 키워드 추출 단순.
3. **#3 (인터뷰+일정)** — 룰 수정보다는 LLM 시스템 프롬프트 가이드 보강이 안전.
4. **#4 (SNAPSHOT vs DIFF)** — 현재 동작이 "의도된 설계"라 변경 전 사용자와 합의 필요.
5. **#5~#8** — 실 사고 발생 후 우선순위 재평가.

각 수정 후 `_classify_by_rules` 의 룰 순서가 "구체적 → 일반적" 으로 유지되는지 함께 점검.

## 검증 체크리스트 (수정 시)

수정마다 아래 검증 케이스가 모두 통과하는지 확인 (현재는 단위 테스트 없음 — 수정 작업 시 함께 추가 권장):

- [ ] `"6월 19일 '하이옐로우 마승은' 일정 등록해줘"` → `schedule_register` (이미 통과)
- [ ] `"오늘 일정 알려줘"` → `schedule_today`
- [ ] `"4월 15일 일정 뭐 있어?"` → `schedule_search` (date=2026-04-15)
- [ ] `.py` 첨부 + `"KISA 점검"` → `code_kisa` (현재 `code_review`, 수정 대상)
- [ ] `.pdf` 첨부 + `"customer_voice 페르소나 깊이"` → `pitch_focus` (현재 `pitch_quick`, 수정 대상)
- [ ] `"다음 주 고객 인터뷰 일정 잡아줘"` → `schedule_register` (현재 LLM 의 판단에 의존)
- [ ] `"develop 브랜치 변경사항 봐줘"` → `code_branch_diff`
- [ ] `"develop 브랜치 전체 통째로 리뷰"` → `code_branch_snapshot`
