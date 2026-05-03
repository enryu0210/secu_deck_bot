# Code Sentinel

> 코드 리뷰 + KISA 가이드라인·개인정보보호법 정합성 자동 체크 봇.

## 슬래시 커맨드

| 명령 | 설명 |
|---|---|
| `/code review` | 코드 첨부/입력/PR URL → 일반 + Argos 보안 리뷰 |
| `/code test`   | 단위 테스트 자동 생성 (positive/negative/edge) |
| `/code kisa`   | 신규 기능 설명 → KISA·PIPA 정합성 매핑 |

## 동작 흐름

1. 사용자 입력 → ``RuleMatcher`` 가 정규식·휴리스틱으로 1차 매칭 (LLM 비용 0)
2. ``Escalator`` 가 CRITICAL/HIGH 발견·코드 길이·보안 키워드로 Haiku vs Sonnet 결정
3. ``LLMRouter`` 호출 — 시스템 프롬프트에 룰 매처 결과를 함께 주입
4. LLM 이 false positive 검증 + 추가 발견을 더해 최종 보고서 생성

## 로컬 실행

```bash
uv sync
cd bots/code_sentinel
uv run python -m code_sentinel.main
```

## 주의

- ⚠️ **코드 외부 전송**: 첨부 코드가 Anthropic API 로 전송됩니다.
  민감 코드는 직접 리뷰하거나 Anthropic Zero Data Retention 플랜 사용.
- GitHub PR URL 사용 시 read-only PAT 필요 (`GITHUB_PAT`).
- 모델 ID(`claude-haiku-4-5`, `claude-sonnet-4-5`) 는 2026.04 기준 추정.
- 비용: 짧은 코드 ≈ 80원, 보안 집중 ≈ 600원 (Sonnet 승급 시).
