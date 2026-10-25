from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.member import Member
from discord.ext.commands import Bot

from onehead.betting import Bet, BetResult, Betting
from onehead.common import Side
from onehead.coordinator import GameCoordinator
from onehead.game import Challenge, ClassicGame
from onehead.store import GameStore

BETTOR_ID: int = 210079807906643980


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
        game._bets = [Bet(bettor="RBEEZAY", bettor_id=BETTOR_ID, selection=Side.RADIANT, stake=100, price=2.0)]
        store.current_game = game

        results: dict[int, list[BetResult]] = betting.get_bet_results(Side(typed.lower()))

        assert results[BETTOR_ID][0].win is True
        assert results[BETTOR_ID][0].winnings == 100
        assert results[BETTOR_ID][0].bettor == "RBEEZAY"

    @pytest.mark.asyncio
    async def test_a_bet_on_the_losing_side_does_not_pay_out(self, bot: Bot) -> None:
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        game: ClassicGame = ClassicGame()
        game._in_progress = True
        game._bets = [Bet(bettor="RBEEZAY", bettor_id=BETTOR_ID, selection=Side.DIRE, stake=100, price=2.0)]
        store.current_game = game

        results: dict[int, list[BetResult]] = betting.get_bet_results(Side.RADIANT)

        assert results[BETTOR_ID][0].win is False


class TestDuelBetsSettleOnIds:
    """
    A duel bet stored the backed duelist's display name and compared it against the
    winner's display name at result time, so renaming yourself mid-duel voided the bet.
    The same applied to the bettor, whose payout was looked up by name.
    """

    @pytest.mark.asyncio
    async def test_a_winning_duel_bet_pays_out_after_a_rename(self, bot: Bot) -> None:
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        # spec=Member so that get_bet_results takes its duel branch rather than its Side one.
        challenger = MagicMock(spec=Member)
        challenger.id = 111
        challenger.display_name = "THE_NAME_THEY_HAVE_NOW"

        game = Challenge(1, challenger, MagicMock(id=222))
        game._in_progress = True
        # The bet was placed when they were called something else.
        game._bets = [
            Bet(
                bettor="BETTOR",
                bettor_id=BETTOR_ID,
                selection="THE_NAME_THEY_HAD_THEN",
                selection_id=111,
                stake=100,
                price=2.0,
            )
        ]
        store.current_game = game

        results = betting.get_bet_results(challenger)

        assert results[BETTOR_ID][0].win is True
        assert results[BETTOR_ID][0].winnings == 100

    @pytest.mark.asyncio
    async def test_a_losing_duel_bet_still_loses(self, bot: Bot) -> None:
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        winner = MagicMock(spec=Member)
        winner.id = 222

        game = Challenge(1, MagicMock(id=111), winner)
        game._in_progress = True
        game._bets = [
            Bet(bettor="BETTOR", bettor_id=BETTOR_ID, selection="OTHER", selection_id=111, stake=100, price=2.0)
        ]
        store.current_game = game

        results = betting.get_bet_results(winner)

        assert results[BETTOR_ID][0].win is False
