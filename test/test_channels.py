import asyncio
import time
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.errors import HTTPException
from discord.ext.commands import Bot

from onehead.channels import Channels, move_member

MOVE_LATENCY_SECONDS: float = 0.05


def make_member(name: str, latency: float = MOVE_LATENCY_SECONDS) -> MagicMock:
    """
    Build a member whose move_to takes a measurable amount of time.

    :param name: The member's display name.
    :param latency: How long a move takes.
    :return: The member.
    """
    member = MagicMock()
    member.display_name = name

    async def move_to(_) -> None:
        await asyncio.sleep(latency)

    member.move_to = move_to

    return member


def make_channel(name: str) -> MagicMock:
    channel = MagicMock()
    channel.name = name

    return channel


class TestMoveMember:
    @pytest.mark.asyncio
    async def test_a_refused_move_is_logged_rather_than_raised(self, capsys) -> None:
        member = MagicMock()
        member.display_name = "RBEEZAY"
        member.move_to = AsyncMock(side_effect=HTTPException(MagicMock(status=403), "no"))

        await move_member(member, make_channel("IHL #1"))

        assert "Failed to move RBEEZAY" in capsys.readouterr().out


class TestMoveDiscordChannels:
    @pytest.mark.asyncio
    async def test_players_are_moved_concurrently(self, bot: Bot) -> None:
        """
        Ten players were moved one at a time, so the wait was ten round trips to Discord.
        """
        channels: Channels = cast(Channels, bot.get_cog("Channels"))
        channels.ihl_discord_channels = [make_channel("IHL #1"), make_channel("IHL #2")]

        radiant = [make_member(f"R{i}") for i in range(5)]
        dire = [make_member(f"D{i}") for i in range(5)]

        started: float = time.perf_counter()
        await channels.move_discord_channels(AsyncMock(), (radiant, dire))
        elapsed: float = time.perf_counter() - started

        sequential: float = MOVE_LATENCY_SECONDS * 10
        assert elapsed < sequential / 2, f"took {elapsed:.3f}s, sequential would be {sequential:.3f}s"

    @pytest.mark.asyncio
    async def test_every_player_reaches_their_team_channel(self, bot: Bot) -> None:
        channels: Channels = cast(Channels, bot.get_cog("Channels"))
        t1, t2 = make_channel("IHL #1"), make_channel("IHL #2")
        channels.ihl_discord_channels = [t1, t2]

        radiant = [MagicMock(display_name=f"R{i}", move_to=AsyncMock()) for i in range(5)]
        dire = [MagicMock(display_name=f"D{i}", move_to=AsyncMock()) for i in range(5)]

        await channels.move_discord_channels(AsyncMock(), (radiant, dire))

        for member in radiant:
            member.move_to.assert_awaited_once_with(t1)
        for member in dire:
            member.move_to.assert_awaited_once_with(t2)

    @pytest.mark.asyncio
    async def test_one_failure_does_not_abandon_the_rest(self, bot: Bot) -> None:
        channels: Channels = cast(Channels, bot.get_cog("Channels"))
        t1, t2 = make_channel("IHL #1"), make_channel("IHL #2")
        channels.ihl_discord_channels = [t1, t2]

        broken = MagicMock(display_name="BROKEN")
        broken.move_to = AsyncMock(side_effect=HTTPException(MagicMock(status=403), "no"))
        radiant = [broken] + [MagicMock(display_name=f"R{i}", move_to=AsyncMock()) for i in range(4)]
        dire = [MagicMock(display_name=f"D{i}", move_to=AsyncMock()) for i in range(5)]

        await channels.move_discord_channels(AsyncMock(), (radiant, dire))

        for member in radiant[1:] + dire:
            member.move_to.assert_awaited_once()


class TestMoveBackToLobby:
    @pytest.mark.asyncio
    async def test_players_are_moved_concurrently(self, bot: Bot) -> None:
        channels: Channels = cast(Channels, bot.get_cog("Channels"))

        lobby = make_channel(channels.lobby_name)
        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.voice_channels = [lobby]

        radiant = [make_member(f"R{i}") for i in range(5)]
        dire = [make_member(f"D{i}") for i in range(5)]

        started: float = time.perf_counter()
        await channels.move_back_to_lobby(ctx, (radiant, dire))
        elapsed: float = time.perf_counter() - started

        assert elapsed < (MOVE_LATENCY_SECONDS * 10) / 2

    @pytest.mark.asyncio
    async def test_everyone_ends_up_in_the_lobby(self, bot: Bot) -> None:
        channels: Channels = cast(Channels, bot.get_cog("Channels"))

        lobby = make_channel(channels.lobby_name)
        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.voice_channels = [lobby]

        radiant = [MagicMock(display_name=f"R{i}", move_to=AsyncMock()) for i in range(5)]
        dire = [MagicMock(display_name=f"D{i}", move_to=AsyncMock()) for i in range(5)]

        await channels.move_back_to_lobby(ctx, (radiant, dire))

        for member in radiant + dire:
            member.move_to.assert_awaited_once_with(lobby)
