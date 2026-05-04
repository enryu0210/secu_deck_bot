"""PRD 텍스트 → 개인정보보호법 조항 매핑 (옵션 B: LLM 호출 없음).

알고리즘:
1. ``pipa_articles.yaml`` 에서 (article_id, keywords[], must_have_in_prd[]) 로드.
2. PRD 본문에 article 의 keyword 가 N개 이상 등장하면 hit.
3. hit 된 article 의 ``must_have_in_prd`` 항목 중 PRD 에 없는 것은 ``missing_requirements`` 로 보고.
4. 위험 시나리오는 article 별 사전 정의 텍스트 (LLM 추론 X).

LLM 매핑 대비 한계:
- "사용자 활동 로그 90일 보관" 같은 명시적 키워드는 잘 잡지만,
- "사용자가 자기 데이터를 내보낼 수 있게 함" → 제35조 (열람권) 같은 의역은 놓칠 수 있음.
- 이를 보완하기 위해 keyword 목록을 충분히 넓게 큐레이션.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger


_log = get_logger("argos_self_audit.compliance_mapper")

# 키워드가 PRD 에 N개 등장하면 hit. 너무 낮으면 false positive, 너무 높으면 누락.
_KEYWORD_HIT_THRESHOLD = 1


@dataclass
class ArticleMatch:
    """단일 조항 매핑 결과."""

    article_id: str
    title: str
    summary: str
    matched_keywords: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)


@dataclass
class ComplianceMap:
    """PRD → 컴플라이언스 매핑 종합."""

    matched_articles: list[ArticleMatch] = field(default_factory=list)
    risk_scenarios: list[str] = field(default_factory=list)
    implementation_checklist: list[str] = field(default_factory=list)


# 위험 시나리오 — article_id → 사전 정의 텍스트.
# 빌드 가이드(07_ARGOS_SELF_AUDIT.md § 시나리오 3) 의 위험 시나리오 예시와 일치.
_RISK_SCENARIOS_BY_ARTICLE: dict[str, list[str]] = {
    "art_21": [
        "🔴 보유기간 경과 데이터 자동 파기 실패 시 → 법 위반 (과태료 최대 3천만원)",
        "🔴 파기 후 백업에서 복구 시 → 파기 의무 위반",
    ],
    "art_24": [
        "🔴 주민번호 등 고유식별정보 평문 저장 시 → 형사처벌 가능",
        "🔴 법령 근거 없이 수집·이용 시 → 즉시 사용 중단 + 폐기 명령",
    ],
    "art_29": [
        "🔴 안전성 확보 조치 미흡으로 유출 시 → 손해배상 + 형사책임",
        "🟠 접속 기록(audit log) 1년 미만 보관 시 → 시정명령 대상",
    ],
    "art_39_3": [
        "🔴 1천명 이상 유출 시 72시간 내 신고 누락 → 과징금",
        "🔴 정보주체 통지 24시간 초과 시 → 과태료",
    ],
}


# 구현 체크리스트 — article_id → 권장 구현 항목.
_CHECKLIST_BY_ARTICLE: dict[str, list[str]] = {
    "art_15": [
        "수집 항목·목적·보유기간을 동의 화면에 명시",
        "동의 이력 저장 (감사 대비)",
    ],
    "art_17": [
        "제3자 제공 동의를 별도 체크박스로 분리",
        "제공 로그 보관 (수신자·일시·항목)",
    ],
    "art_21": [
        "보유기간 경과 시 자동 파기 cron job",
        "파기 시 DoD 5220.22-M 또는 동급 방식 (overwrite + 검증)",
        "파기 로그를 audit_log 테이블에 분리 보관 (10년)",
        "백업 보관소도 동일 파기 정책 적용",
    ],
    "art_22": [
        "필수/선택 동의를 시각적으로 분리",
        "동의 철회 UI 제공",
        "14세 미만이면 법정대리인 동의 플로우",
    ],
    "art_23": [
        "민감정보 별도 동의 플로우",
        "DB 컬럼 단위 암호화 (AES-256-GCM)",
    ],
    "art_24": [
        "고유식별정보는 법령 근거 명시 후만 수집",
        "단방향 해시 또는 강한 암호화로 저장",
    ],
    "art_29": [
        "AES-256-GCM 등 권고 알고리즘 사용",
        "접근 권한 분리 (관리자/운영자/일반)",
        "접속 기록 1년 이상 보관",
        "분기별 취약점 점검",
    ],
    "art_30": [
        "처리방침 페이지 공개",
        "변경 시 7일 전 사전 고지",
    ],
    "art_35": [
        "/api/user/data 열람 엔드포인트",
        "10일 내 회신 SLA 모니터링",
    ],
    "art_36": [
        "회원 탈퇴 플로우",
        "탈퇴 후 백업 데이터 처리 정책",
    ],
    "art_39_3": [
        "유출 감지 자동 알람 (모니터링 시스템 연동)",
        "통지 템플릿 사전 준비",
        "신고 담당자 지정",
    ],
}


class ComplianceMapper:
    """``pipa_articles.yaml`` 기반 키워드 매퍼."""

    def __init__(self, articles_yaml: Path):
        self.articles_yaml = articles_yaml
        self._mtime: float = 0.0
        self._articles: list[dict[str, Any]] = []
        self._adjacent: list[dict[str, Any]] = []
        self._reload_if_stale()

    def _reload_if_stale(self) -> None:
        if not self.articles_yaml.exists():
            raise ConfigError(f"PIPA 조항 YAML 없음: {self.articles_yaml}")
        mtime = self.articles_yaml.stat().st_mtime
        if mtime == self._mtime:
            return
        try:
            data = yaml.safe_load(self.articles_yaml.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"PIPA YAML 파싱 실패: {exc}") from exc
        self._articles = list(data.get("articles") or [])
        self._adjacent = list(data.get("adjacent") or [])
        self._mtime = mtime
        _log.info(
            "pipa_loaded",
            articles=len(self._articles),
            adjacent=len(self._adjacent),
        )

    def map_feature(self, prd_text: str) -> ComplianceMap:
        """PRD 본문 → ``ComplianceMap``. LLM 호출 없음."""
        self._reload_if_stale()
        prd_lower = (prd_text or "").lower()
        cmap = ComplianceMap()

        all_articles = self._articles + self._adjacent
        for art in all_articles:
            keywords = [str(k).lower() for k in (art.get("keywords") or [])]
            matched = [k for k in keywords if k and k in prd_lower]
            if len(matched) < _KEYWORD_HIT_THRESHOLD:
                continue

            must_have = list(art.get("must_have_in_prd") or [])
            missing = [m for m in must_have if not _has_phrase(prd_lower, m)]

            cmap.matched_articles.append(ArticleMatch(
                article_id=str(art.get("id") or "?"),
                title=str(art.get("title") or ""),
                summary=str(art.get("summary") or ""),
                matched_keywords=matched[:6],   # 너무 많으면 임베드 잘림
                missing_requirements=missing,
            ))

        # 매핑된 article 의 위험 시나리오·체크리스트를 합산 (중복 제거).
        seen_risk: set[str] = set()
        seen_check: set[str] = set()
        for am in cmap.matched_articles:
            for r in _RISK_SCENARIOS_BY_ARTICLE.get(am.article_id, []):
                if r not in seen_risk:
                    cmap.risk_scenarios.append(r)
                    seen_risk.add(r)
            for c in _CHECKLIST_BY_ARTICLE.get(am.article_id, []):
                if c not in seen_check:
                    cmap.implementation_checklist.append(c)
                    seen_check.add(c)

        _log.info(
            "feature_mapped",
            articles=len(cmap.matched_articles),
            risks=len(cmap.risk_scenarios),
            checks=len(cmap.implementation_checklist),
        )
        return cmap


def _has_phrase(haystack_lower: str, phrase: str) -> bool:
    """단어 단위 부분 매칭 — must_have_in_prd 항목이 한국어·영어 혼재라 단순 in 검사."""
    if not phrase:
        return True
    p = phrase.lower()
    # 핵심 단어들이 모두 등장하면 hit (공백 분할).
    tokens = [t for t in re.split(r"[\s/·,]+", p) if t]
    if not tokens:
        return p in haystack_lower
    return all(t in haystack_lower for t in tokens)


__all__ = ["ComplianceMapper", "ComplianceMap", "ArticleMatch"]
