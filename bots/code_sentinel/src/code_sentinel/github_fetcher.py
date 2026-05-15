"""GitHub PR URL → diff + 변경 파일 내용.

GitHub PAT 은 ``GITHUB_PAT`` 환경변수에서 읽음. read-only 권한만 부여할 것.

지원 시나리오:
- PR URL (``fetch``)               — 기존 ``/code review pr_url:...``
- 브랜치 ↔ base diff (``fetch_branch_diff``) — ``/code branch``
- 브랜치 전체 스냅샷 (``fetch_branch_snapshot``) — ``/code branch_full``
"""
from __future__ import annotations

import io
import os
import re
import tarfile
from dataclasses import dataclass, field

import httpx

from sd_core.utils.errors import ConfigError, SecuDeckError
from sd_core.utils.logger import get_logger


_log = get_logger("code_sentinel.github_fetcher")

# https://github.com/owner/repo/pull/123 패턴
_PR_URL_RE = re.compile(
    r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
)

# ``owner/repo`` 형식 검증 — GitHub 가 허용하는 문자만 (영문/숫자/.-_)
_REPO_SPEC_RE = re.compile(r"^([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)$")

# 브랜치 스냅샷에서 받을 텍스트 확장자 화이트리스트.
# argos repo_scanner 와 의도적으로 분리 — 그쪽은 룰베이스 스캐너, 여기는 LLM 리뷰용.
# LLM 컨텍스트 비용 때문에 argos 보다 좁게 가져간다.
_SNAPSHOT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".sql",
    ".yaml", ".yml", ".json", ".toml",
    ".sh", ".ps1",
    ".md",  # README 등 docs 는 KISA 정합성 평가에 도움
}

# 스냅샷에서 무조건 제외하는 경로 조각 — 잡음·자동생성·서드파티.
_SNAPSHOT_PATH_EXCLUDE = (
    "/.git/", "/node_modules/", "/__pycache__/", "/.venv/", "/venv/",
    "/dist/", "/build/", "/.next/", "/target/", "/.idea/", "/.vscode/",
    "/vendor/", "/.cache/",
)

# 단일 파일 크기 상한 — LLM 컨텍스트 토큰 보호 (argos 는 1MB 지만 우리는 LLM 입력이라 훨씬 작게).
_SNAPSHOT_MAX_FILE_BYTES = 64 * 1024

# tarball 다운로드 자체의 압축 해제 전 raw 크기 상한 — 메모리 보호.
# 일반 작업 레포(수 MB)는 충분히 통과. 거대 모노레포는 거절.
_SNAPSHOT_MAX_TARBALL_BYTES = 50 * 1024 * 1024


@dataclass
class PRContent:
    """PR 내용 구조."""

    repo: str            # "owner/repo"
    number: int
    title: str
    body: str
    diff: str            # unified diff (커지면 절단)
    changed_files: list[str]


@dataclass
class BranchDiff:
    """브랜치 ↔ base 비교 결과 (PRContent 의 PR-less 버전)."""

    repo: str            # "owner/repo"
    branch: str
    base: str            # 비교 기준 — 명시 입력 또는 default_branch 자동 감지
    diff: str            # unified diff (커지면 절단)
    changed_files: list[str]
    ahead_by: int        # base 대비 앞선 커밋 수 (참고용)

    def to_review_prompt(self) -> str:
        """리뷰 LLM 에 넣을 markdown 본문 — commands·internal_handlers 공용."""
        return (
            f"# {self.repo} — `{self.base}` ... `{self.branch}` "
            f"(ahead {self.ahead_by} commits)\n\n"
            f"## 변경 파일 ({len(self.changed_files)})\n"
            + "\n".join(f"- {f}" for f in self.changed_files)
            + "\n\n## diff\n"
            + self.diff
        )


@dataclass
class FileBlob:
    """스냅샷 안의 단일 파일."""

    path: str            # 레포 루트 기준 상대경로 (POSIX)
    content: str


@dataclass
class BranchSnapshot:
    """브랜치 전체 스냅샷 — 화이트리스트 확장자 + 상한 적용 결과."""

    repo: str            # "owner/repo"
    branch: str
    files: list[FileBlob] = field(default_factory=list)
    # 상한(파일 수·총 바이트)에 걸려 일부 누락되었는지 — UI 에 경고 노출용
    truncated: bool = False
    total_bytes: int = 0

    def to_review_prompt(self) -> str:
        """리뷰 LLM 에 넣을 markdown 본문 (파일 블록 결합) — commands·internal_handlers 공용."""
        head = (
            f"# {self.repo} — branch `{self.branch}` 스냅샷\n"
            f"파일 {len(self.files)}개, 총 {self.total_bytes:,}바이트"
            f"{' (일부 절단됨)' if self.truncated else ''}\n\n"
        )
        blocks: list[str] = [head]
        for blob in self.files:
            blocks.append(f"## file: {blob.path}\n```\n{blob.content}\n```\n")
        return "\n".join(blocks)


