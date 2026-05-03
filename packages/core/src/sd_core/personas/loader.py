"""YAML 페르소나 로더."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sd_core.personas.base import Persona
from sd_core.utils.errors import ConfigError
from sd_core.utils.logger import get_logger


_log = get_logger("sd_core.personas.loader")

# 알려진 키. extras 로 분리할 키와 구분하기 위함.
_KNOWN_KEYS = {
    "id", "name", "emoji", "title", "core_lens",
    "priorities_in_order", "priorities", "speaking_style",
    "forbidden", "decision_lens", "red_flags", "output_format",
}


class PersonaLoader:
    """단일/일괄 YAML 로더."""

    def load(self, persona_id: str, search_paths: list[str | Path]) -> Persona:
        """주어진 검색 경로들에서 ``<id>.yaml`` 을 찾아 로드."""
        for base in search_paths:
            candidate = Path(base) / f"{persona_id}.yaml"
            if candidate.exists():
                return self._load_file(candidate)
        raise ConfigError(
            f"Persona '{persona_id}' not found in {[str(p) for p in search_paths]}"
        )

    def load_all(self, dir_path: str | Path) -> list[Persona]:
        """디렉토리 내 모든 *.yaml 을 페르소나로 로드."""
        d = Path(dir_path)
        if not d.exists():
            raise ConfigError(f"Persona directory not found: {d}")
        personas: list[Persona] = []
        for f in sorted(d.glob("*.yaml")):
            try:
                personas.append(self._load_file(f))
            except ConfigError as exc:
                # 한 페르소나 실패가 전체를 막지 않도록 로그 후 스킵
                _log.warning("persona_load_failed", file=str(f), error=str(exc))
        if not personas:
            raise ConfigError(f"No valid personas in {d}")
        return personas

    @staticmethod
    def _load_file(path: Path) -> Persona:
        try:
            data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML parse error in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"Persona YAML must be a mapping: {path}")

        # priorities_in_order 또는 priorities 둘 다 허용
        priorities = data.get("priorities_in_order") or data.get("priorities") or []

        extras = {k: v for k, v in data.items() if k not in _KNOWN_KEYS}

        try:
            return Persona(
                id=str(data["id"]),
                name=str(data["name"]),
                emoji=str(data.get("emoji", "")),
                title=str(data.get("title", "")),
                core_lens=str(data.get("core_lens", "")),
                priorities=list(priorities),
                speaking_style=dict(data.get("speaking_style") or {}),
                forbidden=list(data.get("forbidden") or []),
                decision_lens=list(data.get("decision_lens") or []),
                red_flags=list(data.get("red_flags") or []),
                output_format=str(data.get("output_format", "")),
                extras=extras,
            )
        except KeyError as exc:
            raise ConfigError(f"Persona YAML missing required key {exc} in {path}") from exc
