"""Argos 레포 룰베이스 스캐너.

설계 결정:
- **LLM 호출 없음** (옵션 B). 모든 finding 은 정규식·경로 휴리스틱으로 산출.
- **mtime 감지로 YAML 자동 재로드** — 봇 재시작 없이 룰 갱신 즉시 반영
  (CLAUDE.md 함정 ⁴ 패턴: ArgosContext / DesignSystem 와 동일).
- **레포는 매 스캔마다 fresh clone/pull**. Railway 컨테이너가 ephemeral 이라 일관 동작.
- **false_positive_excludes** YAML 의 path_substrings 로 테스트·docs 디렉토리 자동 제외.

스캔 대상 파일 확장자는 ``_SCAN_EXTS`` 에 화이트리스트로 정의 — 바이너리·노이즈 제거.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sd_core.utils.errors import ConfigError, SecuDeckError
from sd_core.utils.logger import get_logger


_log = get_logger("argos_self_audit.repo_scanner")


# 스캔 대상 텍스트 확장자. 바이너리·이미지·미디어 제외.
# 너무 넓히면 false positive·시간 비용↑, 너무 좁히면 누락↑ — 대표 언어·설정파일 위주.
_SCAN_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".sql",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".env", ".sh", ".ps1", ".dockerfile",
    ".md",  # README/docs 도 스캔 (시크릿이 docs 에 묻혀 들어가는 사고 흔함)
}

# 스캔에서 무조건 제외하는 경로 조각 (잡음 + 시간 절감).
_HARD_EXCLUDE = (
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/.venv/",
    "/venv/",
    "/dist/",
    "/build/",
    "/.next/",
    "/target/",
    "/.idea/",
    "/.vscode/",
)

# 1 MB 초과 파일은 스킵 (대용량 lockfile·minified JS 등).
_MAX_FILE_BYTES = 1 * 1024 * 1024


@dataclass
class Finding:
    """스캔 결과 단일 항목."""

    rule_id: str
    severity: str            # CRITICAL / HIGH / MED / LOW
    description: str
    file_path: str           # 레포 루트 기준 상대경로 (POSIX)
    line_number: int | None
    matched_text: str        # 최대 120자
    suggestion: str
    category: str            # "secret" | "pii" | "kisa" | "legacy"

    def short(self) -> str:
        loc = f"{self.file_path}:{self.line_number}" if self.line_number else self.file_path
        return f"[{self.severity}] {self.rule_id} @ {loc}"


@dataclass
class CoverageInfo:
    """테스트 커버리지 정보 (coverage.xml/json 있을 때만 채움)."""

    percent: float | None = None
    target_percent: float = 80.0
    source: str = "unknown"   # "coverage.xml" | "coverage.json" | "unknown"


@dataclass
class ScanResult:
    """레포 스캔 종합 결과."""

    repo_url: str
    commit_sha: str | None
    secret_findings: list[Finding] = field(default_factory=list)
    pii_findings: list[Finding] = field(default_factory=list)
    kisa_findings: list[Finding] = field(default_factory=list)
    legacy_findings: list[Finding] = field(default_factory=list)
    coverage: CoverageInfo = field(default_factory=CoverageInfo)
    scanned_files: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return (
            len(self.secret_findings)
            + len(self.pii_findings)
            + len(self.kisa_findings)
            + len(self.legacy_findings)
        )

    @property
    def critical_count(self) -> int:
        return sum(
            1
            for f in (
                *self.secret_findings,
                *self.pii_findings,
                *self.kisa_findings,
                *self.legacy_findings,
            )
            if f.severity == "CRITICAL"
        )


# ---------------------------------------------------------------------
# 룰 로더 — mtime 감지로 자동 재로드.
# ---------------------------------------------------------------------
class _RuleSet:
    """단일 YAML 파일에서 patterns + excludes 로드."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime: float = 0.0
        self.patterns: list[dict[str, Any]] = []
        self.legacy_paths: list[str] = []
        self.exclude_substrings: list[str] = []
        self._compiled_regex: dict[str, re.Pattern[str]] = {}
        self._compiled_co_occur: dict[str, tuple[re.Pattern[str], re.Pattern[str] | None]] = {}
        self._reload_if_stale()

    def _reload_if_stale(self) -> None:
        if not self.path.exists():
            raise ConfigError(f"룰 파일 없음: {self.path}")
        mtime = self.path.stat().st_mtime
        if mtime == self._mtime:
            return
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML 파싱 실패: {self.path} — {exc}") from exc

        self.patterns = list(data.get("patterns", []) or [])
        self.legacy_paths = list(data.get("legacy_paths", []) or [])

        excludes = data.get("false_positive_excludes") or {}
        self.exclude_substrings = [s.lower() for s in (excludes.get("path_substrings") or [])]

        # 정규식 컴파일 캐시 — 매 파일 매 룰마다 재컴파일 회피.
        self._compiled_regex.clear()
        self._compiled_co_occur.clear()
        for rule in self.patterns:
            rid = str(rule.get("id") or "?")
            regex = rule.get("regex")
            if regex:
                try:
                    self._compiled_regex[rid] = re.compile(regex, re.MULTILINE)
                except re.error as exc:
                    _log.warning("rule_regex_invalid", rule_id=rid, error=str(exc))
            co = rule.get("regex_co_occur") or {}
            must = co.get("must_match")
            must_not = co.get("must_not_match")
            if must:
                try:
                    self._compiled_co_occur[rid] = (
                        re.compile(must, re.MULTILINE),
                        re.compile(must_not, re.MULTILINE) if must_not else None,
                    )
                except re.error as exc:
                    _log.warning("rule_co_occur_invalid", rule_id=rid, error=str(exc))

        self._mtime = mtime
        _log.info("ruleset_loaded", path=str(self.path), patterns=len(self.patterns))

    def patterns_with_compiled(self) -> list[tuple[dict[str, Any], re.Pattern[str] | None, tuple | None]]:
        self._reload_if_stale()
        result = []
        for rule in self.patterns:
            rid = str(rule.get("id") or "?")
            result.append((
                rule,
                self._compiled_regex.get(rid),
                self._compiled_co_occur.get(rid),
            ))
        return result

    def is_excluded(self, posix_path: str) -> bool:
        self._reload_if_stale()
        low = posix_path.lower()
        return any(s in low for s in self.exclude_substrings)


