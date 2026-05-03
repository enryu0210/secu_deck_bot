# 🎨 Design Echo

> Phase 2 — Argos PC 앱·관리자 대시보드·랜딩페이지(7월 오픈) 의 디자인 시스템·핸드오프·UX 라이팅 봇.

---

## 슬래시 커맨드

| 커맨드 | 동작 | 예상 시간 | 모델 |
|---|---|---|---|
| `/design check` | 시안 PNG/JPG → DS 토큰 일관성 + 화면 텍스트 톤 체크 | ~30초 | Gemini Flash (Vision) + Sonnet (톤) |
| `/design spec` | 시안 → 개발 핸드오프 spec (Tailwind 힌트 포함) | ~60초 | Gemini Flash (Vision) |
| `/design copy` | 카피 1개 → 톤 검토 + 3가지 대안 (A 차분 / B 신뢰 / C 행동) | ~20초 | Claude Sonnet |

### 사용 예

```
/design check
  image: dashboard_v2.png
```

```
/design spec
  image: scan_results.png
  screen_name: 관리자 대시보드 / 점검 결과
```

```
/design copy
  screen_context: 회원가입 완료 후
  purpose: 사용자가 다음 단계로 자연스럽게 이동
  current_copy: 축하합니다! Argos에 오신 걸 환영합니다 🎉
```

---

## 환경변수

| 키 | 필수 | 설명 |
|---|---|---|
| `DISCORD_BOT_TOKEN_DESIGN` | ✅ | Discord 봇 토큰 |
| `GOOGLE_API_KEY` | ✅ | Gemini Vision (시안 분석) |
| `ANTHROPIC_API_KEY` | ✅ | Sonnet (톤·카피) |
| `DISCORD_GUILD_ID` | 선택 | 개발 중 즉시 슬래시 동기화용 |
| `COST_MONTHLY_LIMIT_KRW_DESIGN` | 선택 | 월 한도(원). 기본 50000 |
| `ARGOS_CONTEXT_PATH` | 선택 | Argos_Context.md 경로 |

---

## 디자인 시스템 (봇의 "정답지")

`design_system/` 의 YAML 3개가 source of truth. 디자인팀이 직접 수정 → 봇이 mtime 감지 후 자동 재로드.

| 파일 | 역할 |
|---|---|
| `tokens.yaml` | 색상·타이포·간격·radius·elevation 토큰 |
| `components.yaml` | 등록된 UI 컴포넌트 목록 |
| `tone_guide.yaml` | UX 라이팅 톤·금기·예시 |

### 비교 로직 (`design_system.py`)

- **색상** — RGB 거리 ≤ 12 면 ✅ 일치 / ≤ ~50 이면 ⚠️ 거의 같음 / 그 이상이면 ❌ 미등록
- **타이포 크기** — DS 표준 ±1px 까지 ⚠️ 권장 알림
- **간격** — 8px 그리드 (4·8·12·16·20·24·32·40·48·64) 벗어나면 ⚠️
- **컴포넌트** — components.yaml 에 없는 이름 등장 시 ⚠️ "DS 미등록"

LLM 호출 없이 룰베이스로 판정해 비용 0 + 결과 일관.

---

## ⚠️ 주의사항

### 1. 이미지 형식
- PNG / JPG / WEBP 지원 (8MB 이하)
- PSD / Figma 파일은 직접 분석 X → "PNG export 후 업로드" 안내

### 2. 외부 LLM 전송
- 시안 이미지 → Google Gemini API 전송
- 미공개 경쟁 정보가 시안에 있다면 봇 사용 자제 권장

### 3. Vision 추출의 한계
- 압축·렌더링 차이로 실제 디자인과 미세 색상 차이 발생 가능
- 경계 픽셀이 흐리면 폰트 크기 추정에 ±1~2px 오차
- 모든 결과 임베드 끝에 면책 한 줄 자동 부착

### 4. 톤 가이드 한국어
- 한국어 톤 분석은 Gemini 보다 Claude Sonnet 이 안정적 → 톤 체크는 항상 Sonnet 강제

---

## 비용 예산 (월)

| 시나리오 | 회수 | 호출당 | 합계 |
|---|---|---|---|
| `/design check` (Vision + 톤) | 40 | ~250원 | 10,000원 |
| `/design spec` | 10 | ~60원 | 600원 |
| `/design copy` | 20 | ~350원 | 7,000원 |
| **합계** | | | **약 17,600원** |

월 한도 기본 50,000원. 95% 도달 경고 / 100% 초과 시 비용 발생 기능 차단.