class GitHubFetchError(SecuDeckError):
    """GitHub fetch 실패 — 첫 인자를 그대로 사용자 메시지로도 노출.

    부모(``SecuDeckError``) 는 ``user_message`` 미지정 시 ``default_user_message``
    로 폴백한다. 하지만 GitHub fetch 의 디버그 메시지는 모두 보안상 안전한
    표준 정보(상태코드/브랜치명/권한 안내)뿐이라, 사용자에게 그대로 노출해
    정확한 원인을 즉시 알 수 있게 한다. (default 로 떨어지면 'URL 또는 권한을
    확인해 주세요' 같은 두루뭉술한 메시지가 나와 디버깅이 어려워진다.)
    """

    default_user_message = "GitHub 가져오기에 실패했어요. URL 또는 권한을 확인해 주세요."

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message, user_message=user_message or message)


def _extract_github_message(resp: httpx.Response) -> str | None:
    """GitHub 4xx 응답의 ``message`` 필드만 안전하게 추출.

    응답 본문 전체는 인증 헤더 fragment 가 섞일 위험 등으로 노출 금지.
    ``message`` 필드는 GitHub 가 공식적으로 사용자 안내용으로 두는 값 — 노출 안전.
    예: "Bad credentials" / "Not Found" / "API rate limit exceeded for ..."
    """
    try:
        body = resp.json()
    except (ValueError, TypeError):
        return None
    if isinstance(body, dict):
        m = body.get("message")
        if isinstance(m, str) and m:
            return m[:200]
    return None


def _diagnose_status(status: int, github_msg: str | None, scope: str) -> str:
    """상태코드별 사용자 친화 진단 메시지.

    403 을 일률적으로 '브랜치명 확인' 으로 안내하면 잘못된 곳을 의심하게 만든다.
    GitHub 의 의미를 그대로 살려 권한·rate limit·존재 여부를 구분해 노출.
    """
    suffix = f" — GitHub: \"{github_msg}\"" if github_msg else ""
    if status == 401:
        return (
            f"{scope} 실패 (401, 인증 오류). GITHUB_PAT 가 유효한지 또는 "
            f"만료되지 않았는지 확인해 주세요.{suffix}"
        )
    if status == 403:
        return (
            f"{scope} 실패 (403, 권한 부족 또는 rate limit). "
            f"private 레포라면 GITHUB_PAT 에 'repo' (classic) 또는 'Contents: Read' "
            f"(fine-grained) 권한이 있어야 해요. PAT 미설정이라면 시간당 60회 "
            f"rate limit 가능성 — 잠시 후 재시도하거나 PAT 를 설정해 주세요.{suffix}"
        )
    if status == 404:
        return (
            f"{scope} 실패 (404, 리소스 없음). 레포·브랜치 이름 오타 또는 "
            f"private 레포에 PAT 미설정 가능성.{suffix}"
        )
    return f"{scope} 실패 ({status}).{suffix}"


