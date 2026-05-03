"""pytest 공통 설정 — asyncio 모드 활성화."""
import pytest


# pytest-asyncio: 모든 async 테스트를 자동 실행
pytest_plugins = ["pytest_asyncio"]
