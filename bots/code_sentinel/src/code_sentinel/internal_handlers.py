"""Chief of Staff 위임용 액션 핸들러.

지원 액션:
- ``code_review``:           payload={"code": str, "language": str?, "focus": "general"|"security"|None}
- ``code_test``:             payload={"code": str, "language": str?}
- ``code_kisa``:             payload={"feature_description": str}
- ``code_branch_diff``:      payload={"branch": str, "repo": str?, "base": str?, "focus": str?}
- ``code_branch_snapshot``:  payload={"branch": str, "repo": str?, "focus": str?}

언어 미지정 시 ``LanguageDetector`` 가 자동 감지.

브랜치 액션은 GitHubFetcher 가 필요 — main.py 에서 fetcher 를 함께 주입한다.
"""
from __future__ import annotations

from typing import Any

from sd_core.utils.errors import SecuDeckError

from code_sentinel.github_fetcher import GitHubFetcher, GitHubFetchError
from code_sentinel.language_detector import detect_language
from code_sentinel.reviewer import CodeReviewer


# Discord 메시지·임베드 description 4096 한계. 코드 6KB 정도가 LLM 입력에도 적합.
_MAX_CODE_LEN = 8000


def _truncate(code: str) -> str:
    if len(code) <= _MAX_CODE_LEN:
        return code
    return code[: _MAX_CODE_LEN - 200] + "\n\n# ... 본문 절단됨 ..."


def _normalize_focus(raw: Any) -> str | None:
    """payload.focus 표준화 — security/general 만 허용, 그 외는 None."""
    if isinstance(raw, str) and raw in ("security", "general"):
        return raw
    return None