class GitHubFetcher:
    """GitHub REST API 로 PR / 브랜치 diff / 브랜치 스냅샷을 가져옴."""

    API_BASE = "https://api.github.com"

    def __init__(self, pat: str | None = None, default_repo: str | None = None):
        self.pat = pat or os.getenv("GITHUB_PAT")
        # default_repo 는 ``owner/repo`` 형식. 슬래시 커맨드에서 repo 옵션 생략 시 대체.
        # 환경변수 보다 생성자 인자가 우선.
        self.default_repo = default_repo or os.getenv("CODE_SENTINEL_DEFAULT_REPO")
        if self.default_repo and not _REPO_SPEC_RE.match(self.default_repo):
            # 부팅은 막지 않되 명확히 경고 — 잘못된 값이 들어와도 슬래시 입력으로 회복 가능
            _log.warning(
                "default_repo_invalid_format",
                value=self.default_repo,
                hint="CODE_SENTINEL_DEFAULT_REPO 는 'owner/repo' 형식이어야 합니다",
            )
            self.default_repo = None
        if not self.pat:
            # 토큰이 없으면 public repo 만 가능. 부팅은 막지 않음.
            _log.warning("github_pat_missing", note="public repo 만 접근 가능")

    # -----------------------------------------------------------------
    # 공통 유틸
    # -----------------------------------------------------------------
    def _resolve_repo(self, repo: str | None) -> tuple[str, str]:
        """슬래시 입력 repo 가 비면 default_repo 사용. 둘 다 없으면 명확히 에러.

        반환: (owner, name)
        """
        spec = (repo or "").strip() or self.default_repo
        if not spec:
            raise GitHubFetchError(
                "리뷰할 레포가 지정되지 않았어요. repo: 옵션을 입력하거나 "
                "CODE_SENTINEL_DEFAULT_REPO 환경변수를 설정해 주세요."
            )
        m = _REPO_SPEC_RE.match(spec)
        if not m:
            raise GitHubFetchError(
                f"레포 형식이 잘못됐어요 ('owner/repo' 만 허용): {spec}"
            )
        return m.group(1), m.group(2)

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        h = {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.pat:
            h["Authorization"] = f"Bearer {self.pat}"
        return h

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
                # 응답 본문은 로그에만 — 사용자 메시지에는 노출 금지(인증 헤더 fragment 등 안전).
                _log.warning(
                    "pr_meta_fetch_failed",
                    status=meta_resp.status_code,
                    body=meta_resp.text[:200],
                )
                raise GitHubFetchError(
                    f"PR 메타 조회 실패 ({meta_resp.status_code}). URL·권한을 확인해 주세요."
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

    # -----------------------------------------------------------------
    # 브랜치 ↔ base diff (PR 없이 비교)
    # -----------------------------------------------------------------
    async def _get_default_branch(
        self, client: httpx.AsyncClient, owner: str, repo: str
    ) -> str:
        """레포의 기본 브랜치명 조회 — base 미지정 시 fallback 용도."""
        resp = await client.get(
            f"{self.API_BASE}/repos/{owner}/{repo}",
            headers=self._headers(),
        )
        if resp.status_code >= 400:
            _log.warning(
                "repo_meta_failed",
                status=resp.status_code,
                owner=owner, repo=repo,
                body=resp.text[:300],
            )
            raise GitHubFetchError(
                _diagnose_status(resp.status_code, _extract_github_message(resp), "레포 조회")
            )
        return resp.json().get("default_branch") or "main"

    async def fetch_branch_diff(
        self,
        repo: str | None,
        branch: str,
        base: str | None = None,
        *,
        max_diff_chars: int = 50000,
    ) -> BranchDiff:
        """선택 브랜치와 base 브랜치 사이의 diff + 변경 파일을 가져온다.

        - ``repo`` 미입력 시 ``CODE_SENTINEL_DEFAULT_REPO`` fallback
        - ``base`` 미입력 시 레포의 default_branch 자동 사용
        - diff 가 ``max_diff_chars`` 를 넘으면 끝을 절단 (LLM 토큰 보호)
        """
        owner, name = self._resolve_repo(repo)
        branch = (branch or "").strip()
        if not branch:
            raise GitHubFetchError("branch 가 비어 있어요.")

        async with httpx.AsyncClient(timeout=20.0) as client:
            # 1) base 자동 감지 (필요 시)
            base_branch = (base or "").strip()
            if not base_branch:
                base_branch = await self._get_default_branch(client, owner, name)

            # base 와 branch 가 같으면 비교 의미 없음
            if base_branch == branch:
                raise GitHubFetchError(
                    f"base 와 branch 가 같아요 ({branch}). 다른 브랜치를 지정해 주세요."
                )

            # 2) compare 메타 (변경 파일 목록 + ahead_by)
            compare_url = (
                f"{self.API_BASE}/repos/{owner}/{name}/compare/"
                f"{base_branch}...{branch}"
            )
            meta_resp = await client.get(compare_url, headers=self._headers())
            if meta_resp.status_code >= 400:
                _log.warning(
                    "branch_compare_failed",
                    status=meta_resp.status_code,
                    owner=owner, repo=name,
                    branch=branch, base=base_branch,
                    body=meta_resp.text[:300],
                )
                raise GitHubFetchError(
                    _diagnose_status(
                        meta_resp.status_code,
                        _extract_github_message(meta_resp),
                        "브랜치 비교",
                    )
                )
            meta = meta_resp.json()
            changed = [f["filename"] for f in (meta.get("files") or [])][:30]
            ahead = int(meta.get("ahead_by") or 0)

            # 3) diff (Accept 헤더 변경)
            diff_resp = await client.get(
                compare_url,
                headers=self._headers("application/vnd.github.v3.diff"),
            )
            if diff_resp.status_code >= 400:
                _log.warning(
                    "branch_diff_failed",
                    status=diff_resp.status_code,
                    owner=owner, repo=name,
                    branch=branch, base=base_branch,
                    body=diff_resp.text[:300],
                )
                raise GitHubFetchError(
                    _diagnose_status(
                        diff_resp.status_code,
                        _extract_github_message(diff_resp),
                        "브랜치 diff 조회",
                    )
                )
            diff_text = diff_resp.text
            if len(diff_text) > max_diff_chars:
                diff_text = diff_text[:max_diff_chars] + "\n\n[...diff 절단...]"

        return BranchDiff(
            repo=f"{owner}/{name}",
            branch=branch,
            base=base_branch,
            diff=diff_text,
            changed_files=changed,
            ahead_by=ahead,
        )

    # -----------------------------------------------------------------
    # 브랜치 전체 스냅샷 (tarball)
    # -----------------------------------------------------------------
    async def fetch_branch_snapshot(
        self,
        repo: str | None,
        branch: str,
        *,
        max_files: int = 30,
        max_total_bytes: int = 200_000,
    ) -> BranchSnapshot:
        """브랜치의 텍스트 소스 파일들을 tarball 로 받아 스냅샷 구성.

        화이트리스트 확장자·경로 제외·파일/총 크기 상한 적용.
        한도 초과 시 잘라낸 뒤 ``truncated=True`` 로 표시 — UI 가 사용자에게 경고.
        """
        owner, name = self._resolve_repo(repo)
        branch = (branch or "").strip()
        if not branch:
            raise GitHubFetchError("branch 가 비어 있어요.")

        # GitHub tarball 엔드포인트는 302 → codeload.github.com 으로 리다이렉트
        tarball_url = f"{self.API_BASE}/repos/{owner}/{name}/tarball/{branch}"

        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
        ) as client:
            resp = await client.get(tarball_url, headers=self._headers())
            if resp.status_code >= 400:
                _log.warning(
                    "branch_tarball_failed",
                    status=resp.status_code,
                    owner=owner, repo=name, branch=branch,
                    body=resp.text[:300],
                )
                raise GitHubFetchError(
                    _diagnose_status(
                        resp.status_code,
                        _extract_github_message(resp),
                        "브랜치 tarball 다운로드",
                    )
                )
            raw = resp.content

        if len(raw) > _SNAPSHOT_MAX_TARBALL_BYTES:
            raise GitHubFetchError(
                f"브랜치가 너무 커요 ({len(raw) // (1024 * 1024)}MB). "
                "LLM 리뷰 범위를 넘었어요 — 특정 파일이나 PR 단위 리뷰를 사용해 주세요."
            )

        files: list[FileBlob] = []
        total_bytes = 0
        truncated = False

        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue

                    # tarball 안의 경로는 ``<owner>-<repo>-<sha>/path/to/file`` 형태.
                    # 첫 디렉토리 prefix 제거해서 레포 루트 기준 상대경로로 만듦.
                    parts = member.name.split("/", 1)
                    if len(parts) < 2 or not parts[1]:
                        continue
                    rel_path = parts[1]

                    # 경로 화이트리스트 / 블랙리스트
                    posix_check = "/" + rel_path
                    if any(seg in posix_check for seg in _SNAPSHOT_PATH_EXCLUDE):
                        continue
                    ext = ""
                    if "." in rel_path.rsplit("/", 1)[-1]:
                        ext = "." + rel_path.rsplit(".", 1)[-1].lower()
                    if ext not in _SNAPSHOT_EXTS:
                        continue

                    # 단일 파일 크기 상한 — LLM 토큰 보호
                    if member.size > _SNAPSHOT_MAX_FILE_BYTES:
                        continue

                    # 누적 한도 도달 → 잘라내고 종료
                    if (
                        len(files) >= max_files
                        or total_bytes + member.size > max_total_bytes
                    ):
                        truncated = True
                        break

                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    try:
                        content = f.read().decode("utf-8")
                    except UnicodeDecodeError:
                        # 바이너리·인코딩 다른 파일은 건너뜀
                        continue

                    files.append(FileBlob(path=rel_path, content=content))
                    total_bytes += member.size
        except tarfile.TarError as exc:
            raise GitHubFetchError(
                f"tarball 해제 실패: {exc}"
            ) from exc

        return BranchSnapshot(
            repo=f"{owner}/{name}",
            branch=branch,
            files=files,
            truncated=truncated,
            total_bytes=total_bytes,
        )
