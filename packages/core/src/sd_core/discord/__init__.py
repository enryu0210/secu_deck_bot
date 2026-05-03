"""Discord 통합 — 모든 봇이 상속하는 베이스."""
from sd_core.discord.base_bot import SecuDeckBot
from sd_core.discord.ui import (
    make_error_embed,
    make_success_embed,
    make_info_embed,
    truncate_field,
)

__all__ = [
    "SecuDeckBot",
    "make_error_embed",
    "make_success_embed",
    "make_info_embed",
    "truncate_field",
]
