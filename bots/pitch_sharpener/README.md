# Pitch Sharpener

> 사업계획서 6 페르소나 정밀 리뷰 봇. 1차 탈락 6대 원인을 직격.

## 슬래시 커맨드

| 명령 | 설명 |
|---|---|
| `/pitch review` | 6 페르소나 병렬 정밀 리뷰 (약 2분) |
| `/pitch quick`  | 1분 이내 빠른 진단 |
| `/pitch focus`  | 단일 페르소나 깊이 리뷰 (Select 메뉴) |

## 페르소나 (1차 탈락 6대 원인 매핑)

1. 🎤 Customer Voice — 고객 검증 부재
2. 📊 Data Skeptic — 시장 데이터 출처
3. 💸 Pricing Analyst — 가격 근거
4. 🎯 Competitor Hunter — 경쟁사 분석
5. ⚙️ Tech Differentiator — 기술 차별성
6. 💰 Budget Reality — 인건비·예산

## 로컬 실행

```bash
# 모노레포 루트에서
uv sync

# .env 에 DISCORD_BOT_TOKEN_PITCH, ANTHROPIC_API_KEY 설정 후
cd bots/pitch_sharpener
uv run python -m pitch_sharpener.main
```

## 사용 예

```
사용자: /pitch review [argos.pdf 첨부]
봇:    🏁 종합 심사 결과
       [등급] B-
       [Top 3 우선 조치]
       1. 인터뷰 10건 인용 추가 (Customer Voice)
       2. 모든 숫자에 1차 출처 (Data Skeptic)
       3. 인건비 산정 로직 명시 (Budget Reality)

       [🎤 Customer Voice]
       검증 필요 가설 7개 중 인터뷰 근거 0개. ...

       [📊 Data Skeptic]
       문서 내 숫자 14개 중 출처 명시 3개. ...

       (이하 6 페르소나)
```

## 주의

- 사업계획서가 외부 LLM(Anthropic) 으로 전송됩니다. 미공개 사업 정보는 신중히.
- 모델 ID(`claude-sonnet-4-5`) 는 2026.04 기준 추정. 실 배포 전 검증 필수.
- 한 번 풀 리뷰 비용 ≈ 2,000원 (Prompt Caching 적용 시).
