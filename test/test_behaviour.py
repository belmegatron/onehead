from typing import cast
from unittest.mock import Mock

import discord.ext.test as dpytest
import pytest
from conftest import (
    TEST_USER,
    add_ihl_role,
    create_fake_player,
    create_fake_team,
    create_test_player,
    join_member,
)
from discord.ext.commands import Bot, errors
from discord.member import Member

from onehead.behaviour import Behaviour
from onehead.common import Player, Team
from onehead.game import ClassicGame
from onehead.store import GameStore


class TestCommend:
    @pytest.mark.asyncio
    async def test_no_ihl_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!commend RBEEZAY")

    @pytest.mark.asyncio
    async def test_no_previous_game(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        await dpytest.message("!commend RBEEZAY")
        assert dpytest.verify().message().content("Unable to commend as a game is yet to be played.")

    @pytest.mark.asyncio
    async def test_commender_did_not_play(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game = cast(ClassicGame, store.previous_game)
        store.previous_game.radiant = Team()
        store.previous_game.dire = Team()

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!commend RBEEZAY")
        assert (
            dpytest.verify()
            .message()
            .content("did not participate in the previous game and therefore cannot commend another player.")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_commend_self(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game = cast(ClassicGame, store.previous_game)
        store.previous_game.radiant = (
            create_test_player(bot),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        await add_ihl_role(bot, "IHL")
        await dpytest.message(f"!commend {TEST_USER}")
        assert dpytest.verify().message().content("you cannot commend yourself, nice try...").contains()

    @pytest.mark.asyncio
    async def test_commendee_did_not_play(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game = cast(ClassicGame, store.previous_game)
        store.previous_game.radiant = (
            create_test_player(bot),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        await dpytest.member_join(name="RBEEZAY")

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!commend RBEEZAY")
        assert (
            dpytest.verify()
            .message()
            .content("cannot be commended as they did not participate in the previous game.")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_previously_commended(self, bot: Bot) -> None:
        rbeezay: Member = await join_member(bot, "RBEEZAY")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game = cast(ClassicGame, store.previous_game)
        store.previous_game.radiant = (
            create_test_player(bot),
            Player(name="RBEEZAY", id=rbeezay.id, mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()
        store.previous_game._commends["RBEEZAY"] = [TEST_USER]

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!commend RBEEZAY")
        assert dpytest.verify().message().content("has already been commended by").contains()

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        rbeezay: Member = await join_member(bot, "RBEEZAY")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game.radiant = (
            create_test_player(bot),
            Player(name="RBEEZAY", id=rbeezay.id, mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        behaviour: Behaviour = cast(Behaviour, bot.get_cog("Behaviour"))
        behaviour.database.get = Mock()
        behaviour.database.get.return_value = Player(name="RBEEZAY", id=rbeezay.id, mmr=3000, behaviour=10000)
        behaviour.database.update = Mock()

        await add_ihl_role(bot, "IHL")

        await dpytest.message("!commend RBEEZAY")
        assert dpytest.verify().message().content("has been commended").contains()


class TestReport:
    @pytest.mark.asyncio
    async def test_no_ihl_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!report RBEEZAY")

    @pytest.mark.asyncio
    async def test_missing_reason(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        with pytest.raises(errors.MissingRequiredArgument):
            await dpytest.message("!report RBEEZAY")

    @pytest.mark.asyncio
    async def test_no_previous_game(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        await dpytest.message("!report RBEEZAY abandon")
        assert dpytest.verify().message().content("Unable to report as a game is yet to be played.")

    @pytest.mark.asyncio
    async def test_reporter_did_not_play(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game.radiant = (
            Player(name="RBEEZAY", id=0, mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!report RBEEZAY abandon")
        assert (
            dpytest.verify()
            .message()
            .content("did not participate in the previous game and therefore cannot report another player.")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_report_self(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game.radiant = (
            create_test_player(bot),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL")
        await dpytest.message(f"!report {TEST_USER} abandon")
        assert dpytest.verify().message().content("has brought dishonour upon themselves").contains()

    @pytest.mark.asyncio
    async def test_reportee_did_not_play(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game.radiant = (
            create_test_player(bot),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        # RBEEZAY exists in the guild but is deliberately not in either team.
        await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL")
        await dpytest.message("!report RBEEZAY abandon")
        assert (
            dpytest.verify()
            .message()
            .content("cannot be reported as they did not participate in the previous game.")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_reported_previously(self, bot: Bot) -> None:
        rbeezay: Member = await join_member(bot, "RBEEZAY")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game.radiant = (
            create_test_player(bot),
            Player(name="RBEEZAY", id=rbeezay.id, mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()
        store.previous_game._reports["RBEEZAY"] = [TEST_USER]

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!report RBEEZAY abandon")
        assert dpytest.verify().message().content("has already been reported by").contains()

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        rbeezay: Member = await join_member(bot, "RBEEZAY")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.previous_game = ClassicGame()
        store.previous_game.radiant = (
            create_test_player(bot),
            Player(name="RBEEZAY", id=rbeezay.id, mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.previous_game.dire = create_fake_team()

        behaviour: Behaviour = cast(Behaviour, bot.get_cog("Behaviour"))
        behaviour.database.get = Mock()
        behaviour.database.get.return_value = Player(name="RBEEZAY", id=rbeezay.id, mmr=3000, behaviour=10000)

        behaviour.database.update = Mock()

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!report RBEEZAY abandon")
        assert dpytest.verify().message().content("has been reported").contains()
