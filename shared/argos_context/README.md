# Argos Context

이 디렉토리에 `Argos_Context.md` 파일을 배치해 주세요.

이 파일은 모든 봇의 시스템 프롬프트에 들어가는 핵심 제품 컨텍스트입니다.
파일이 없으면 봇은 일반 응답만 가능하고 Argos 특화 판단(보안 이슈·KISA 정합성 등)
신뢰도가 떨어집니다.

## 배치 방법
```
shared/argos_context/Argos_Context.md
```

## 주의
- `.gitignore` 에 의해 이 파일은 커밋되지 않습니다 (외부 노출 방지).
- 운영 환경에서는 환경변수 `ARGOS_CONTEXT_PATH` 로 다른 경로를 지정할 수도 있습니다.
- 파일이 변경되면 봇 재시작 없이 자동 재로드됩니다 (`ArgosContext` mtime 추적).
