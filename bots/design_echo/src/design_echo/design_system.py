"""design_system YAML 로더 + 토큰 비교 유틸.

`tokens.yaml`, `components.yaml`, `tone_guide.yaml` 을 mtime 감지로 로드한다.
디자인팀이 이 파일을 수정하면 봇 재시작 없이 다음 호출부터 반영.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

import yaml

from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger


_log = get_logger("design_echo.design_system")


# 색상이 같다고 볼지 판단하는 RGB 거리 한계. 이 안이면 "거의 같음" 으로 처리.
_COLOR_NEAR_THRESHOLD = 12  # 0~441 (3D RGB 거리). 12 면 일반인 눈으로 구분 잘 안 됨.

# 폰트 크기 차이 허용 — 시안에서 ±1px 정도는 자동 매칭
_TYPO_SIZE_TOLERANCE = 1


@dataclass
class TokenDiff:
    """토큰 비교 결과 1건."""

    kind: str               # "color" | "typography" | "spacing" | "component"
    severity: str           # "ok" | "warn" | "error"
    message: str            # 사용자에게 노출
    detected: Any = None    # 시안에서 본 값
    expected: Any = None    # DS 기대값


@dataclass
class CheckSummary:
    """전체 비교 결과 컨테이너."""

    diffs: list[TokenDiff] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(d.severity == "error" for d in self.diffs)

    @property
    def has_warnings(self) -> bool:
        return any(d.severity == "warn" for d in self.diffs)


class DesignSystem:
    """디자인 시스템 YAML 3개를 묶어 관리. mtime 캐시."""

    def __init__(self, ds_dir: Path):
        self._dir = ds_dir
        self._tokens_path = ds_dir / "tokens.yaml"
        self._components_path = ds_dir / "components.yaml"
        self._tone_path = ds_dir / "tone_guide.yaml"

        self._lock = Lock()
        self._cache_tokens: dict[str, Any] = {}
        self._cache_components: dict[str, Any] = {}
        self._cache_tone: dict[str, Any] = {}
        self._mtimes: dict[str, float] = {}

    # ---------------- public ----------------
    def tokens(self) -> dict[str, Any]:
        self._reload_if_needed()
        return self._cache_tokens

    def components(self) -> list[dict[str, Any]]:
        self._reload_if_needed()
        return self._cache_components.get("components") or []

    def tone(self) -> dict[str, Any]:
        self._reload_if_needed()
        return self._cache_tone

    def known_component_names(self) -> set[str]:
        return {str(c.get("name", "")).lower() for c in self.components()}

    def all_colors_flat(self) -> list[tuple[str, str]]:
        """tokens.colors 를 (path, hex) 평탄화. 비교용."""
        out: list[tuple[str, str]] = []
        for group, sub in (self.tokens().get("colors") or {}).items():
            if isinstance(sub, dict):
                for key, val in sub.items():
                    if isinstance(val, str):
                        out.append((f"{group}.{key}", val.upper()))
        return out

    def typography_sizes(self) -> dict[str, dict[str, Any]]:
        return (self.tokens().get("typography") or {}).get("sizes") or {}

    def spacing_scale(self) -> list[int]:
        scale = (self.tokens().get("spacing") or {}).get("scale") or []
        return [int(x) for x in scale]

    # ---------------- compare ----------------
    def compare(self, extracted: dict[str, Any]) -> CheckSummary:
        """LLM 이 시안에서 추출한 dict 와 DS 비교 → diff 목록."""
        summary = CheckSummary()
        self._compare_colors(extracted, summary)
        self._compare_typography(extracted, summary)
        self._compare_spacing(extracted, summary)
        self._compare_components(extracted, summary)
        return summary

    # ---------------- internal ----------------
    def _compare_colors(self, extracted: dict[str, Any], summary: CheckSummary) -> None:
        ds_pairs = self.all_colors_flat()
        ds_hexes = [p[1] for p in ds_pairs]

        seen: set[str] = set()
        for group, hex_list in (extracted.get("colors") or {}).items():
            for raw in (hex_list or []):
                if not isinstance(raw, str):
                    continue
                hex_val = raw.upper()
                if hex_val in seen:
                    continue
                seen.add(hex_val)

                if hex_val in ds_hexes:
                    summary.diffs.append(TokenDiff(
                        kind="color", severity="ok",
                        message=f"`{group}` {hex_val} — DS 일치",
                        detected=hex_val,
                    ))
                    continue

                # 가까운 색이 있으면 warn (오타·렌더링 차이 가능성)
                near = _nearest_color(hex_val, ds_hexes)
                if near and _color_distance(hex_val, near) <= _COLOR_NEAR_THRESHOLD:
                    summary.diffs.append(TokenDiff(
                        kind="color", severity="warn",
                        message=f"`{group}` {hex_val} ≈ DS {near} (거의 같음 — 통일 권장)",
                        detected=hex_val, expected=near,
                    ))
                else:
                    summary.diffs.append(TokenDiff(
                        kind="color", severity="error",
                        message=f"`{group}` {hex_val} — DS 미등록 색상",
                        detected=hex_val,
                    ))

    def _compare_typography(self, extracted: dict[str, Any], summary: CheckSummary) -> None:
        ds_sizes = self.typography_sizes()
        ds_size_set = {int(v.get("size", 0)) for v in ds_sizes.values() if isinstance(v, dict)}

        for entry in (extracted.get("typography") or []):
            if not isinstance(entry, dict):
                continue
            size = entry.get("size_px")
            if not isinstance(size, (int, float)):
                continue
            size_int = int(size)
            role = str(entry.get("role", "?"))
            font = str(entry.get("font", "?"))

            # DS 크기 집합과 매칭 (허용 오차 내)
            if size_int in ds_size_set:
                summary.diffs.append(TokenDiff(
                    kind="typography", severity="ok",
                    message=f"`{role}` {font} {size_int}px — DS 일치",
                ))
            elif any(abs(size_int - s) <= _TYPO_SIZE_TOLERANCE for s in ds_size_set):
                near = min(ds_size_set, key=lambda s: abs(s - size_int))
                summary.diffs.append(TokenDiff(
                    kind="typography", severity="warn",
                    message=f"`{role}` {size_int}px → DS 표준 {near}px 권장",
                    detected=size_int, expected=near,
                ))
            else:
                summary.diffs.append(TokenDiff(
                    kind="typography", severity="error",
                    message=f"`{role}` {size_int}px — DS 크기표 벗어남 ({sorted(ds_size_set)})",
                    detected=size_int, expected=sorted(ds_size_set),
                ))

    def _compare_spacing(self, extracted: dict[str, Any], summary: CheckSummary) -> None:
        scale = set(self.spacing_scale())
        if not scale:
            return
        spacing = extracted.get("spacing") or {}
        for key, val in spacing.items():
            if not isinstance(val, (int, float)):
                continue
            v = int(val)
            if v in scale:
                summary.diffs.append(TokenDiff(
                    kind="spacing", severity="ok",
                    message=f"`{key}` {v}px — 8px 그리드 일치",
                ))
            else:
                # 스케일에서 가장 가까운 값 추천
                near = min(scale, key=lambda s: abs(s - v))
                summary.diffs.append(TokenDiff(
                    kind="spacing", severity="warn",
                    message=f"`{key}` {v}px — 그리드 벗어남, {near}px 권장",
                    detected=v, expected=near,
                ))

    def _compare_components(self, extracted: dict[str, Any], summary: CheckSummary) -> None:
        known = self.known_component_names()
        for name in (extracted.get("components") or []):
            if not isinstance(name, str):
                continue
            normalized = name.strip().lower()
            if any(k in normalized or normalized in k for k in known):
                summary.diffs.append(TokenDiff(
                    kind="component", severity="ok",
                    message=f"`{name}` — DS 등록 컴포넌트",
                ))
            else:
                summary.diffs.append(TokenDiff(
                    kind="component", severity="warn",
                    message=f"`{name}` — DS 미등록, 등록 검토 필요",
                ))

    # ---------------- reload ----------------
    def _reload_if_needed(self) -> None:
        with self._lock:
            self._reload_one(self._tokens_path, "tokens", lambda d: setattr(self, "_cache_tokens", d))
            self._reload_one(self._components_path, "components", lambda d: setattr(self, "_cache_components", d))
            self._reload_one(self._tone_path, "tone", lambda d: setattr(self, "_cache_tone", d))

    def _reload_one(self, path: Path, key: str, setter) -> None:
        if not path.exists():
            raise ConfigError(f"design_system 파일 누락: {path}")
        current = path.stat().st_mtime
        if self._mtimes.get(key) == current:
            return
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"design_system YAML 파싱 실패 ({path}): {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"design_system YAML 은 매핑이어야 합니다: {path}")
        setter(data)
        self._mtimes[key] = current
        _log.info("design_system_loaded", file=key, mtime=current)


# ---------------------------------------------------------------------
# 색상 유틸
# ---------------------------------------------------------------------
def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError:
        return None


def _color_distance(a: str, b: str) -> float:
    ra = _hex_to_rgb(a)
    rb = _hex_to_rgb(b)
    if not ra or not rb:
        return 999.0
    return ((ra[0] - rb[0]) ** 2 + (ra[1] - rb[1]) ** 2 + (ra[2] - rb[2]) ** 2) ** 0.5


def _nearest_color(target: str, candidates: Iterable[str]) -> str | None:
    best, best_d = None, 999.0
    for c in candidates:
        d = _color_distance(target, c)
        if d < best_d:
            best, best_d = c, d
    return best
