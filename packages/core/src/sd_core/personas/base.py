"""Persona 데이터클래스 + 시스템 프롬프트 직렬화."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Persona:
    """봇 페르소나 (예: Pitch Sharpener 의 Customer Voice)."""

    id: str
    name: str
    emoji: str
    title: str
    core_lens: str
    priorities: list[str] = field(default_factory=list)
    speaking_style: dict[str, Any] = field(default_factory=dict)
    forbidden: list[str] = field(default_factory=list)
    decision_lens: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    output_format: str = ""
    # 원본 YAML 필드 추가 (몰랐던 키도 시스템 프롬프트 생성 시 포함)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_system_prompt(self) -> str:
        """페르소나를 LLM 시스템 프롬프트 텍스트로 변환.

        한국어로 직역해 모델이 일관된 톤·관점을 유지하게 한다.
        """
        parts: list[str] = [
            f"# 당신의 정체성: {self.emoji} {self.name} — {self.title}",
            "",
            "## 핵심 관점",
            self.core_lens.strip(),
        ]
        if self.priorities:
            parts.append("\n## 우선순위 (위에서 아래)")
            for p in self.priorities:
                parts.append(f"- {p}")
        if self.decision_lens:
            parts.append("\n## 판단 기준")
            for d in self.decision_lens:
                parts.append(f"- {d}")
        if self.red_flags:
            parts.append("\n## 위험 신호")
            for r in self.red_flags:
                parts.append(f"- {r}")
        if self.speaking_style:
            parts.append("\n## 말투·형식")
            for k, v in self.speaking_style.items():
                parts.append(f"- {k}: {v}")
        if self.forbidden:
            parts.append("\n## 금기")
            for f_item in self.forbidden:
                parts.append(f"- {f_item}")
        if self.output_format:
            parts.append("\n## 출력 형식")
            parts.append(self.output_format.strip())
        return "\n".join(parts)
