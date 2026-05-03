"""ArgosContext 로더 테스트."""
from __future__ import annotations

import time
from pathlib import Path

from sd_core.context.argos import ArgosContext


def test_missing_file_returns_fallback(tmp_path: Path):
    ctx = ArgosContext(path=str(tmp_path / "no_such.md"))
    text = ctx.get_summary()
    assert "Argos 컨텍스트" in text  # 폴백 메시지의 한국어 키워드


def test_loads_and_reloads_on_change(tmp_path: Path):
    f = tmp_path / "argos.md"
    f.write_text("# 제품 핵심 기능\n\n초기 내용", encoding="utf-8")
    ctx = ArgosContext(path=str(f))
    first = ctx.get_full()
    assert "초기 내용" in first

    # mtime 변경
    time.sleep(0.01)
    f.write_text("# 제품 핵심 기능\n\n변경된 내용", encoding="utf-8")
    # mtime 갱신을 명시적으로 (일부 OS 에서 변경 누락 방지)
    import os
    os.utime(f, None)

    second = ctx.get_full()
    assert "변경된 내용" in second


def test_get_section_extracts_heading(tmp_path: Path):
    f = tmp_path / "argos.md"
    f.write_text(
        "# 인트로\n인트로 본문\n\n## 보안 이슈 요약\n주요 위험 1, 2, 3\n\n## 다음 섹션\n다른 내용",
        encoding="utf-8",
    )
    ctx = ArgosContext(path=str(f))
    section = ctx.get_section("보안 이슈 요약")
    assert "주요 위험" in section
    assert "다른 내용" not in section


def test_summary_truncates_long_text(tmp_path: Path):
    long_content = "# 섹션\n" + ("긴 내용 " * 5000)
    f = tmp_path / "argos.md"
    f.write_text(long_content, encoding="utf-8")
    ctx = ArgosContext(path=str(f))
    summary = ctx.get_summary(max_tokens=500)
    assert len(summary) < len(long_content)
