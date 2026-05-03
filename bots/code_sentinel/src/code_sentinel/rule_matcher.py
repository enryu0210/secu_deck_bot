"""룰베이스 1차 매처.

LLM 호출 전에 정규식·간단 휴리스틱으로 잡을 수 있는 건 미리 잡아 비용 절감.
정규식 결과는 시스템 프롬프트에 ``[RULE_FINDINGS]`` 블록으로 주입되어,
LLM 이 false positive 인지 판단하고 최종 보고서를 만든다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sd_core.utils.errors import ConfigError


@dataclass
class Finding:
    rule_id: str
    severity: str            # CRITICAL / HIGH / MED / LOW
    description: str
    line_number: int | None
    matched_text: str
    suggestion: str

    def to_brief(self) -> str:
        loc = f"line {self.line_number}" if self.line_number else "(line 추정 불가)"
        return (
            f"[{self.severity}] {self.rule_id} @ {loc}\n"
            f"  desc: {self.description}\n"
            f"  match: {self.matched_text[:100]}\n"
            f"  suggest: {self.suggestion}"
        )


class RuleMatcher:
    """argos_patterns.yaml 기반 매처."""

    def __init__(self, rules_path: Path):
        self.rules: list[dict[str, Any]] = self._load(rules_path)

    def match(self, code: str) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self.rules:
            findings.extend(self._apply_rule(code, rule))
        return findings

    # -----------------------------------------------------------------
    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise ConfigError(f"Rules file not found: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML parse error: {exc}") from exc
        return list(data.get("patterns", []))

    @staticmethod
    def _apply_rule(code: str, rule: dict[str, Any]) -> list[Finding]:
        rule_id = rule.get("id", "unknown")
        severity = rule.get("severity", "MED")
        description = rule.get("description", "")
        suggestion = rule.get("suggestion", "")

        # 단순 regex
        regex = rule.get("regex")
        # co-occur (must_match + must_not_match) — PII 외부 송신 같은 패턴
        co_occur = rule.get("regex_co_occur")

        findings: list[Finding] = []

        if regex:
            try:
                pattern = re.compile(regex, re.MULTILINE)
            except re.error:
                # 정규식 자체가 잘못된 경우 — 룰 작성자가 고쳐야 함
                return []

            for m in pattern.finditer(code):
                line_no = code.count("\n", 0, m.start()) + 1
                findings.append(Finding(
                    rule_id=rule_id,
                    severity=severity,
                    description=description,
                    line_number=line_no,
                    matched_text=m.group(0),
                    suggestion=suggestion,
                ))

        if co_occur:
            must = co_occur.get("must_match")
            must_not = co_occur.get("must_not_match")
            if must and re.search(must, code):
                if not (must_not and re.search(must_not, code)):
                    # 위치는 must 매칭 첫 줄로
                    m = re.search(must, code)
                    line_no = code.count("\n", 0, m.start()) + 1 if m else None
                    findings.append(Finding(
                        rule_id=rule_id,
                        severity=severity,
                        description=description,
                        line_number=line_no,
                        matched_text=m.group(0) if m else "",
                        suggestion=suggestion,
                    ))

        return findings


def serialize_findings_for_prompt(findings: list[Finding]) -> str:
    """LLM 시스템 프롬프트에 주입할 ``[RULE_FINDINGS]`` 블록."""
    if not findings:
        return "[RULE_FINDINGS]\n(룰 매처가 잡은 항목 없음)\n"
    parts = ["[RULE_FINDINGS]"]
    for f in findings:
        parts.append(f.to_brief())
    parts.append("")
    return "\n".join(parts)
