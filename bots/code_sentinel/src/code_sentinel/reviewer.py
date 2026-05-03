"""리뷰 오케스트레이션 — RuleMatcher → Escalator → LLMRouter."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from sd_core.context.argos import ArgosContext
from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType

from code_sentinel.escalator import Escalator
from code_sentinel.rule_matcher import (
    Finding,
    RuleMatcher,
    serialize_findings_for_prompt,
)


@dataclass
class ReviewResult:
    text: str
    findings: list[Finding]
    model_used: str
    cost_krw: float
    fallback_triggered: bool


@dataclass
class ComplianceReport:
    text: str
    cost_krw: float


@dataclass
class TestSuite:
    text: str
    cost_krw: float


class CodeReviewer:
    """``/code review``, ``/code test``, ``/code kisa`` 의 백엔드."""

    def __init__(
        self,
        llm: LLMRouter,
        argos: ArgosContext,
        rules_dir: Path,
        prompts_dir: Path,
    ):
        self.llm = llm
        self.argos = argos
        self.matcher = RuleMatcher(rules_dir / "argos_patterns.yaml")
        self.kisa_text = self._read_yaml_as_text(rules_dir / "kisa_guidelines.yaml")
        self.pipa_text = self._read_yaml_as_text(rules_dir / "pipa_articles.yaml")
        self.escalator = Escalator()

        self._base_prompt = self._read(prompts_dir / "system_base.md")
        self._review_general = self._read(prompts_dir / "review_general.md")
        self._review_security = self._read(prompts_dir / "review_security.md")
        self._test_gen = self._read(prompts_dir / "test_generation.md")
        self._kisa_check = self._read(prompts_dir / "kisa_compliance.md")

    # -----------------------------------------------------------------
    async def review(
        self,
        code: str,
        language: str,
        focus: str | None,
        user_id: str,
    ) -> ReviewResult:
        # 1) 룰베이스 1차
        findings = self.matcher.match(code)

        # 2) Haiku vs Sonnet 결정
        task_type = self.escalator.choose(code, findings, focus)

        # 3) LLM 호출
        focus_prompt = self._review_security if focus == "security" else self._review_general
        system = self._compose_system(focus_prompt)

        user_content = (
            f"언어: {language}\n"
            f"{serialize_findings_for_prompt(findings)}\n"
            "--- 코드 시작 ---\n"
            f"{code}\n"
            "--- 코드 끝 ---"
        )

        response = await self.llm.call(LLMRequest(
            task_type=task_type,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="code_sentinel",
            max_tokens=2000,
            temperature=0.3,
        ))

        return ReviewResult(
            text=response.text,
            findings=findings,
            model_used=response.model_used,
            cost_krw=response.cost_krw,
            fallback_triggered=response.fallback_triggered,
        )

    # -----------------------------------------------------------------
    async def generate_tests(self, code: str, language: str, user_id: str) -> TestSuite:
        system = self._compose_system(self._test_gen)
        response = await self.llm.call(LLMRequest(
            task_type=TaskType.CODE_REVIEW_COMPLEX,  # 테스트 생성은 Sonnet 권장
            system=system,
            messages=[{
                "role": "user",
                "content": f"언어: {language}\n\n--- 코드 ---\n{code}\n--- 끝 ---",
            }],
            user_id=user_id,
            bot_name="code_sentinel",
            max_tokens=2200,
            temperature=0.4,
        ))
        return TestSuite(text=response.text, cost_krw=response.cost_krw)

    # -----------------------------------------------------------------
    async def check_kisa(self, feature_description: str, user_id: str) -> ComplianceReport:
        system = "\n\n".join([
            self._base_prompt,
            self._kisa_check,
            "# KISA 가이드라인",
            self.kisa_text,
            "# 개인정보보호법 조항",
            self.pipa_text,
            "# Argos 컨텍스트",
            self.argos.get_summary(max_tokens=1200),
        ])
        response = await self.llm.call(LLMRequest(
            task_type=TaskType.CODE_REVIEW_COMPLEX,
            system=system,
            messages=[{
                "role": "user",
                "content": f"다음 신규 기능을 분석해 주세요.\n\n{feature_description}",
            }],
            user_id=user_id,
            bot_name="code_sentinel",
            max_tokens=1800,
            temperature=0.3,
        ))
        return ComplianceReport(text=response.text, cost_krw=response.cost_krw)

    # -----------------------------------------------------------------
    def _compose_system(self, focus_prompt: str) -> str:
        return "\n\n".join([
            self._base_prompt,
            focus_prompt,
            "# Argos 컨텍스트",
            self.argos.get_summary(max_tokens=1500),
            "# KISA 가이드라인 (요약)",
            self.kisa_text,
        ])

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @staticmethod
    def _read_yaml_as_text(path: Path) -> str:
        """YAML 을 LLM 가독 텍스트로 변환 (key: value 직렬화)."""
        if not path.exists():
            return ""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