class CodeInternalHandlers:
    """CodeReviewer + GitHubFetcher 인스턴스를 공유."""

    def __init__(self, reviewer: CodeReviewer, fetcher: GitHubFetcher):
        self.reviewer = reviewer
        self.fetcher = fetcher

    # -----------------------------------------------------------------
    async def code_review(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        code = (payload.get("code") or "").strip()
        if not code:
            raise SecuDeckError(
                "code 누락",
                user_message="리뷰할 코드를 함께 보내 주세요.",
            )
        language = (payload.get("language") or "").strip() or detect_language(code)
        # focus 는 "security" 일 때만 보안 프롬프트로 전환. 그 외는 general.
        focus_raw = payload.get("focus")
        focus = focus_raw if focus_raw in ("security", "general") else None

        result = await self.reviewer.review(
            code=_truncate(code),
            language=language,
            focus=focus,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [
                {"title": "언어", "value": language or "auto", "inline": True},
                {"title": "포커스", "value": focus or "general", "inline": True},
                {"title": "모델", "value": result.model_used, "inline": True},
                {
                    "title": "룰베이스 발견",
                    "value": str(len(result.findings)),
                    "inline": True,
                },
            ],
        }

    # -----------------------------------------------------------------
    async def code_test(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        code = (payload.get("code") or "").strip()
        if not code:
            raise SecuDeckError(
                "code 누락",
                user_message="테스트를 만들 코드를 함께 보내 주세요.",
            )
        language = (payload.get("language") or "").strip() or detect_language(code)
        result = await self.reviewer.generate_tests(
            code=_truncate(code),
            language=language,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [{"title": "언어", "value": language or "auto", "inline": True}],
        }

    # -----------------------------------------------------------------
    async def code_kisa(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        desc = (payload.get("feature_description") or "").strip()
        if not desc:
            raise SecuDeckError(
                "feature_description 누락",
                user_message="컴플라이언스 점검할 기능 설명을 함께 보내 주세요.",
            )
        # 너무 긴 설명은 자르기 (LLM 입력 한계 대비)
        if len(desc) > 6000:
            desc = desc[:6000] + "\n\n[설명 절단]"
        result = await self.reviewer.check_kisa(feature_description=desc, user_id=user_id)
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [{"title": "검사", "value": "KISA + 개인정보보호법", "inline": True}],
        }

    # -----------------------------------------------------------------
    async def code_branch_diff(
        self, payload: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        """브랜치 ↔ base diff 리뷰 — 슬래시 ``/code branch`` 와 동일 파이프라인."""
        branch = (payload.get("branch") or "").strip()
        if not branch:
            raise SecuDeckError(
                "branch 누락",
                user_message="어느 브랜치를 리뷰할지 알려주세요 (예: feature/auth-rework).",
            )
        repo = (payload.get("repo") or "").strip() or None
        base = (payload.get("base") or "").strip() or None
        focus = _normalize_focus(payload.get("focus"))

        try:
            diff = await self.fetcher.fetch_branch_diff(repo, branch, base=base)
        except GitHubFetchError as exc:
            # cos delegator 가 SecuDeckError.user_message 를 사용자에게 그대로 노출
            raise SecuDeckError(str(exc), user_message=exc.user_message) from exc

        if not diff.changed_files:
            return {
                "ok": True,
                "summary": (
                    f"`{diff.base}` 대비 `{diff.branch}` 에 변경된 파일이 없어요."
                ),
                "cost_krw": 0.0,
                "blocks": [
                    {"title": "레포", "value": diff.repo, "inline": True},
                    {"title": "브랜치", "value": diff.branch, "inline": True},
                    {"title": "base", "value": diff.base, "inline": True},
                ],
            }

        result = await self.reviewer.review(
            code=diff.to_review_prompt(),
            language="multi",
            focus=focus,
            user_id=user_id,
        )
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": [
                {"title": "레포", "value": diff.repo, "inline": True},
                {"title": "브랜치", "value": diff.branch, "inline": True},
                {"title": "base", "value": diff.base, "inline": True},
                {"title": "변경 파일", "value": str(len(diff.changed_files)), "inline": True},
                {"title": "포커스", "value": focus or "general", "inline": True},
                {"title": "모델", "value": result.model_used, "inline": True},
            ],
        }

    # -----------------------------------------------------------------
    async def code_branch_snapshot(
        self, payload: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        """브랜치 전체 스냅샷 리뷰 — 슬래시 ``/code branch_full`` 과 동일 파이프라인."""
        branch = (payload.get("branch") or "").strip()
        if not branch:
            raise SecuDeckError(
                "branch 누락",
                user_message="어느 브랜치를 통째로 리뷰할지 알려주세요.",
            )
        repo = (payload.get("repo") or "").strip() or None
        focus = _normalize_focus(payload.get("focus"))

        try:
            snap = await self.fetcher.fetch_branch_snapshot(repo, branch)
        except GitHubFetchError as exc:
            raise SecuDeckError(str(exc), user_message=exc.user_message) from exc

        if not snap.files:
            return {
                "ok": True,
                "summary": (
                    "스냅샷에서 리뷰 대상 파일을 찾지 못했어요. "
                    "(확장자 화이트리스트·크기 상한 적용 후 0개)"
                ),
                "cost_krw": 0.0,
                "blocks": [
                    {"title": "레포", "value": snap.repo, "inline": True},
                    {"title": "브랜치", "value": snap.branch, "inline": True},
                ],
            }

        result = await self.reviewer.review(
            code=snap.to_review_prompt(),
            language="multi",
            focus=focus,
            user_id=user_id,
        )
        blocks = [
            {"title": "레포", "value": snap.repo, "inline": True},
            {"title": "브랜치", "value": snap.branch, "inline": True},
            {"title": "파일 수", "value": str(len(snap.files)), "inline": True},
            {"title": "총 바이트", "value": f"{snap.total_bytes:,}", "inline": True},
            {"title": "포커스", "value": focus or "general", "inline": True},
            {"title": "모델", "value": result.model_used, "inline": True},
        ]
        if snap.truncated:
            blocks.append({
                "title": "주의",
                "value": "한도 초과로 일부 파일만 리뷰했어요. 정밀 리뷰는 `/code branch` (diff) 권장.",
                "inline": False,
            })
        return {
            "ok": True,
            "summary": result.text,
            "cost_krw": result.cost_krw,
            "blocks": blocks,
        }


__all__ = ["CodeInternalHandlers"]
