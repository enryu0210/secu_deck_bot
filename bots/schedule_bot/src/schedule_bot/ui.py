"""디스코드 임베드 빌더 — 슬래시 응답 + cos 위임 응답 공용.

색상 컨벤션 (다른 봇과 통일):
- 파랑(0x5865F2): 일반 정보 (단일 일정 상세 등)
- 초록(0x57F287): 성공 (등록 완료 등)
- 노랑(0xFEE75C): 경고/주의 (알림·삭제)
- 빨강(0xED4245): 에러
- 분홍(0xEB459E): 목록 헤더 (군집 표시 강조)
"""
from __future__ import annotations

import discord


COLOR_PRIMARY = 0x5865F2
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_ERROR = 0xED4245
COLOR_INFO = 0xEB459E


def format_schedule_embed(schedule: dict, title_prefix: str = "") -> discord.Embed:
    """단일 일정 dict → 상세 임베드."""
    title = f"{title_prefix}📅 [{schedule['id']}] {schedule['title']}"
    embed = discord.Embed(title=title, color=COLOR_PRIMARY)

    time_display = schedule["time"] if schedule.get("time") else "시간 미정"
    embed.add_field(name="🗓️ 날짜", value=schedule["date"], inline=True)
    embed.add_field(name="⏰ 시간", value=time_display, inline=True)

    if schedule.get("description"):
        embed.add_field(name="📝 설명", value=schedule["description"], inline=False)

    embed.set_footer(text=f"등록자: {schedule['created_by']}")
    return embed


def build_schedule_list_embed(schedules: list[dict], title: str) -> discord.Embed:
    """일정 목록 → 임베드. 비어 있으면 안내 문구."""
    embed = discord.Embed(title=title, color=COLOR_INFO)

    if not schedules:
        embed.description = "등록된 일정이 없어요. `/일정 등록`으로 추가해보세요!"
        return embed

    for s in schedules:
        time_str = s["time"] if s.get("time") else "시간 미정"
        value = f"⏰ {time_str}"
        if s.get("description"):
            desc = s["description"]
            if len(desc) > 50:
                desc = desc[:50] + "..."
            value += f"\n📝 {desc}"
        value += f"\n👤 {s['created_by']}"
        embed.add_field(
            name=f"[{s['id']}] {s['title']} — {s['date']}",
            value=value,
            inline=False,
        )

    embed.set_footer(text=f"총 {len(schedules)}개 일정")
    return embed


def schedules_to_summary_text(schedules: list[dict], header: str) -> str:
    """cos 위임 응답용 — 디스코드 임베드 description 에 들어갈 텍스트.

    cos 측 임베드 폭(약 4096자) 안에서 5~10개까지 표시. 너무 길면 잘림.
    """
    if not schedules:
        return f"{header}\n(등록된 일정 없음)"

    lines = [header]
    for s in schedules:
        time_str = s.get("time") or "시간 미정"
        line = f"• `[{s['id']}]` **{s['title']}** — {s['date']} {time_str}"
        if s.get("description"):
            desc = s["description"]
            if len(desc) > 60:
                desc = desc[:60] + "..."
            line += f"\n  📝 {desc}"
        lines.append(line)
    return "\n".join(lines)


def summary_blocks_for_schedule(schedule: dict) -> list[dict]:
    """등록 결과를 cos 위임 응답의 blocks 로 표현."""
    return [
        {"title": "🆔 ID", "value": str(schedule["id"]), "inline": True},
        {"title": "🗓️ 날짜", "value": schedule["date"], "inline": True},
        {"title": "⏰ 시간", "value": schedule.get("time") or "시간 미정", "inline": True},
    ]


__all__ = [
    "COLOR_PRIMARY",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_ERROR",
    "COLOR_INFO",
    "format_schedule_embed",
    "build_schedule_list_embed",
    "schedules_to_summary_text",
    "summary_blocks_for_schedule",
]
