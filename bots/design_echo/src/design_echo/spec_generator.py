"""개발 핸드오프 spec 생성.

Gemini Flash Vision 1회로 시안 → Markdown spec.
DS 토큰 ID 는 design_system 의 키 그대로 노출 (개발자가 tailwind.config.js 매핑할 때 쉽게).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sd_core.llm.router import LLMRouter
from sd_core.llm.types import LLMRequest, TaskType

from design_echo.design_system import DesignSystem


@dataclass
class HandoffSpec:
    text: str
    cost_krw: float


class SpecGenerator:
    def __init__(
        self,
        llm: LLMRouter,
        ds: DesignSystem,
        spec_prompt_path: Path,
        base_prompt_path: Path,
    ):
        self.llm = llm
        self.ds = ds
        self._spec_prompt_path = spec_prompt_path
        self._base_prompt_path = base_prompt_path

    async def generate(
        self,
        image_bytes: bytes,
        screen_name: str,
        user_id: str,
    ) -> HandoffSpec:
        if not image_bytes:
            raise ValueError("이미지가 비어 있습니다.")
        if not screen_name.strip():
            raise ValueError("화면 이름은 필수입니다.")

        system_prompt = self._build_system_prompt()
        user_content = (
            f"## 대상 화면\n{screen_name.strip()}\n\n"
            "첨부된 시안을 보고 system 의 형식 그대로 핸드오프 spec 을 작성해 주세요.\n"
            "DS 토큰 ID 는 system 에 첨부된 token/component 카탈로그를 그대로 사용하세요.\n"
            "확실하지 않은 부분은 ⚠️ 로 표시하세요."
        )

        request = LLMRequest(
            task_type=TaskType.VISION_DESIGN,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            images=[image_bytes],
            user_id=user_id,
            bot_name="design_echo",
            max_tokens=2200,
            temperature=0.2,
        )
        response = await self.llm.call(request)
        return HandoffSpec(text=response.text, cost_krw=response.cost_krw)

    # -----------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        """베이스 + spec 프롬프트 + DS 카탈로그 요약. 캐시 효율 위해 1024자 이상 보장됨."""
        base = self._read(self._base_prompt_path)
        spec = self._read(self._spec_prompt_path)
        catalog = self._format_ds_catalog()
        return "\n\n".join([base, spec, catalog])

    def _format_ds_catalog(self) -> str:
        """DS tokens / components 를 LLM 이 ID 로 인용할 수 있도록 직렬화."""
        tokens = self.ds.tokens()
        components = self.ds.components()

        lines: list[str] = ["# DS 카탈로그 (이 이름들을 그대로 인용하세요)"]

        # 색상
        lines.append("\n## colors (token_id → hex)")
        for path, hex_val in self.ds.all_colors_flat():
            lines.append(f"- {path}: {hex_val}")

        # 타이포
        sizes = self.ds.typography_sizes()
        if sizes:
            lines.append("\n## typography sizes")
            for role, body in sizes.items():
                if isinstance(body, dict):
                    lines.append(
                        f"- {role}: size={body.get('size')}px weight={body.get('weight')} lh={body.get('line_height')}"
                    )

        # 간격
        scale = self.ds.spacing_scale()
        if scale:
            lines.append(f"\n## spacing scale (px): {scale}")

        # radius
        radius = (tokens.get("radius") or {})
        if radius:
            lines.append("\n## radius")
            for k, v in radius.items():
                lines.append(f"- radius.{k}: {v}px")

        # elevation
        elevation = (tokens.get("elevation") or {})
        if elevation:
            lines.append("\n## elevation")
            for k, v in elevation.items():
                lines.append(f"- elevation.{k}: {v}")

        # 컴포넌트
        if components:
            lines.append("\n## components (등록된 이름)")
            for c in components:
                if not isinstance(c, dict):
                    continue
                name = c.get("name") or c.get("id") or ""
                variants = ", ".join(c.get("variants") or []) or "-"
                lines.append(f"- {name} (variants: {variants})")

        return "\n".join(lines)

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""


__all__ = ["SpecGenerator", "HandoffSpec"]
