"""GitHub PR URL → diff + 변경 파일 내용.

GitHub PAT 은 ``GITHUB_PAT`` 환경변수에서 읽음. read-only 권한만 부여할 것.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

from sd_core.utils.errors import ConfigError, SecuDeckError
from sd_core.utils.logger import get_logger


_log = get_logger("code_sentinel.github_fetcher")

# https://github.com/owner/repo/pull/123 패턴
_PR_URL_RE = re.compile(
    r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
)


@dataclass
class PRContent:
    """PR 내용 구조."""

    repo: str            # "owner/repo"
    number: int
    title: str
    body: str
    diff: str            # unified diff (커지면 절단)
    changed_files: list[str]


class GitHubFetchError(SecuDeckError):
    default_user_message = "GitHub PR 가져오기에 실패했어요. URL 또는 권한을 확인해 주세요."


class GitHubFetcher:
    """GitHub REST API 로 PR diff 를 가져옴."""

    API_BASE = "https://api.github.com"

    def __init__(self, pat: str | None = None):
        self.pat = pat or os.getenv("GITHUB_PAT")
        if not self.pat:
            # 토큰이 없으면 public repo 만 가능. 부팅은 막지 않음.
            _log.warning("github_pat_missing", note="public repo 만 접근 가능")

    @staticmethod
    def parse_url(url: str) -> tuple[str, str, int] | None:
        m = _PR_URL_RE.match(url.strip())
        if not m:
            return None
        return m.group(1), m.group(2), int(m.group(3))

    async def fetch(self, pr_url: str, max_diff_chars: int = 50000) -> PRContent:
        parsed = self.parse_url(pr_url)
        if parsed is None:
            raise GitHubFetchError(f"GitHub PR URL 형식이 아니에요: {pr_url}")
        owner, repo, number = parsed

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.pat:
            headers["Authorization"] = f"Bearer {self.pat}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1) PR 메타
            meta_resp = await client.get(
                f"{self.API_BASE}/repos/{owner}/{repo}/pulls/{number}",
                headers=headers,
            )
            if meta_resp.status_code >= 400:
                raise GitHubFetchError(
                    f"PR 메타 조회 실패 ({meta_resp.status_code}): {meta_resp.text[:200]}"
                )
            meta = meta_resp.json()

            # 2) diff (Accept 헤더 변경)
            diff_resp = await client.get(
                f"{self.API_BASE}/repos/{owner}/{repo}/pulls/{number}",
                headers={**headers, "Accept": "application/vnd.github.v3.diff"},
            )
            if diff_resp.status_code >= 400:
                raise GitHubFetchError(
                    f"PR diff 조회 실패 ({diff_resp.status_code})"
                )
            diff_text = diff_resp.text
            if len(diff_text) > max_diff_chars:
                diff_text = diff_text[:max_diff_chars] + "\n\n[...diff 절단...]"

            # 3) 변경 파일 목록 — 큰 PR 은 다 안 가져오고 30개까지만
            files_resp = await client.get(
                f"{self.API_BASE}/repos/{owner}/{repo}/pulls/{number}/files",
                headers=headers,
                params={"per_page": 30},
            )
            files: list[str] = []
            if files_resp.status_code < 400:
                files = [f["filename"] for f in files_resp.json()]

        return PRContent(
            repo=f"{owner}/{repo}",
            number=number,
            title=meta.get("title", ""),
            body=meta.get("body") or "",
            diff=diff_text,
            changed_files=files,
        )
