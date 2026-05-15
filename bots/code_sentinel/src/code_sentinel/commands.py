"""슬래시 커맨드 그룹 ``/code``."""
from __future__ import annotations

import discord
from discord import app_commands

from sd_core.utils.errors import SecuDeckError

from code_sentinel.github_fetcher import (
    BranchDiff,
    BranchSnapshot,
    GitHubFetcher,
    GitHubFetchError,
)
from code_sentinel.language_detector import detect_language
from code_sentinel.reviewer import CodeReviewer
from code_sentinel.ui import (
    make_compliance_embed,
    make_findings_embed,
    make_review_embed,
    make_test_embed,
)
from sd_core.discord.ui import make_warning_embed


_MAX_INLINE_CODE_CHARS = 60000  # 코드 첨부/입력 상한


def _serialize_branch_diff(diff: BranchDiff) -> str:
    """BranchDiff → 리뷰 LLM 에 넣을 markdown 본문."""
    return (
        f"# {diff.repo} — `{diff.base}` ... `{diff.branch}` "
        f"(ahead {diff.ahead_by} commits)\n\n"
        f"## 변경 파일 ({len(diff.changed_files)})\n"
        + "\n".join(f"- {f}" for f in diff.changed_files)
        + "\n\n## diff\n"
        + diff.diff
    )


def _serialize_branch_snapshot(snap: BranchSnapshot) -> str:
    """BranchSnapshot → 리뷰 LLM 에 넣을 markdown 본문 (파일 블록 결합)."""
    head = (
        f"# {snap.repo} — branch `{snap.branch}` 스냅샷\n"
        f"파일 {len(snap.files)}개, 총 {snap.total_bytes:,}바이트"
        f"{' (일부 절단됨)' if snap.truncated else ''}\n\n"
    )
    blocks: list[str] = [head]
    for blob in snap.files:
        blocks.append(f"## file: {blob.path}\n```\n{blob.content}\n```\n")
    return "\n".join(blocks)


async def _read_attachment_text(attachment: discord.Attachment) -> str:
    if attachment.size > _MAX_INLINE_CODE_CHARS:
        raise SecuDeckError("파일이 너무 커요 (60KB 이하만).", "코드 파일이 너무 커요.")
    raw = await attachment.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecuDeckError("UTF-8 디코딩 실패", "텍스트 파일만 지원합니다.") from exc


