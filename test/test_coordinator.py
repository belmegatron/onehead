from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import discord.ext.test as dpytest
import pytest
from conftest import add_ihl_role, create_fake_team
from discord.ext.commands import Bot, CommandInvokeError, errors

from onehead.betting import Bet
from onehead.common import Player, Side
from onehead.coordinator import GameCoordinator
from onehead.game import ClassicGame
from onehead.lobby import Lobby
from onehead.store import GameStore


class TestStart:
    @pytest.mark.asyncio
    async def test_no_ihl_admin_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!start")

    @pytest.mark.asyncio
    async def test_game_in_progress(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True

        await dpytest.message("!start")
        assert dpytest.verify().message().content("Game already in progress...")

    @pytest.mark.asyncio
    async def test_game_no_signups(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        await dpytest.message("!start")
        assert dpytest.verify().message().content("There are currently no signups.")

    @pytest.mark.asyncio
    async def test_game_not_enough_signups(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")

        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))
        lobby._signups = {"BOB": datetime.now(), "BILL": datetime.now()}

        await dpytest.message("!start")
        assert dpytest.verify().message().content("Only `2` signup(s), require `8` more.")

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        await add_ihl_role(bot, "IHL Admin")

        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))
        players: list[Player] = lobby.database.get_all()[:10]
        lobby._signups = {player.name: datetime.now() for player in players}

        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        balance: AsyncMock = AsyncMock()
        balance.return_value = create_fake_team(), create_fake_team()

        coordinator.matchmaking.balance = balance
        coordinator.setup_team_channels = AsyncMock()

        with patch("onehead.game.ClassicGame.open_transfer_window"):
            with patch("onehead.game.Game.open_betting_window"):
                with patch("onehead.coordinator.play_sound"):
                    await dpytest.message("!start")

        assert dpytest.verify().message().content("Starting game:").contains()
        assert dpytest.verify().message().content("**Current Game**").contains()
        assert dpytest.verify().message().content("Create Dota 2 Lobby and join with the above teams.")
        assert dpytest.verify().message().content("GLHF")


