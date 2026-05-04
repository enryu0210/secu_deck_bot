"""의존성 CVE 체커 — osv-scanner subprocess 기반 (LLM 없음).

전략:
- ``osv-scanner`` 가 PATH 에 있으면 그것을 사용 (최신 GitHub Advisory + OSV DB).
- 없으면 즉시 비활성화. 폴백 없음 — false positive 도 false negative 도 위험해서 차라리 N/A.
- pip-audit·safety 같은 Python 전용 도구는 다언어 레포(JS/Go 등) 에서 부분만 보게 되므로 폴백 후보 제외.

osv-scanner 가 없는 환경(예: 개발 머신) 에서는 ``available=False`` 로 표시되어
리포트에 "의존성 검사: skip (osv-scanner 미설치)" 로 출력된다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sd_core.utils.logger import get_logger


_log = get_logger("argos_self_audit.dependency_checker")


@dataclass
class CVEFinding:
    """단일 CVE 경고."""

    package: str
    ecosystem: str           # "PyPI" | "npm" | "Go" 등
    installed_version: str
    cve_id: str              # CVE-2025-XXXX 또는 GHSA-...
    severity: str            # CRITICAL / HIGH / MED / LOW / UNKNOWN
    summary: str
    fixed_version: str | None = None

    def short(self) -> str:
        fix = f" → {self.fixed_version}" if self.fixed_version else ""
        return f"[{self.severity}] {self.package} {self.installed_version}{fix} ({self.cve_id})"


@dataclass
class DependencyReport:
    """의존성 스캔 종합 결과."""

    available: bool                          # osv-scanner 가능 여부
    findings: list[CVEFinding] = field(default_factory=list)
    error: str | None = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "HIGH")


# OSV-Scanner 의 severity 표기 정규화.
_SEVERITY_NORMALIZE = {
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MODERATE": "MED",
    "MEDIUM": "MED",
    "LOW": "LOW",
    "": "UNKNOWN",
}


class DependencyChecker:
    """osv-scanner 호출 + JSON 파싱."""

    def __init__(self, *, scanner_bin: str | None = None, timeout_s: int = 180):
        # 명시적 경로가 있으면 그것을 쓰고, 없으면 PATH 에서 찾음.
        self.scanner_bin = scanner_bin or shutil.which("osv-scanner")
        self.timeout_s = timeout_s

    def is_available(self) -> bool:
        return bool(self.scanner_bin)

    async def check(self, repo_path: Path) -> DependencyReport:
        """``repo_path`` 의 의존성 lockfile 들을 osv-scanner 로 검사."""
        if not self.scanner_bin:
            return DependencyReport(
                available=False,
                error="osv-scanner 미설치 — `go install github.com/google/osv-scanner/cmd/osv-scanner@latest`",
            )

        try:
            proc = subprocess.run(
                [self.scanner_bin, "--format", "json", "--recursive", str(repo_path)],
                capture_output=True,
                timeout=self.timeout_s,
                text=True,
            )
        except subprocess.TimeoutExpired:
            return DependencyReport(available=True, error="osv-scanner 타임아웃")
        except OSError as exc:
            return DependencyReport(available=True, error=f"osv-scanner 실행 실패: {exc}")

        # osv-scanner 는 취약점 발견 시 returncode != 0. JSON 출력 자체는 정상.
        # 따라서 returncode 로 실패 판단하지 않고 JSON 파싱 가능 여부로 판단.
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError as exc:
            return DependencyReport(
                available=True,
                error=f"osv-scanner JSON 파싱 실패: {exc} (stderr: {proc.stderr[:200]})",
            )

        findings = list(self._parse_results(data))
        _log.info(
            "osv_scan_done",
            findings=len(findings),
            critical=sum(1 for f in findings if f.severity == "CRITICAL"),
            high=sum(1 for f in findings if f.severity == "HIGH"),
        )
        return DependencyReport(available=True, findings=findings)

    # -----------------------------------------------------------------
    @staticmethod
    def _parse_results(data: dict) -> list[CVEFinding]:
        """osv-scanner v1+ JSON 스키마 — ``results[].packages[].vulnerabilities[]``."""
        out: list[CVEFinding] = []
        for result in data.get("results") or []:
            for pkg in result.get("packages") or []:
                pkg_info = pkg.get("package") or {}
                name = str(pkg_info.get("name") or "?")
                version = str(pkg_info.get("version") or "?")
                ecosystem = str(pkg_info.get("ecosystem") or "?")
                vulns = pkg.get("vulnerabilities") or []
                groups = pkg.get("groups") or []

                # severity 추출 — 우선 groups[].max_severity, 없으면 vuln별 severity[0].score 매핑 시도.
                group_sev = "UNKNOWN"
                for g in groups:
                    cand = (g.get("max_severity") or "").upper()
                    if cand in _SEVERITY_NORMALIZE:
                        group_sev = _SEVERITY_NORMALIZE[cand]
                        break

                for v in vulns:
                    cve_id = str(v.get("id") or "")
                    summary = str(v.get("summary") or v.get("details") or "")[:200]
                    severity = group_sev
                    # vuln 자체에 database_specific.severity 가 있으면 우선
                    spec_sev = (
                        ((v.get("database_specific") or {}).get("severity") or "").upper()
                    )
                    if spec_sev in _SEVERITY_NORMALIZE:
                        severity = _SEVERITY_NORMALIZE[spec_sev]

                    fixed = _extract_fixed_version(v)
                    out.append(CVEFinding(
                        package=name,
                        ecosystem=ecosystem,
                        installed_version=version,
                        cve_id=cve_id or "(unknown)",
                        severity=severity,
                        summary=summary,
                        fixed_version=fixed,
                    ))
        return out


def _extract_fixed_version(vuln: dict) -> str | None:
    """OSV ``affected[].ranges[].events`` 에서 ``fixed`` 이벤트 첫 번째."""
    for aff in vuln.get("affected") or []:
        for rng in aff.get("ranges") or []:
            for ev in rng.get("events") or []:
                if "fixed" in ev:
                    return str(ev["fixed"])
    return None


__all__ = ["DependencyChecker", "DependencyReport", "CVEFinding"]
