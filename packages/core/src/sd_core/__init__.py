"""sd_core — Secu Deck 봇 공용 코어 패키지.

각 봇은 이 패키지를 통해서만 LLM, 페르소나, Argos 컨텍스트, 비용 추적에 접근한다.
직접 anthropic.Anthropic() 등을 호출하지 말 것 (00_OVERVIEW.md § 2 LLM 라우팅 의무화).
"""

__version__ = "0.1.0"