class TestStop:
    @pytest.mark.asyncio
    async def test_no_ihl_admin_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!stop")

    @pytest.mark.asyncio
    async def test_no_active_game(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        await dpytest.message("!stop")
        assert dpytest.verify().message().content("No currently active game.")

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")

        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        coordinator.store.current_game = ClassicGame()
        coordinator.store.current_game._in_progress = True
        coordinator.betting.refund_all_bets = AsyncMock()
        coordinator.transfers.refund_transfers = AsyncMock()
        coordinator.channels.move_back_to_lobby = AsyncMock()
        coordinator.reset = AsyncMock()

        await dpytest.message("!stop")
        coordinator.betting.refund_all_bets.assert_called()
        coordinator.transfers.refund_transfers.assert_called()
        coordinator.reset.assert_called()


class TestResult:
    @pytest.mark.asyncio
    async def test_no_ihl_admin_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message(f"!result {Side.RADIANT}")

    @pytest.mark.asyncio
    async def test_no_active_game(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        await dpytest.message(f"!result {Side.RADIANT}")
        assert dpytest.verify().message().content("No currently active game.")

    @pytest.mark.asyncio
    async def test_transfer_window_open(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True
        store.current_game._transfer_window_open = True
        store.current_game._betting_window_open = False

        with pytest.raises(CommandInvokeError):
            await dpytest.message(f"!result {Side.RADIANT}")

        assert (
            dpytest.verify()
            .message()
            .content("Cannot enter result as the transfer window for the game is currently open")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_betting_window_open(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True
        store.current_game._transfer_window_open = False
        store.current_game._betting_window_open = True

        with pytest.raises(CommandInvokeError):
            await dpytest.message(f"!result {Side.RADIANT}")

        assert (
            dpytest.verify()
            .message()
            .content("Cannot enter result as the betting window for the game is currently open")
            .contains()
        )

    @pytest.mark.asyncio
    async def test_invalid_side(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True

        with pytest.raises(CommandInvokeError):
            await dpytest.message("!result derp")

        assert dpytest.verify().message().content(f"Must be either {Side.RADIANT} or {Side.DIRE}.")

    @pytest.mark.asyncio
    async def test_invalid_team(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True

        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        coordinator.channels.move_back_to_lobby = AsyncMock()

        with pytest.raises(CommandInvokeError):
            await dpytest.message(f"!result {Side.RADIANT}")

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL")
        await add_ihl_role(bot, "IHL Admin")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True
        store.current_game.radiant = (
            Player(
                id=262570465212497920,
                name="HARRY",
                mmr=4750,
                win=11,
                loss=11,
                win_streak=1,
                loss_streak=0,
                rbucks=100,
                rating=1500,
                commends=0,
                reports=1,
                behaviour=9800,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=252408793978241020,
                name="JEFFERIES",
                mmr=2706,
                win=12,
                loss=14,
                win_streak=1,
                loss_streak=0,
                rbucks=450,
                rating=1500,
                commends=0,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=213767888438427650,
                name="RUGOR",
                mmr=2100,
                win=10,
                loss=5,
                win_streak=0,
                loss_streak=1,
                rbucks=150,
                rating=1500,
                commends=1,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=141986719309234180,
                name="GEE",
                mmr=2524,
                win=18,
                loss=17,
                win_streak=0,
                loss_streak=1,
                rbucks=300,
                rating=1500,
                commends=1,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=880082547789430900,
                name="JORDAN",
                mmr=1215,
                win=15,
                loss=11,
                win_streak=1,
                loss_streak=0,
                rbucks=150,
                rating=1500,
                commends=0,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
        )

        store.current_game.dire = (
            Player(
                id=525045015093706750,
                name="LUKE",
                mmr=3200,
                win=11,
                loss=3,
                win_streak=5,
                loss_streak=0,
                rbucks=500,
                rating=1500,
                commends=1,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=252414167871389700,
                name="TOCCO",
                mmr=1950,
                win=8,
                loss=19,
                win_streak=2,
                loss_streak=0,
                rbucks=550,
                rating=1500,
                commends=1,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=210079807906643970,
                name="RBEEZAY",
                mmr=3700,
                win=14,
                loss=11,
                win_streak=1,
                loss_streak=0,
                rbucks=3948,
                rating=1500,
                commends=0,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=211554012082733060,
                name="ZEE",
                mmr=2995,
                win=6,
                loss=13,
                win_streak=0,
                loss_streak=2,
                rbucks=300,
                rating=1500,
                commends=0,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
            Player(
                id=432258130664095740,
                name="EDD",
                mmr=4224,
                win=7,
                loss=7,
                win_streak=0,
                loss_streak=1,
                rbucks=550,
                rating=1500,
                commends=0,
                reports=0,
                behaviour=10000,
                pos=None,
                adjusted_mmr=None,
                win_percentage=None,
            ),
        )

        store.current_game._bets = [
            Bet("HARRY", 262570465212497920, Side.RADIANT, 100),
            Bet("HARRY", 262570465212497920, Side.DIRE, 500),
        ]

        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        coordinator.scoreboard.scoreboard = AsyncMock()
        coordinator.reset = AsyncMock()
        coordinator.database.update = Mock()

        with patch("onehead.coordinator.play_sound"):
            await dpytest.message(f"!result {Side.RADIANT}")

        coordinator.reset.assert_called_once()


class TestStatus:
    @pytest.mark.asyncio
    async def test_no_ihl_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!status")

    @pytest.mark.asyncio
    async def test_no_active_game(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        await dpytest.message("!status")
        assert dpytest.verify().message().content("No currently active game.")

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._in_progress = True
        store.current_game.radiant = create_fake_team()
        store.current_game.dire = create_fake_team()

        await dpytest.message("!status")
        assert dpytest.verify().message().content("**Current Game**").contains()
