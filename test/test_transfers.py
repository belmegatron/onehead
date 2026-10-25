from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import discord.ext.test as dpytest
import pytest
from conftest import add_ihl_role, create_fake_player, create_fake_team, create_test_player
from discord.ext.commands import Bot, CommandInvokeError, errors

from onehead.common import Player, PlayerTransfer
from onehead.game import ClassicGame
from onehead.store import GameStore
from onehead.transfers import Transfers


class TestShuffle:
    @pytest.mark.asyncio
    async def test_no_ihl_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!shuffle")

    @pytest.mark.asyncio
    async def test_transfer_window_closed(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._transfer_window_open = False

        await dpytest.message("!shuffle")
        assert dpytest.verify().message().content("Unable to shuffle as player transfer window is closed.")

    @pytest.mark.asyncio
    async def test_invalid_teams(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._transfer_window_open = True

        with pytest.raises(CommandInvokeError):
            await dpytest.message("!shuffle")

    @pytest.mark.asyncio
    async def test_not_signed_up(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._transfer_window_open = True
        store.current_game.radiant = create_fake_team()
        store.current_game.dire = create_fake_team()

        await dpytest.message("!shuffle")
        assert (
            dpytest.verify()
            .message()
            .content("is unable to shuffle as they are not participating in the current game.")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_insufficient_rbucks(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._transfer_window_open = True
        store.current_game.radiant = (
            create_test_player(bot),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.current_game.dire = create_fake_team()

        transfers: Transfers = cast(Transfers, bot.get_cog("Transfers"))

        transfers.database.get = Mock()
        transfers.database.get.return_value = Player(
            id=262570465212497920,
            name="HARRY",
            mmr=4750,
            rbucks=0,
        )

        await dpytest.message("!shuffle")
        assert dpytest.verify().message().content("cannot shuffle as they only have 0 RBUCKS").contains()

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._transfer_window_open = True
        store.current_game.radiant = (
            create_test_player(bot),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.current_game.dire = create_fake_team()

        transfers: Transfers = cast(Transfers, bot.get_cog("Transfers"))

        transfers.database.get = Mock()
        transfers.database.get.return_value = Player(
            id=262570465212497920,
            name="HARRY",
            mmr=4750,
            rbucks=Transfers.SHUFFLE_COST + 100,
        )
        transfers.database.update = Mock()

        transfers.matchmaking.balance = AsyncMock()
        transfers.matchmaking.balance.return_value = (
            create_fake_team(),
            create_fake_team(),
        )

        with patch("onehead.transfers.play_sound"):
            await dpytest.message("!shuffle")
            assert (
                dpytest.verify()
                .message()
                .content(f"has spent **{Transfers.SHUFFLE_COST}** RBUCKS to **shuffle** the teams!")
                .contains()
            )


class TestRenamedPlayers:
    """
    Participation used to be checked against the signups, which are keyed by display name,
    and refunds resolved the buyer by display name - so renaming yourself mid-game locked
    you out of shuffling and silently lost you your refund.
    """

    @pytest.mark.asyncio
    async def test_a_renamed_participant_can_still_shuffle(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        author = list(bot.get_all_members())[0]

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._transfer_window_open = True
        # On a team, but the record carries the name they registered under.
        store.current_game.radiant = (
            Player(id=author.id, name="NAME_FROM_BEFORE_THE_RENAME", mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        store.current_game.dire = create_fake_team()

        transfers: Transfers = cast(Transfers, bot.get_cog("Transfers"))
        # Nobody signed up under the author's current display name.
        transfers.lobby.get_signups = Mock(return_value=[])
        transfers.database.get = Mock(
            return_value=Player(id=author.id, name="NAME_FROM_BEFORE_THE_RENAME", mmr=3000, rbucks=1000)
        )
        transfers.database.update = Mock()
        transfers.matchmaking.balance = AsyncMock(return_value=(create_fake_team(), create_fake_team()))

        with patch("onehead.transfers.play_sound"):
            await dpytest.message("!shuffle")

        assert dpytest.verify().message().content("has spent").contains()

    @pytest.mark.asyncio
    async def test_a_refund_finds_the_buyer_by_id(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        game = ClassicGame()
        game._player_transfers = [PlayerTransfer(buyer_id=1234, amount=Transfers.SHUFFLE_COST)]
        store.current_game = game

        transfers: Transfers = cast(Transfers, bot.get_cog("Transfers"))
        record = Player(id=1234, name="WHO_CARES", mmr=3000, rbucks=0)
        transfers.database.get = Mock(return_value=record)
        transfers.database.update = Mock()

        ctx = AsyncMock()
        await transfers.refund_transfers(ctx)

        transfers.database.get.assert_called_once_with(1234)
        assert record.rbucks == Transfers.SHUFFLE_COST
        assert "All player transactions have been refunded." in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_a_partial_refund_does_not_claim_otherwise(self, bot: Bot) -> None:
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        game = ClassicGame()
        game._player_transfers = [
            PlayerTransfer(buyer_id=1, amount=500),
            PlayerTransfer(buyer_id=2, amount=500),
        ]
        store.current_game = game

        transfers: Transfers = cast(Transfers, bot.get_cog("Transfers"))
        present = Player(id=1, name="PRESENT", mmr=3000, rbucks=0)
        transfers.database.get = Mock(side_effect=lambda id: present if id == 1 else None)
        transfers.database.update = Mock()

        ctx = AsyncMock()
        await transfers.refund_transfers(ctx)

        assert present.rbucks == 500
        assert "`1` of `2`" in ctx.send.await_args.args[0]
