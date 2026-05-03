"""모델 자동 승급 판단.

기본은 Haiku (저렴·빠름). 다음 중 하나라도 만족하면 Sonnet 으로 승급:
- CRITICAL/HIGH severity 룰 발견
- 코드 길이 > 300줄
- 보안 키워드 다수
- 사용자가 명시적으로 'security' focus 선택
"""
from __future__ import annotations

import re

from sd_core.llm.types import TaskType

from code_sentinel.rule_matcher import Finding


_SECURITY_KEYWORDS = re.compile(
    r"\b(encrypt|decrypt|auth|token|password|secret|crypto|nonce|kms|hash|salt|jwt|tls|ssl)\b",
    re.IGNORECASE,
)


class Escalator:
    """간단 vs 복잡 판단 → TaskType 반환."""

    def choose(
        self,
        code: str,
        rule_findings: list[Finding],
        focus: str | None = None,
    ) -> TaskType:
        if focus and focus.lower() == "security":
            return TaskType.CODE_REVIEW_COMPLEX
        if any(f.severity in ("CRITICAL", "HIGH") for f in rule_findings):
            return TaskType.CODE_REVIEW_COMPLEX
        if len(code.splitlines()) > 300:
            return TaskType.CODE_REVIEW_COMPLEX
        # 보안 키워드가 5개 이상 등장하면 보안 코드로 간주
        if len(_SECURITY_KEYWORDS.findall(code)) >= 5:
            return TaskType.CODE_REVIEW_COMPLEX
        return TaskType.CODE_REVIEW_SIMPLE