# ---------------------------------------------------------------------
# 메인 스캐너
# ---------------------------------------------------------------------
class RepoScanner:
    """Argos 레포 clone/pull 후 룰베이스 스캔."""

    def __init__(
        self,
        checks_dir: Path,
        repo_url: str,
        clone_dir: Path,
        github_pat: str | None = None,
    ):
        self.checks_dir = checks_dir
        self.repo_url = repo_url
        self.clone_dir = clone_dir
        self.github_pat = github_pat

        # 4종 룰셋 — mtime 자동 재로드.
        self.secret_rules = _RuleSet(checks_dir / "secret_patterns.yaml")
        self.pii_rules = _RuleSet(checks_dir / "pii_patterns.yaml")
        self.kisa_rules = _RuleSet(checks_dir / "kisa_checks.yaml")
        # pipa 는 룰베이스 스캔이 아니라 PRD 매핑용 — RepoScanner 는 사용 안 함.

    # -----------------------------------------------------------------
    async def scan_all(self) -> ScanResult:
        """레포 fresh clone → 전 파일 스캔 → 결과 집계."""
        import time

        start = time.monotonic()
        result = ScanResult(repo_url=self.repo_url, commit_sha=None)

        try:
            self._ensure_clone()
        except SecuDeckError as exc:
            result.errors.append(f"clone 실패: {exc}")
            result.duration_seconds = time.monotonic() - start
            return result

        result.commit_sha = self._current_sha()

        for finding in self._scan_files():
            if finding.category == "secret":
                result.secret_findings.append(finding)
            elif finding.category == "pii":
                result.pii_findings.append(finding)
            elif finding.category == "kisa":
                result.kisa_findings.append(finding)
            elif finding.category == "legacy":
                result.legacy_findings.append(finding)

        result.scanned_files = self._last_scanned_files
        result.coverage = self._read_coverage()
        result.duration_seconds = time.monotonic() - start
        _log.info(
            "scan_done",
            total=result.total_findings,
            critical=result.critical_count,
            files=result.scanned_files,
            duration=round(result.duration_seconds, 2),
        )
        return result

    # -----------------------------------------------------------------
    # git clone/pull
    # -----------------------------------------------------------------
    def _ensure_clone(self) -> None:
        """클론 디렉토리가 있으면 ``git pull``, 없으면 ``git clone``.

        PAT 가 있으면 ``https://x-access-token:<PAT>@github.com/...`` 형태로 주입.
        PAT 노출 회피를 위해 stderr 는 로그에 안 남김.
        """
        url = self._authed_url()

        if (self.clone_dir / ".git").exists():
            try:
                subprocess.run(
                    ["git", "-C", str(self.clone_dir), "fetch", "--all", "--prune"],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
                subprocess.run(
                    ["git", "-C", str(self.clone_dir), "reset", "--hard", "@{u}"],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                _log.info("repo_pulled", path=str(self.clone_dir))
                return
            except subprocess.CalledProcessError as exc:
                _log.warning("git_pull_failed_will_reclone", returncode=exc.returncode)
                # 손상된 클론은 폐기하고 fresh clone 으로 회복.
                shutil.rmtree(self.clone_dir, ignore_errors=True)
            except subprocess.TimeoutExpired:
                _log.warning("git_pull_timeout_will_reclone")
                shutil.rmtree(self.clone_dir, ignore_errors=True)

        self.clone_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(self.clone_dir)],
                check=True,
                capture_output=True,
                timeout=300,
            )
            _log.info("repo_cloned", path=str(self.clone_dir))
        except subprocess.CalledProcessError as exc:
            raise SecuDeckError(
                f"git clone 실패 (returncode={exc.returncode})",
                user_message="레포 clone 에 실패했어요. ARGOS_REPO_URL/GITHUB_PAT_AUDIT 설정을 확인해 주세요.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SecuDeckError(
                "git clone 타임아웃 (5분 초과)",
                user_message="레포 clone 시간 초과. 다시 시도해 주세요.",
            ) from exc

    def _authed_url(self) -> str:
        """PAT 가 있으면 HTTPS URL 에 주입. PAT 없으면 원본 URL 반환 (public repo)."""
        if not self.github_pat:
            return self.repo_url
        if self.repo_url.startswith("https://github.com/"):
            return self.repo_url.replace(
                "https://github.com/",
                f"https://x-access-token:{self.github_pat}@github.com/",
                1,
            )
        # SSH 또는 다른 프로토콜은 그대로 (PAT 의미 없음).
        return self.repo_url

    def _current_sha(self) -> str | None:
        try:
            out = subprocess.run(
                ["git", "-C", str(self.clone_dir), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                timeout=10,
                text=True,
            )
            return out.stdout.strip()[:12] or None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None

    # -----------------------------------------------------------------
    # 파일 순회 + 룰 적용
    # -----------------------------------------------------------------
    _last_scanned_files: int = 0

    def _scan_files(self) -> list[Finding]:
        findings: list[Finding] = []
        scanned = 0

        for fpath in self.clone_dir.rglob("*"):
            if not fpath.is_file():
                continue
            posix = fpath.as_posix()
            if any(ex in posix for ex in _HARD_EXCLUDE):
                continue
            if fpath.suffix.lower() not in _SCAN_EXTS and fpath.name.lower() not in (".env",):
                continue
            try:
                if fpath.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            scanned += 1
            rel = fpath.relative_to(self.clone_dir).as_posix()
            findings.extend(self._apply_ruleset(content, rel, self.secret_rules, "secret"))
            findings.extend(self._apply_ruleset(content, rel, self.pii_rules, "pii"))
            findings.extend(self._apply_ruleset(content, rel, self.kisa_rules, "kisa"))

        # 레거시 경로 — 별도 패스 (파일 단위가 아니라 경로 패턴 매칭).
        findings.extend(self._scan_legacy_paths())

        self._last_scanned_files = scanned
        return findings

    def _apply_ruleset(
        self,
        content: str,
        rel_path: str,
        ruleset: _RuleSet,
        category: str,
    ) -> list[Finding]:
        if ruleset.is_excluded(rel_path):
            return []

        out: list[Finding] = []
        for rule, compiled, co in ruleset.patterns_with_compiled():
            rid = str(rule.get("id") or "?")
            severity = str(rule.get("severity") or "MED")
            description = str(rule.get("description") or "")
            suggestion = str(rule.get("suggestion") or "")

            if compiled is not None:
                for m in compiled.finditer(content):
                    line_no = content.count("\n", 0, m.start()) + 1
                    out.append(Finding(
                        rule_id=rid,
                        severity=severity,
                        description=description,
                        file_path=rel_path,
                        line_number=line_no,
                        matched_text=_truncate(m.group(0), 120),
                        suggestion=suggestion,
                        category=category,
                    ))

            if co is not None:
                must, must_not = co
                m = must.search(content)
                if m and not (must_not and must_not.search(content)):
                    line_no = content.count("\n", 0, m.start()) + 1
                    out.append(Finding(
                        rule_id=rid,
                        severity=severity,
                        description=description,
                        file_path=rel_path,
                        line_number=line_no,
                        matched_text=_truncate(m.group(0), 120),
                        suggestion=suggestion,
                        category=category,
                    ))
        return out

    def _scan_legacy_paths(self) -> list[Finding]:
        """``kisa_checks.yaml`` 의 ``legacy_paths`` 와 매칭되는 파일·디렉토리를 finding 으로."""
        out: list[Finding] = []
        legacy = self.kisa_rules.legacy_paths
        if not legacy:
            return out
        for fpath in self.clone_dir.rglob("*"):
            if not fpath.is_file():
                continue
            posix = fpath.as_posix()
            if any(ex in posix for ex in _HARD_EXCLUDE):
                continue
            rel = fpath.relative_to(self.clone_dir).as_posix()
            for marker in legacy:
                if marker in rel:
                    out.append(Finding(
                        rule_id="legacy_code",
                        severity="LOW",
                        description=f"레거시 마커 '{marker}' 가 경로에 포함됨",
                        file_path=rel,
                        line_number=None,
                        matched_text=marker,
                        suggestion="레거시 코드 제거 일정을 잡거나, 활성 코드면 마커 이름을 바꿀 것.",
                        category="legacy",
                    ))
                    break
        return out

    # -----------------------------------------------------------------
    # 테스트 커버리지 — coverage.xml/json 이 레포에 커밋돼 있을 때만 사용.
    # 옵션 B 라 LLM 으로 추론하지 않고, 파일이 없으면 그냥 N/A.
    # -----------------------------------------------------------------
    def _read_coverage(self) -> CoverageInfo:
        info = CoverageInfo()
        xml = self.clone_dir / "coverage.xml"
        json_path = self.clone_dir / "coverage.json"
        if xml.exists():
            try:
                # coverage.py 의 cobertura 형식은 root tag 의 line-rate 속성
                content = xml.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'line-rate="([0-9.]+)"', content)
                if m:
                    info.percent = float(m.group(1)) * 100
                    info.source = "coverage.xml"
            except OSError:
                pass
        elif json_path.exists():
            try:
                import json
                data = json.loads(json_path.read_text(encoding="utf-8"))
                pct = data.get("totals", {}).get("percent_covered")
                if pct is not None:
                    info.percent = float(pct)
                    info.source = "coverage.json"
            except (OSError, ValueError):
                pass
        return info


# ---------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------
def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def default_clone_dir() -> Path:
    """Railway/로컬 모두에서 안전한 임시 클론 경로 — 환경변수 override 가능."""
    base = os.getenv("ARGOS_CLONE_DIR")
    if base:
        return Path(base)
    return Path("/tmp") / "argos-self-audit-repo" if os.name != "nt" else Path.cwd() / ".argos-clone"


__all__ = [
    "RepoScanner",
    "ScanResult",
    "Finding",
    "CoverageInfo",
    "default_clone_dir",
]
