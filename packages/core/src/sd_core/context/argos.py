"""Argos_Context.md 로더.

모든 봇의 시스템 프롬프트에 들어가는 핵심 컨텍스트. mtime 추적해 봇 재시작 없이 갱신.
파일이 없는 경우(개발 초기) 안전한 빈 기본값을 돌려 봇이 부팅은 되도록 한다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from threading import Lock

from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.context.argos")

# Argos 컨텍스트가 없을 때 기본 안내 — 비어 있으면 봇이 사실 환각을 만들 위험.
_FALLBACK = """\
[ Argos 컨텍스트 미배치 ]

shared/argos_context/Argos_Context.md 파일이 아직 배치되지 않았습니다.
봇은 일반 응답만 가능하며, 제품 특화 판단(보안 이슈·KISA 정합성 등)은 신뢰도가 떨어질 수 있습니다.
관리자에게 Argos_Context.md 배치 요청을 보내주세요.
"""


class ArgosContext:
    """Argos 제품 컨텍스트를 로드·캐시·재로드하는 헬퍼.

    사용 방식:
        ctx = ArgosContext()
        ctx.get_summary()             # 시스템 프롬프트용 요약
        ctx.get_section("보안_이슈")  # 특정 섹션만
    """

    DEFAULT_PATH = "shared/argos_context/Argos_Context.md"

    def __init__(self, path: str | None = None):
        # 환경변수 ARGOS_CONTEXT_PATH 가 있으면 우선
        env_path = os.getenv("ARGOS_CONTEXT_PATH")
        self._path = Path(path or env_path or self.DEFAULT_PATH)
        self._cache: str | None = None
        self._mtime: float | None = None
        self._lock = Lock()

    # ---------------- public ----------------
    def get_full(self) -> str:
        """전체 문서 — 비용 큼. 자주 쓰지 말 것."""
        return self._read_with_reload()

    def get_summary(self, max_tokens: int = 2000) -> str:
        """봇 시스템 프롬프트용 요약. 약 max_tokens × 4자 까지 절단.

        토큰을 정확히 세지 않고 문자 길이로 근사. 한국어 1토큰 ≈ 1.5~2자.
        """
        full = self._read_with_reload()
        # 매우 긴 경우 헤딩 위주로 추려서 자른다.
        max_chars = max_tokens * 3  # 보수적
        if len(full) <= max_chars:
            return full
        return self._truncate_smart(full, max_chars)

    def get_section(self, section_id: str) -> str:
        """헤딩 일치하는 섹션만 추출 (대소문자·공백 무시).

        예: ``get_section("보안 이슈 요약")`` 또는 ``get_section("제품 핵심 기능")``.
        """
        full = self._read_with_reload()
        return self._extract_section(full, section_id)

    # ---------------- internal ----------------
    def _read_with_reload(self) -> str:
        """파일 mtime 변화 감지해 자동 재로드. 파일 없으면 폴백."""
        with self._lock:
            if not self._path.exists():
                if self._cache is None:
                    _log.warning("argos_context_missing", path=str(self._path))
                return _FALLBACK
            current_mtime = self._path.stat().st_mtime
            if self._cache is None or current_mtime != self._mtime:
                try:
                    self._cache = self._path.read_text(encoding="utf-8")
                    self._mtime = current_mtime
                    _log.info("argos_context_loaded", path=str(self._path), bytes=len(self._cache))
                except OSError as exc:
                    _log.warning("argos_context_read_failed", error=str(exc))
                    return _FALLBACK
            return self._cache or _FALLBACK

    @staticmethod
    def _truncate_smart(text: str, max_chars: int) -> str:
        """헤딩 단위로 잘라 max_chars 이하로 만든다.

        가장 단순한 방법: 헤딩 단위로 누적하되 한도 도달 시 멈춤.
        """
        sections = re.split(r"(?m)^(?=#)", text)
        out: list[str] = []
        total = 0
        for s in sections:
            if total + len(s) > max_chars:
                # 마지막 섹션은 잘라서 추가
                remaining = max_chars - total
                if remaining > 200:
                    out.append(s[:remaining] + "\n\n[...요약 절단...]")
                break
            out.append(s)
            total += len(s)
        return "".join(out)

    @staticmethod
    def _extract_section(text: str, target: str) -> str:
        """target 키워드와 일치하는 헤딩의 본문만 반환."""
        # 헤딩(# ~ ######) 으로 분할
        normalized_target = re.sub(r"\s+", "", target).lower()
        pattern = re.compile(r"(?m)^(#{1,6})\s*(.+?)\s*$")
        matches = list(pattern.finditer(text))
        for i, m in enumerate(matches):
            heading = re.sub(r"\s+", "", m.group(2)).lower()
            if normalized_target in heading:
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                return text[start:end].strip()
        return ""  # 매칭 없으면 빈 문자열
