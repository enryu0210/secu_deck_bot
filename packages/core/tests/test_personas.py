"""PersonaLoader / Persona 직렬화 테스트."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sd_core.personas import Persona, PersonaLoader
from sd_core.utils.errors import ConfigError


def _write_yaml(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / f"{name}.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_load_minimal_persona(tmp_path: Path):
    _write_yaml(tmp_path, "tester", """
        id: tester
        name: Tester
        emoji: "🧪"
        title: 테스트 페르소나
        core_lens: 모든 것을 의심한다
    """)
    loader = PersonaLoader()
    persona = loader.load("tester", [tmp_path])
    assert persona.id == "tester"
    assert "테스트 페르소나" in persona.title
    # 시스템 프롬프트에 정체성 헤더가 들어가야 한다
    prompt = persona.to_system_prompt()
    assert "Tester" in prompt and "🧪" in prompt


def test_load_full_persona_with_priorities(tmp_path: Path):
    _write_yaml(tmp_path, "skeptic", """
        id: skeptic
        name: Skeptic
        emoji: "🕵️"
        title: 회의주의자
        core_lens: 출처 없는 숫자는 가짜다
        priorities_in_order:
          - 모든 숫자에 출처가 있는가
          - 1차 출처인가
        forbidden:
          - 추측을 사실로 보강
        speaking_style:
          tone: 단호
          length: 3문장
    """)
    loader = PersonaLoader()
    persona = loader.load("skeptic", [tmp_path])
    assert persona.priorities[0].startswith("모든 숫자")
    assert "단호" in persona.to_system_prompt()


def test_load_all_skips_invalid(tmp_path: Path):
    _write_yaml(tmp_path, "ok", """
        id: ok
        name: OK
        emoji: "✓"
        title: 정상
        core_lens: 정상 동작
    """)
    # 깨진 YAML
    (tmp_path / "broken.yaml").write_text("id: : :\nname: ", encoding="utf-8")

    loader = PersonaLoader()
    personas = loader.load_all(tmp_path)
    # 정상 1건만 로드되어야 한다
    assert len(personas) == 1
    assert personas[0].id == "ok"


def test_missing_directory_raises():
    loader = PersonaLoader()
    with pytest.raises(ConfigError):
        loader.load_all("/nonexistent/path/xyz")
