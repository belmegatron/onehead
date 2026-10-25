from typing import cast
from unittest.mock import MagicMock

import discord.ext.test as dpytest
import pytest
from conftest import add_ihl_role, join_member
from discord.ext.commands import Bot

from onehead.challenge import ChallengeMode
from onehead.common import Player


def stub_records(challenge_mode: ChallengeMode, *players: Player) -> None:
    """
    Make the database return the given records, looked up by id.

    :param challenge_mode: The cog under test.
    :param players: The records to serve.
    """
    by_id: dict[int, Player] = {player.id: player for player in players}
    challenge_mode.database.get = MagicMock(side_effect=by_id.get)


def cancel_expiry_tasks(challenge_mode: ChallengeMode) -> None:
    """
    Cancel the 24 hour expiry timers a successful challenge leaves behind.

    :param challenge_mode: The cog under test.
    """
    for challenge in challenge_mode.challenges:
        if challenge.handle_expiration_task:
            challenge.handle_expiration_task.cancel()


class TestMMRGuard:
    """
    The guard is deliberately one directional - punching up is allowed, punching down is
    not - which is why it is not abs(). These tests are the record of that decision, so
    anyone "fixing" the asymmetry has to change them on purpose.
    """

    @pytest.mark.asyncio
    async def test_cannot_challenge_someone_far_below_you(self, bot: Bot) -> None:
        target = await join_member(bot, "WEAKLING")
        author = list(bot.get_all_members())[0]
        await add_ihl_role(bot, "IHL")

        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))
        stub_records(
            challenge_mode,
            Player(id=author.id, name="AUTHOR", mmr=9000),
            Player(id=target.id, name="WEAKLING", mmr=1000),
        )

        await dpytest.message("!challenge WEAKLING")

        assert dpytest.verify().message().content("Pick on someone your own size").contains()
        assert challenge_mode.challenges == []

    @pytest.mark.asyncio
    async def test_can_challenge_someone_far_above_you(self, bot: Bot) -> None:
        target = await join_member(bot, "SMURF")
        author = list(bot.get_all_members())[0]
        await add_ihl_role(bot, "IHL")

        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))
        stub_records(
            challenge_mode,
            Player(id=author.id, name="AUTHOR", mmr=1000),
            Player(id=target.id, name="SMURF", mmr=9000),
        )

        await dpytest.message("!challenge SMURF")

        try:
            assert dpytest.verify().message().content("has challenged").contains()
            assert len(challenge_mode.challenges) == 1
        finally:
            cancel_expiry_tasks(challenge_mode)

    @pytest.mark.asyncio
    async def test_an_evenly_matched_duel_is_allowed(self, bot: Bot) -> None:
        target = await join_member(bot, "RIVAL")
        author = list(bot.get_all_members())[0]
        await add_ihl_role(bot, "IHL")

        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))
        stub_records(
            challenge_mode,
            Player(id=author.id, name="AUTHOR", mmr=5000),
            Player(id=target.id, name="RIVAL", mmr=4000),
        )

        await dpytest.message("!challenge RIVAL")

        try:
            assert dpytest.verify().message().content("has challenged").contains()
            assert len(challenge_mode.challenges) == 1
        finally:
            cancel_expiry_tasks(challenge_mode)

    @pytest.mark.asyncio
    async def test_the_boundary_is_inclusive(self, bot: Bot) -> None:
        """
        Exactly MAX_RATING_DIFFERENCE below is still a legal target - the guard rejects
        only what exceeds it.
        """
        target = await join_member(bot, "EDGE")
        author = list(bot.get_all_members())[0]
        await add_ihl_role(bot, "IHL")

        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))
        stub_records(
            challenge_mode,
            Player(id=author.id, name="AUTHOR", mmr=5000),
            Player(id=target.id, name="EDGE", mmr=5000 - ChallengeMode.MAX_RATING_DIFFERENCE),
        )

        await dpytest.message("!challenge EDGE")

        try:
            assert dpytest.verify().message().content("has challenged").contains()
        finally:
            cancel_expiry_tasks(challenge_mode)


class TestSelfChallenge:
    @pytest.mark.asyncio
    async def test_you_cannot_challenge_yourself(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        author = list(bot.get_all_members())[0]

        await dpytest.message(f"!challenge {author.display_name}")

        assert dpytest.verify().message().content("You cannot challenge yourself...")
