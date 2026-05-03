# 🎙 Interview Companion

> Phase 2 — 고객 인터뷰 가이드·기록·누적 분석 봇.
> 5월 사업계획서 재지원의 1차 탈락 원인("고객 검증 부재") 해소가 핵심 미션.

---

## 슬래시 커맨드

| 커맨드 | 동작 | 예상 시간 | 모델 |
|---|---|---|---|
| `/interview prep` | 인터뷰 가이드 생성 (가설별 우선순위 + 단계별 질문지) | ~30초 | Claude Sonnet |
| `/interview log` | 인터뷰 메모/녹취 → 요약·가설검증·인용 추출 + 저장 | ~60초 | Gemini Flash + Sonnet |
| `/interview insight` | 누적 인터뷰 패턴 분석 (가설 카운트·페인 포인트·인용 후보) | ~90초 | Gemini Flash (1M 컨텍스트) |
| `/interview quotes` | 저장된 인용문 키워드/가설 필터 검색 | 즉시 | LLM 사용 안 함 |

### 사용 예

```
/interview prep
  target_name: "A보험 보안팀장"
  target_role: 보안팀장
  target_company: A보험 (익명)
  company_size: 30인
  background: 작년 KISA 점검 미흡, 외부 컨설팅 활용 중
  focus: H1_subcontractor_risk,H4_compliance_report_burden  # 비우면 priority 1 자동 선택
```

```
/interview log
  target_name: "A보험 보안팀장"
  date_str: 2026-04-15
  notes: meeting_notes.txt        # 또는 text 인자로 직접 입력
```

---

## 환경변수

| 키 | 필수 | 설명 |
|---|---|---|
| `DISCORD_BOT_TOKEN_INTERVIEW` | ✅ | Discord 봇 토큰 |
| `ANTHROPIC_API_KEY` | ✅ | Claude API 키 (가이드·정리·인용 추출) |
| `GOOGLE_API_KEY` | ✅ | Gemini API 키 (긴 녹취 압축 + 누적 분석) |
| `DATABASE_URL` | ⚠️ | Postgres DSN. 없으면 in-memory 폴백 (재시작 시 데이터 소실) |
| `DISCORD_GUILD_ID` | 선택 | 개발 중 즉시 슬래시 동기화용 |
| `COST_MONTHLY_LIMIT_KRW_INTERVIEW` | 선택 | 월 한도(원). 기본 50000 |
| `ARGOS_CONTEXT_PATH` | 선택 | Argos_Context.md 경로 |

---

## 데이터 모델

스키마 정의: [`migrations/001_interviews.sql`](migrations/001_interviews.sql)

- `interviews` — 인터뷰 본체 + 요약/가설검증/인용 (JSONB)
- `hypotheses` — 가설 카탈로그 미러 (YAML 이 source of truth)

`storage.py` 가 사용자별로 격리해 저장하므로 다른 사용자의 인터뷰는 보이지 않음.

---

## 가설 카탈로그

`data/argos_hypotheses.yaml` 이 봇의 "검증 대상". mtime 감지로 봇 재시작 없이 갱신.

추가 시:
```yaml
- id: H7_새가설
  statement: ...
  priority: 1   # 1 = 사업계획서 재지원 전 검증 필수
  related_features: [...]
  sample_questions: [...]
```

---

## ⚠️ 주의사항

### 1. 인터뷰이 익명화
- `target_name` 은 이니셜·역할로 입력 권장 (실명 비권장)
- `raw_notes` 에 회사 매출·실명 등 민감 정보가 들어갈 수 있음 → 외부 공유 시 주의

### 2. 외부 LLM 전송
- 정리 단계에서 인터뷰 메모가 Claude API 로 전송됨
- 긴 녹취(~8000자 이상)는 Google Gemini API 로도 1차 압축 전송
- 매우 민감한 인터뷰는 봇을 사용하지 말고 직접 정리 권장

### 3. 자동 분석 한계
- 가설 카운트가 절대적으로 보일 위험. 모든 임베드 끝에 면책 한 줄 자동 부착.
- 인용 발언은 사업계획서 사용 전 원문(녹취) 재확인 필수.

### 4. 6개월 익명화 (TODO)
- `interviews.anonymized_at` 컬럼 준비됨. 별도 cron (Argos Self-Audit 봇 또는 Railway Cron) 으로
  6개월 경과 row 의 `raw_notes` / `quotes` 를 마스킹할 것. (Stage 6 또는 별도 작업)

---

## 비용 예산 (월)

| 시나리오 | 회수 | 호출당 | 합계 |
|---|---|---|---|
| 가이드 생성 | 10 | ~600원 | 6,000원 |
| 로그(짧음) | 6 | ~400원 | 2,400원 |
| 로그(긴 녹취) | 4 | ~700원 | 2,800원 |
| 누적 분석 | 5 | ~800원 | 4,000원 |
| **합계** | | | **약 15,200원** |

월 한도 기본 50,000원. 95% 도달 시 봇이 경고 로그, 100% 초과 시 비용 발생 기능 차단.
