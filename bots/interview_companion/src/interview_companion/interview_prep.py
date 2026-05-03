"""인터뷰 가이드 생성기.

대표가 인터뷰 30분 전에 호출. Claude Sonnet 1회로 가설별 우선순위·질문지·주의사항을 만든다.
가설은 ``data/argos_hypotheses.yaml`` 에서 mtime 감지 자동 재로드.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from sd_core.context.argos import ArgosContext
from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger

from interview_companion.storage import InterviewTarget


_log = get_logger("interview_companion.prep")


@dataclass
class Hypothesis:
    id: str
    statement: str
    priority: int
    related_features: list[str] = field(default_factory=list)
    sample_questions: list[str] = field(default_factory=list)


@dataclass
class InterviewGuide:
    """봇 응답으로 그대로 사용. text 는 LLM 의 원문 markdown."""

    text: str
    cost_krw: float
    focused_hypotheses: list[str]


class _HypothesisRepo:
    """YAML 가설 카탈로그 로더. mtime 감지로 봇 재시작 없이 갱신."""

    def __init__(self, path: Path):
        self._path = path
        self._cache: list[Hypothesis] = []
        self._mtime: float | None = None
        self._lock = Lock()

    def list_all(self) -> list[Hypothesis]:
        self._reload_if_changed()
        return list(self._cache)

    def by_id(self, hyp_id: str) -> Hypothesis | None:
        for h in self.list_all():
            if h.id == hyp_id:
                return h
        return None

    def _reload_if_changed(self) -> None:
        with self._lock:
            if not self._path.exists():
                raise ConfigError(f"가설 카탈로그 파일이 없습니다: {self._path}")
            current = self._path.stat().st_mtime
            if self._cache and current == self._mtime:
                return
            try:
                data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                raise ConfigError(f"가설 YAML 파싱 실패: {exc}") from exc

            raw = data.get("hypotheses") or []
            parsed: list[Hypothesis] = []
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                try:
                    parsed.append(Hypothesis(
                        id=str(entry["id"]),
                        statement=str(entry.get("statement", "")),
                        priority=int(entry.get("priority", 2)),
                        related_features=list(entry.get("related_features") or []),
                        sample_questions=list(entry.get("sample_questions") or []),
                    ))
                except KeyError as exc:
                    _log.warning("hypothesis_missing_key", error=str(exc))
            if not parsed:
                raise ConfigError("가설 카탈로그가 비어 있습니다.")
            self._cache = parsed
            self._mtime = current
            _log.info("hypotheses_loaded", count=len(parsed))


class InterviewPrep:
    """인터뷰 가이드 생성 메인."""

    def __init__(
        self,
        llm: LLMRouter,
        argos: ArgosContext,
        hypotheses_path: Path,
        prompt_path: Path,
    ):
        self.llm = llm
        self.argos = argos
        self.repo = _HypothesisRepo(hypotheses_path)
        self._prompt_path = prompt_path
        self._prompt_cache: tuple[float, str] | None = None

    def all_hypotheses(self) -> list[Hypothesis]:
        return self.repo.list_all()

    async def generate_guide(
        self,
        target: InterviewTarget,
        focus_ids: list[str] | None,
        user_id: str,
    ) -> InterviewGuide:
        """가이드 생성.

        focus_ids: 사용자가 강조하고 싶은 가설 ID. None 이면 priority 1 자동 선택.
        """
        all_hyp = self.repo.list_all()
        if focus_ids:
            chosen = [h for h in all_hyp if h.id in set(focus_ids)]
            if not chosen:
                # 잘못된 ID 들어와도 빈 가이드 만들지 말고 priority 1 로 폴백
                chosen = [h for h in all_hyp if h.priority == 1]
        else:
            chosen = [h for h in all_hyp if h.priority == 1]
        if not chosen:
            # 모든 가설이 priority 2 인 경우 (방어), 전체 사용
            chosen = all_hyp

        system_prompt = self._build_system_prompt()
        user_content = self._build_user_message(target, chosen, all_hyp)

        request = LLMRequest(
            task_type=TaskType.KOREAN_WRITING,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            user_id=user_id,
            bot_name="interview_companion",
            max_tokens=1800,
            temperature=0.4,  # 일관성 우선
        )
        response = await self.llm.call(request)
        return InterviewGuide(
            text=response.text,
            cost_krw=response.cost_krw,
            focused_hypotheses=[h.id for h in chosen],
        )

    # -----------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        """시스템 프롬프트 = 가이드 템플릿 + Argos 요약. 캐시 효과 위해 1024자 이상 보장."""
        prompt = self._read_prompt()
        return "\n\n".join([
            prompt,
            "# Argos 제품 맥락 (인터뷰 가이드 설계 시 참고용. 인터뷰이에게는 노출 X)",
            self.argos.get_summary(max_tokens=1500),
        ])

    def _build_user_message(
        self,
        target: InterviewTarget,
        focused: list[Hypothesis],
        all_hyp: list[Hypothesis],
    ) -> str:
        """user 메시지에 인터뷰이 정보 + 가설 카탈로그 (집중 vs 전체) 를 담는다."""
        lines = [
            "## 인터뷰이 정보",
            f"- 이름·식별: {target.name}",
            f"- 역할: {target.role}",
            f"- 회사: {target.company} (규모 {target.company_size})",
            f"- 배경: {target.background or '추가 정보 없음'}",
            "",
            "## 이번 인터뷰에서 집중 검증할 가설",
        ]
        for h in focused:
            lines.append(f"- **{h.id}** (P{h.priority}): {h.statement}")
            if h.sample_questions:
                lines.append("  참고 질문 후보:")
                for q in h.sample_questions:
                    lines.append(f"    - {q}")

        if len(focused) < len(all_hyp):
            lines.append("\n## 참고: 전체 가설 목록 (집중 외 가설은 시간 남으면 다룸)")
            for h in all_hyp:
                if h not in focused:
                    lines.append(f"- {h.id} (P{h.priority}): {h.statement}")

        lines.append("")
        lines.append(
            "위 정보를 바탕으로 30분 인터뷰 가이드를 만들어 주세요. "
            "출력은 system 의 형식을 그대로 따라야 합니다."
        )
        return "\n".join(lines)

    def _read_prompt(self) -> str:
        """프롬프트 파일 mtime 감지 캐시."""
        current = self._prompt_path.stat().st_mtime if self._prompt_path.exists() else 0
        if self._prompt_cache and self._prompt_cache[0] == current:
            return self._prompt_cache[1]
        text = self._prompt_path.read_text(encoding="utf-8") if self._prompt_path.exists() else ""
        self._prompt_cache = (current, text)
        return text


__all__ = ["InterviewPrep", "InterviewGuide", "Hypothesis"]
