from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import discord.ext.test as dpytest
import pytest
from conftest import add_ihl_role, join_member
from discord.errors import HTTPException
from discord.ext.commands import Bot

from onehead.challenge import ChallengeMode
from onehead.common import Player
from onehead.game import Challenge


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


class TestExpiry:
    """
    handle_expired_challenge is the only thing that removes a challenge from the list on
    the non-rejected path, and Challenge.start() used to cancel it - called from accept -
    so an accepted duel that no admin ever started stayed in the list for the lifetime of
    the process, blocking its challenger from issuing another.
    """

    @pytest.mark.asyncio
    async def test_an_accepted_challenge_keeps_its_expiry_timer(self, bot: Bot) -> None:
        challenge = Challenge(1, MagicMock(), MagicMock())
        challenge.handle_expiration_task = MagicMock()
        challenge.start()

        assert challenge.in_progress() is True
        challenge.handle_expiration_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_expiry_stops_the_timer(self, bot: Bot) -> None:
        challenge = Challenge(1, MagicMock(), MagicMock())
        challenge.handle_expiration_task = MagicMock()

        challenge.cancel_expiry()

        challenge.handle_expiration_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_an_unaccepted_challenge_is_removed_and_announced(self, bot: Bot) -> None:
        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))

        challenge = Challenge(1, MagicMock(), MagicMock())
        challenge.expires = datetime.now(UTC)
        challenge_mode.challenges.append(challenge)

        ctx = AsyncMock()
        await challenge_mode.handle_expired_challenge(ctx, challenge)

        assert challenge not in challenge_mode.challenges
        assert "failed to accept" in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_an_accepted_but_unstarted_challenge_is_still_removed(self, bot: Bot) -> None:
        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))

        challenge = Challenge(1, MagicMock(), MagicMock())
        challenge.expires = datetime.now(UTC)
        challenge.start()
        challenge_mode.challenges.append(challenge)

        ctx = AsyncMock()
        await challenge_mode.handle_expired_challenge(ctx, challenge)

        assert challenge not in challenge_mode.challenges
        assert "never started" in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_a_failing_announcement_still_leaves_the_list_clean(self, bot: Bot) -> None:
        """
        Announcing before removing meant a send that failed a day later kept the challenge
        alive forever.
        """
        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))

        challenge = Challenge(1, MagicMock(), MagicMock())
        challenge.expires = datetime.now(UTC)
        challenge_mode.challenges.append(challenge)

        ctx = AsyncMock()
        ctx.send = AsyncMock(side_effect=HTTPException(MagicMock(status=404), "channel gone"))

        with pytest.raises(HTTPException):
            await challenge_mode.handle_expired_challenge(ctx, challenge)

        assert challenge not in challenge_mode.challenges


class TestBullyPathLeavesVoice:
    @pytest.mark.asyncio
    async def test_the_bot_does_not_stay_parked_after_the_taunt(self, bot: Bot, monkeypatch) -> None:
        """
        bully.mp3 pulls the bot into voice, and no game is created on this path, so without
        an explicit disconnect nothing would ever get it out again.
        """
        import onehead.challenge as challenge_module

        scheduled: list[str] = []
        monkeypatch.setattr(
            challenge_module,
            "create_background_task",
            lambda coro, name: (coro.close(), scheduled.append(name))[1],
        )

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

        assert "voice_client_disconnect" in scheduled


class TestDuplicateChallenges:
    @pytest.mark.asyncio
    async def test_the_reverse_pairing_is_rejected(self, bot: Bot) -> None:
        """
        A challenges B, then B challenges A - both used to become live duels, each with
        its own id, both acceptable and startable.
        """
        other = await join_member(bot, "RIVAL")
        author = list(bot.get_all_members())[0]
        await add_ihl_role(bot, "IHL")

        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))
        stub_records(
            challenge_mode,
            Player(id=author.id, name="AUTHOR", mmr=5000),
            Player(id=other.id, name="RIVAL", mmr=5000),
        )

        # RIVAL has already challenged the author.
        existing = Challenge(0, challenger=other, opponent=author)
        challenge_mode.challenges.append(existing)

        await dpytest.message("!challenge RIVAL")

        assert dpytest.verify().message().content("rather than challenging them back").contains()
        assert len(challenge_mode.challenges) == 1

    @pytest.mark.asyncio
    async def test_a_departed_opponent_still_gets_a_message(self, bot: Bot) -> None:
        """
        The existing opponent used to be looked up and assigned over `opponent`, with the
        return outside the guard - so if they had left the guild, !challenge sent nothing
        at all and looked broken.
        """
        other = await join_member(bot, "RIVAL")
        author = list(bot.get_all_members())[0]
        await add_ihl_role(bot, "IHL")

        challenge_mode: ChallengeMode = cast(ChallengeMode, bot.get_cog("ChallengeMode"))
        stub_records(
            challenge_mode,
            Player(id=author.id, name="AUTHOR", mmr=5000),
            Player(id=other.id, name="RIVAL", mmr=5000),
        )

        # The author already challenged somebody who is no longer in the guild.
        departed = MagicMock()
        departed.id = 999999
        departed.display_name = "LONG_GONE"
        challenge_mode.challenges.append(Challenge(0, challenger=author, opponent=departed))

        await dpytest.message("!challenge RIVAL")

        assert dpytest.verify().message().content("has already issued a challenge to LONG_GONE").contains()
