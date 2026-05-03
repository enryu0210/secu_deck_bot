"""LLM 호출에서 쓰는 공용 데이터 타입.

router/adapter 사이 인터페이스를 고정해 어댑터 추가·교체가 쉽도록 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class Provider(str, Enum):
    """LLM 공급자 식별자."""

    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENAI = "openai"


class TaskType(str, Enum):
    """봇이 router 에 알려주는 작업 의도.

    router 는 이 값을 기반으로 적합한 모델 후보를 골라낸다.
    추가 시 ``router.MODEL_POLICY`` 매핑도 함께 업데이트할 것.
    """

    KOREAN_WRITING = "korean_writing"          # 사업계획서·리뷰·종합
    CODE_REVIEW_SIMPLE = "code_review_simple"  # 짧은 코드, Haiku
    CODE_REVIEW_COMPLEX = "code_review_complex"  # 보안·복잡 코드, Sonnet
    VISION_DESIGN = "vision_design"            # 디자인 이미지 이해
    LARGE_CONTEXT = "large_context"            # 인터뷰 누적 등 대용량
    INSIGHT_EXTRACTION = "insight_extraction"  # 한국어 분석·종합
    ROUTING = "routing"                        # 의도 분류, Haiku/Mini


@dataclass
class LLMRequest:
    """LLM 호출 요청.

    ``system`` 은 캐시 대상 (Argos 컨텍스트·페르소나 등). 사용자 입력은 ``messages``로.
    """

    task_type: TaskType
    system: str
    messages: list[dict[str, Any]]
    user_id: str          # 쿼터·비용 귀속용
    bot_name: str         # 비용 라벨링용
    max_tokens: int = 1024
    temperature: float = 0.7
    # Vision 요청 시 멀티모달 컨텐츠. 어댑터가 공급자별 포맷으로 변환.
    images: list[bytes] | None = None
    # 호출자가 강제하고 싶은 모델이 있을 때 (router policy 우회). 보통은 None.
    force_provider: Provider | None = None
    force_model: str | None = None
    # 시스템 프롬프트를 캐시할지 여부. 대부분 True (Argos 컨텍스트 포함이면 권장).
    enable_cache: bool = True


@dataclass
class LLMResponse:
    """어댑터가 표준화해 router 에 돌려주는 응답."""

    text: str
    provider: Provider
    model_used: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0           # Anthropic 의 cache_read_input_tokens 등
    cost_krw: float = 0.0
    fallback_triggered: bool = False  # 1순위 실패 시 True
    raw: dict[str, Any] = field(default_factory=dict)  # 디버그용 원본 응답 일부


# 어댑터 공통 시그니처를 위한 타입 별칭
LLMRole = Literal["user", "assistant", "system"]
