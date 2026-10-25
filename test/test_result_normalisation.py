from typing import cast
from unittest.mock import AsyncMock

import pytest
from discord.ext.commands import Bot

from onehead.betting import Bet, BetResult, Betting
from onehead.common import Side
from onehead.coordinator import GameCoordinator
from onehead.game import ClassicGame
from onehead.store import GameStore


class TestBetSelectionMatchesTheWinner:
    """
    `!result Radiant` used to score the game correctly and then void every winning bet.

    `handle_classic_game_result` lowercased its own local copy of the argument, while
    `result` took the winner from the raw argument, so the winner reaching
    `get_bet_results` kept the casing the admin typed. Selections are only ever stored
    lower case, so nothing matched and every bettor lost their stake.
    """

    @pytest.mark.parametrize("typed", ["radiant", "Radiant", "RADIANT"])
    @pytest.mark.asyncio
    async def test_result_hands_the_normalised_side_to_betting(self, bot: Bot, typed: str) -> None:
        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        store.current_game = ClassicGame()
        store.current_game._in_progress = True

        coordinator.handle_classic_game_result = AsyncMock(return_value=Side(typed.lower()))
        coordinator.handle_bet_results = AsyncMock()
        coordinator.reset = AsyncMock()

        ctx = AsyncMock()
        await GameCoordinator.result(coordinator, ctx, typed)

        coordinator.handle_bet_results.assert_awaited_once()
        passed_winner = coordinator.handle_bet_results.await_args.args[1]
        assert passed_winner == Side.RADIANT
        assert passed_winner == "radiant"

    @pytest.mark.parametrize("typed", ["radiant", "Radiant", "RADIANT"])
    @pytest.mark.asyncio
    async def test_a_bet_on_the_winning_side_pays_out(self, bot: Bot, typed: str) -> None:
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        game: ClassicGame = ClassicGame()
        game._in_progress = True
        # parse_bet_arguments only ever stores a lower case side.
        game._bets = [Bet(bettor="RBEEZAY", selection=Side.RADIANT, stake=100, price=2.0)]
        store.current_game = game

        results: dict[str, list[BetResult]] = betting.get_bet_results(Side(typed.lower()))

        assert results["RBEEZAY"][0].win is True
        assert results["RBEEZAY"][0].winnings == 100

    @pytest.mark.asyncio
    async def test_a_bet_on_the_losing_side_does_not_pay_out(self, bot: Bot) -> None:
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        game: ClassicGame = ClassicGame()
        game._in_progress = True
        game._bets = [Bet(bettor="RBEEZAY", selection=Side.DIRE, stake=100, price=2.0)]
        store.current_game = game

        results: dict[str, list[BetResult]] = betting.get_bet_results(Side.RADIANT)

        assert results["RBEEZAY"][0].win is False