class CodeCommands(app_commands.Group):
    def __init__(self, reviewer: CodeReviewer, fetcher: GitHubFetcher):
        super().__init__(name="code", description="코드 리뷰 + KISA 정합성 봇")
        self.reviewer = reviewer
        self.fetcher = fetcher

    # -----------------------------------------------------------------
    @app_commands.command(name="review", description="코드 리뷰 + Argos 보안 체크")
    @app_commands.describe(
        attachment="코드 파일 (.py, .ts, .js 등)",
        text="첨부 대신 코드 직접 입력",
        pr_url="GitHub PR URL (대신 사용)",
        focus="general | security | performance | tests",
    )
    @app_commands.choices(focus=[
        app_commands.Choice(name="일반", value="general"),
        app_commands.Choice(name="보안 집중", value="security"),
    ])
    async def review(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment | None = None,
        text: str | None = None,
        pr_url: str | None = None,
        focus: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(thinking=True)

        if not (attachment or text or pr_url):
            await interaction.followup.send(
                embed=make_warning_embed(
                    "입력 누락",
                    "attachment, text, pr_url 중 하나를 입력해 주세요.",
                ),
                ephemeral=True,
            )
            return

        # 입력 우선순위: attachment > pr_url > text
        filename: str | None = None
        if attachment is not None:
            try:
                code = await _read_attachment_text(attachment)
            except SecuDeckError as exc:
                await interaction.followup.send(exc.user_message, ephemeral=True)
                return
            filename = attachment.filename
        elif pr_url:
            try:
                pr = await self.fetcher.fetch(pr_url)
            except GitHubFetchError as exc:
                await interaction.followup.send(exc.user_message, ephemeral=True)
                return
            code = (
                f"# PR: {pr.repo}#{pr.number} — {pr.title}\n\n"
                f"## 변경 파일 ({len(pr.changed_files)})\n"
                + "\n".join(f"- {f}" for f in pr.changed_files)
                + "\n\n## diff\n"
                + pr.diff
            )
            filename = "pr.diff"
        else:
            code = text or ""

        language = detect_language(filename, code_hint=code)
        focus_value = focus.value if focus else None

        result = await self.reviewer.review(
            code=code, language=language, focus=focus_value,
            user_id=str(interaction.user.id),
        )

        embeds: list[discord.Embed] = []
        finding_embed = make_findings_embed(len(result.findings))
        if finding_embed:
            embeds.append(finding_embed)
        embeds.append(make_review_embed(result))
        await interaction.followup.send(embeds=embeds)

    # -----------------------------------------------------------------
    @app_commands.command(
        name="branch",
        description="GitHub 브랜치의 base 대비 diff 를 리뷰",
    )
    @app_commands.describe(
        branch="리뷰할 브랜치명 (예: feature/auth-rework)",
        repo="<owner>/<repo>. 미입력 시 CODE_SENTINEL_DEFAULT_REPO 사용",
        base="비교 기준 브랜치. 미입력 시 레포 default_branch 자동 감지 (보통 main)",
        focus="general | security",
    )
    @app_commands.choices(focus=[
        app_commands.Choice(name="일반", value="general"),
        app_commands.Choice(name="보안 집중", value="security"),
    ])
    async def branch_diff(
        self,
        interaction: discord.Interaction,
        branch: str,
        repo: str | None = None,
        base: str | None = None,
        focus: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(thinking=True)
        try:
            diff = await self.fetcher.fetch_branch_diff(repo, branch, base=base)
        except GitHubFetchError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return

        if not diff.changed_files:
            await interaction.followup.send(
                embed=make_warning_embed(
                    "변경 없음",
                    f"`{diff.base}` 대비 `{diff.branch}` 에 변경된 파일이 없어요.",
                ),
                ephemeral=True,
            )
            return

        code = _serialize_branch_diff(diff)
        focus_value = focus.value if focus else None
        # diff 는 다언어 가능 — reviewer 는 language 를 prompt 표시용으로만 씀
        result = await self.reviewer.review(
            code=code, language="multi", focus=focus_value,
            user_id=str(interaction.user.id),
        )

        embeds: list[discord.Embed] = []
        finding_embed = make_findings_embed(len(result.findings))
        if finding_embed:
            embeds.append(finding_embed)
        embeds.append(make_review_embed(result))
        await interaction.followup.send(embeds=embeds)

    # -----------------------------------------------------------------
    @app_commands.command(
        name="branch_full",
        description="GitHub 브랜치 전체 코드 스냅샷 리뷰 (비용 ↑ — 신중히 사용)",
    )
    @app_commands.describe(
        branch="리뷰할 브랜치명",
        repo="<owner>/<repo>. 미입력 시 CODE_SENTINEL_DEFAULT_REPO 사용",
        focus="general | security",
    )
    @app_commands.choices(focus=[
        app_commands.Choice(name="일반", value="general"),
        app_commands.Choice(name="보안 집중", value="security"),
    ])
    async def branch_full(
        self,
        interaction: discord.Interaction,
        branch: str,
        repo: str | None = None,
        focus: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(thinking=True)
        try:
            snap = await self.fetcher.fetch_branch_snapshot(repo, branch)
        except GitHubFetchError as exc:
            await interaction.followup.send(exc.user_message, ephemeral=True)
            return

        if not snap.files:
            await interaction.followup.send(
                embed=make_warning_embed(
                    "리뷰 대상 없음",
                    "스냅샷에서 LLM 리뷰 대상 파일을 찾지 못했어요. "
                    "(확장자 화이트리스트·크기 상한 적용 후 0개)",
                ),
                ephemeral=True,
            )
            return

        code = _serialize_branch_snapshot(snap)
        focus_value = focus.value if focus else None
        result = await self.reviewer.review(
            code=code, language="multi", focus=focus_value,
            user_id=str(interaction.user.id),
        )

        embeds: list[discord.Embed] = []
        if snap.truncated:
            # 일부 파일이 한도에 걸려 잘렸음을 명시 — 사용자가 결과 신뢰도를 가늠하도록
            embeds.append(make_warning_embed(
                "스냅샷 일부 절단",
                f"파일 수 또는 크기 한도에 걸려 {len(snap.files)}개만 리뷰했어요. "
                "전체 리뷰가 필요하면 `/code branch` (diff) 를 사용하거나 "
                "PR 단위로 나누어 주세요.",
            ))
        finding_embed = make_findings_embed(len(result.findings))
        if finding_embed:
            embeds.append(finding_embed)
        embeds.append(make_review_embed(result))
        await interaction.followup.send(embeds=embeds)

    # -----------------------------------------------------------------
    @app_commands.command(name="test", description="단위 테스트 자동 생성")
    @app_commands.describe(
        attachment="코드 파일",
        text="첨부 대신 코드 직접 입력",
    )
    async def test(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment | None = None,
        text: str | None = None,
    ):
        await interaction.response.defer(thinking=True)
        if not (attachment or text):
            await interaction.followup.send(
                "코드를 첨부하거나 직접 입력해 주세요.", ephemeral=True,
            )
            return

        filename = None
        if attachment is not None:
            try:
                code = await _read_attachment_text(attachment)
            except SecuDeckError as exc:
                await interaction.followup.send(exc.user_message, ephemeral=True)
                return
            filename = attachment.filename
        else:
            code = text or ""

        language = detect_language(filename, code_hint=code)
        result = await self.reviewer.generate_tests(
            code=code, language=language, user_id=str(interaction.user.id),
        )
        await interaction.followup.send(embed=make_test_embed(result))

    # -----------------------------------------------------------------
    @app_commands.command(name="kisa", description="KISA 가이드라인·법령 정합성 체크")
    @app_commands.describe(
        feature="신규 기능 설명 (자연어)",
    )
    async def kisa(self, interaction: discord.Interaction, feature: str):
        await interaction.response.defer(thinking=True)
        result = await self.reviewer.check_kisa(
            feature_description=feature,
            user_id=str(interaction.user.id),
        )
        await interaction.followup.send(embed=make_compliance_embed(result))


def install_commands(bot, reviewer: CodeReviewer, fetcher: GitHubFetcher) -> None:
    bot.tree.add_command(CodeCommands(reviewer, fetcher))
