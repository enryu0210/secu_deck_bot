"""스캔/PR/Feature 결과 → 사람이 읽을 한국어 리포트 문자열 (템플릿).

LLM 호출 없음. 모든 텍스트는 정적 템플릿 + 결과값 포매팅.
ui.py 가 이 문자열을 임베드 description 에 그대로 삽입한다.

빌드 가이드(07_ARGOS_SELF_AUDIT.md § 시나리오 1~3) 의 예시 톤·구조와 일치하도록 작성.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from argos_self_audit.compliance_mapper import ComplianceMap
from argos_self_audit.dependency_checker import DependencyReport, CVEFinding
from argos_self_audit.repo_scanner import Finding, ScanResult


# 디스코드 임베드 description 한도 4096. 안전 마진을 두고 잘라냄.
_DESC_SAFE_LIMIT = 3800


@dataclass
class RenderedReport:
    """ui.py 가 임베드로 변환할 표준 리포트."""

    title: str
    body: str
    severity: str = "INFO"     # "INFO" | "WARN" | "CRIT" — 임베드 색 결정
    footer: str = ""


# ---------------------------------------------------------------------
# 일일 스캔 리포트
# ---------------------------------------------------------------------
def render_daily(scan: ScanResult, deps: DependencyReport) -> RenderedReport:
    """매일 03:00 cron 결과 → 한 임베드짜리 요약."""
    today = datetime.now().strftime("%Y-%m-%d")
    sev = _overall_severity(scan, deps)

    sections = [
        f"**📋 Daily Self-Audit — {today}**",
        f"_(commit: `{scan.commit_sha or '?'}`, scanned files: {scan.scanned_files}, took {scan.duration_seconds:.1f}s)_",
        "",
        "**[코드베이스 스캔 결과]**",
        _line("하드코딩된 시크릿", scan.secret_findings),
        _line("PII 누출 패턴", scan.pii_findings),
        _line("KISA 가이드라인 위반", scan.kisa_findings),
        _line("레거시 코드 잔존", scan.legacy_findings, top_files=2),
        _coverage_line(scan),
        "",
        "**[의존성 보안]**",
        *_dep_lines(deps),
        "",
        "**[Action]**",
        *_action_items(scan, deps),
    ]
    if scan.errors:
        sections.append("")
        sections.append("**[스캔 중 오류]**")
        for e in scan.errors[:3]:
            sections.append(f"- {e}")

    body = _join_truncate(sections)
    return RenderedReport(
        title=f"📋 Daily Self-Audit ({today})",
        body=body,
        severity=sev,
        footer="자동화된 1차 검사입니다. 모든 사고를 잡지 못할 수 있어요. 분기별 외부 펜테스트로 보완하세요.",
    )


# ---------------------------------------------------------------------
# PR 자동 검토 리포트 (Code Sentinel 위임 결과 + 룰베이스 컴플라이언스 매핑)
# ---------------------------------------------------------------------
def render_pr_review(
    *,
    pr_url: str,
    pr_title: str,
    pr_branch: str,
    sentinel_summary: str,
    sentinel_findings_count: int,
    compliance: ComplianceMap,
) -> RenderedReport:
    sev = "CRIT" if compliance.risk_scenarios else (
        "WARN" if sentinel_findings_count > 0 else "INFO"
    )

    sections = [
        f"**🔍 PR 자동 검토 — `{pr_branch}`**",
        f"[{pr_title}]({pr_url})",
        "",
        "**[Code Sentinel 위임 결과]**",
        sentinel_summary[:1500] if sentinel_summary else "_(요약 없음)_",
        "",
    ]
    if compliance.matched_articles:
        sections.append("**[컴플라이언스 매핑]**")
        sections.append("이 PR 이 키워드 기준으로 영향 줄 수 있는 영역:")
        for art in compliance.matched_articles[:6]:
            sections.append(f"- {art.title}")
        sections.append("")

    if compliance.risk_scenarios:
        sections.append("**[Self-Audit 결론]**")
        sections.append("🔴 **머지 차단 권장** — 다음 영역에서 권장 미준수 가능성:")
        for r in compliance.risk_scenarios[:5]:
            sections.append(f"- {r}")
    elif sentinel_findings_count > 0:
        sections.append("**[Self-Audit 결론]**")
        sections.append(f"🟠 머지 전 검토 권장 — Code Sentinel 가 {sentinel_findings_count}건 발견.")
    else:
        sections.append("**[Self-Audit 결론]**")
        sections.append("✅ 룰베이스 1차 통과. 코드 리뷰는 정성 점검을 추가로.")

    body = _join_truncate(sections)
    return RenderedReport(
        title=f"🔍 PR 자동 검토 — {pr_branch}",
        body=body,
        severity=sev,
        footer=f"PR: {pr_url}",
    )


# ---------------------------------------------------------------------
# Feature 컴플라이언스 매핑 리포트 (/audit feature)
# ---------------------------------------------------------------------
def render_feature(compliance: ComplianceMap, prd_excerpt: str) -> RenderedReport:
    if not compliance.matched_articles:
        return RenderedReport(
            title="📋 Feature Compliance Map",
            body=(
                "**키워드 기준으로 매칭된 조항이 없습니다.**\n\n"
                "옵션 B (LLM 미사용) 정책상 매핑은 키워드 기반이라 의역된 표현은 놓칠 수 있어요.\n"
                "PRD 에 다음 단어를 명시하면 정확도가 올라갑니다: '수집/동의/보유기간/암호화/제3자 제공/탈퇴/유출'.\n\n"
                f"_(분석한 PRD 발췌)_\n> {prd_excerpt[:300]}"
            ),
            severity="INFO",
            footer="법률 자문 아님. 의역 매핑이 필요하면 변호사 검토 권장.",
        )

    sections = [
        "**📋 Feature Compliance Map**",
        "",
        "**[관련 법령·표준]**",
    ]
    for art in compliance.matched_articles[:8]:
        sections.append(f"- **{art.title}**")
        sections.append(f"  {art.summary}")
        if art.matched_keywords:
            sections.append(f"  _매칭된 키워드_: {', '.join(art.matched_keywords)}")
        if art.missing_requirements:
            sections.append(f"  ⚠️ PRD 누락 의심: {', '.join(art.missing_requirements)}")
    sections.append("")

    if compliance.implementation_checklist:
        sections.append("**[구현 체크리스트]**")
        for c in compliance.implementation_checklist[:12]:
            sections.append(f"☐ {c}")
        sections.append("")

    if compliance.risk_scenarios:
        sections.append("**[위험 시나리오]**")
        for r in compliance.risk_scenarios[:6]:
            sections.append(f"- {r}")

    body = _join_truncate(sections)
    sev = "CRIT" if compliance.risk_scenarios else "WARN"
    return RenderedReport(
        title="📋 Feature Compliance Map",
        body=body,
        severity=sev,
        footer="키워드 기반 매핑이라 누락 가능. 법률 자문 아님.",
    )


# ---------------------------------------------------------------------
# 즉시 스캔 리포트 (/audit scan) — daily 와 본문 동일하지만 제목·푸터만 다름
# ---------------------------------------------------------------------
def render_immediate_scan(scan: ScanResult, deps: DependencyReport) -> RenderedReport:
    base = render_daily(scan, deps)
    return RenderedReport(
        title=f"🔍 즉시 스캔 결과 ({datetime.now().strftime('%H:%M')})",
        body=base.body,
        severity=base.severity,
        footer="즉시 실행 — 다음 정기 스캔은 매일 03:00 KST.",
    )


# ---------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------
def _line(label: str, findings: list[Finding], *, top_files: int = 0) -> str:
    if not findings:
        return f"✅ {label}: 0건"
    crit = sum(1 for f in findings if f.severity == "CRITICAL")
    high = sum(1 for f in findings if f.severity == "HIGH")
    med = sum(1 for f in findings if f.severity == "MED")
    low = sum(1 for f in findings if f.severity == "LOW")
    parts = [f"{label}: **{len(findings)}건**"]
    sev_parts = []
    if crit:
        sev_parts.append(f"CRITICAL {crit}")
    if high:
        sev_parts.append(f"HIGH {high}")
    if med:
        sev_parts.append(f"MED {med}")
    if low:
        sev_parts.append(f"LOW {low}")
    icon = "🔴" if crit else ("🟠" if high else ("🟡" if med else "ℹ️"))
    line = f"{icon} {parts[0]} ({', '.join(sev_parts)})"
    if top_files > 0:
        files = Counter(f.file_path for f in findings).most_common(top_files)
        if files:
            line += "\n  _주요 파일_: " + ", ".join(f"`{p}`" for p, _ in files)
    return line


def _coverage_line(scan: ScanResult) -> str:
    cov = scan.coverage
    if cov.percent is None:
        return "ℹ️ 단위 테스트 커버리지: N/A (coverage.xml 미발견)"
    icon = "✅" if cov.percent >= cov.target_percent else "⚠️"
    return (
        f"{icon} 단위 테스트 커버리지: {cov.percent:.1f}% "
        f"(목표 {cov.target_percent:.0f}%, 출처 {cov.source})"
    )


def _dep_lines(deps: DependencyReport) -> list[str]:
    if not deps.available:
        return [f"ℹ️ 의존성 검사: skip ({deps.error or 'osv-scanner 미설치'})"]
    if deps.error:
        return [f"⚠️ 의존성 검사 오류: {deps.error}"]
    if not deps.findings:
        return ["✅ 의존성 CVE: 0건"]

    out = [f"🔴 의존성 CVE: **{len(deps.findings)}건** (CRITICAL {deps.critical_count}, HIGH {deps.high_count})"]
    for f in deps.findings[:5]:
        out.append(f"- {f.short()}")
    if len(deps.findings) > 5:
        out.append(f"_(+{len(deps.findings) - 5} more)_")
    return out


def _action_items(scan: ScanResult, deps: DependencyReport) -> list[str]:
    """우선순위 액션 — CRITICAL 먼저, 그다음 HIGH, 그다음 의존성, 그다음 레거시."""
    actions: list[str] = []
    crit_findings = [
        f for f in (
            *scan.secret_findings,
            *scan.pii_findings,
            *scan.kisa_findings,
        ) if f.severity == "CRITICAL"
    ]
    for f in crit_findings[:3]:
        actions.append(f"🔴 {f.short()} — {f.suggestion}")

    crit_cves = [c for c in deps.findings if c.severity == "CRITICAL"]
    for c in crit_cves[:3]:
        actions.append(f"🔴 {c.short()} 즉시 업그레이드 — {c.summary[:120]}")

    if not actions:
        if scan.legacy_findings:
            actions.append(f"🟡 레거시 코드 정리 일정 잡기 ({len(scan.legacy_findings)}건)")
        else:
            actions.append("✅ 즉시 액션 없음. 다음 스캔 대기.")
    return actions


def _overall_severity(scan: ScanResult, deps: DependencyReport) -> str:
    if scan.critical_count > 0 or deps.critical_count > 0:
        return "CRIT"
    if any(f.severity == "HIGH" for f in (
        *scan.secret_findings, *scan.pii_findings, *scan.kisa_findings,
    )) or deps.high_count > 0:
        return "WARN"
    return "INFO"


def _join_truncate(lines: Iterable[str]) -> str:
    text = "\n".join(lines)
    if len(text) <= _DESC_SAFE_LIMIT:
        return text
    return text[: _DESC_SAFE_LIMIT - 4] + "\n…"


__all__ = [
    "render_daily",
    "render_pr_review",
    "render_feature",
    "render_immediate_scan",
    "RenderedReport",
]
