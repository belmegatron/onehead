from typing import cast
from unittest.mock import MagicMock, Mock, patch

import discord.ext.test as dpytest
import pytest
from conftest import add_ihl_role
from discord.ext.commands import Bot, errors
from discord.member import Member

from onehead.betting import Bet, Betting
from onehead.challenge import Challenge
from onehead.common import Player, Side
from onehead.database import Database
from onehead.game import ClassicGame
from onehead.store import GameStore


class TestBets:
    @pytest.mark.asyncio
    async def test_no_ihl_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!bets")

    @pytest.mark.asyncio
    async def test_no_bets(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        await dpytest.message("!bets")
        assert dpytest.verify().message().content("There is no active game to currently bet on.")

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._bets.append(
            Bet(selection="dire", stake=1000, bettor="RBEEZAY", bettor_id=210079807906643980)
        )

        await dpytest.message("!bets")
        assert dpytest.verify().message().content("**Bets** ```\n").contains()


class TestPlaceBet:
    @pytest.mark.asyncio
    async def test_no_ihl_role(self, bot: Bot) -> None:
        with pytest.raises(errors.MissingRole):
            await dpytest.message("!bets")

    @pytest.mark.asyncio
    async def test_betting_window_closed(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        await dpytest.message("!bet dire all")
        assert dpytest.verify().message().content("Betting window closed.")

    @pytest.mark.asyncio
    async def test_player_does_not_exist(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True
        await dpytest.message(f"!bet {Side.RADIANT} all")
        assert dpytest.verify().message().content("Unable to find").contains()

    @pytest.mark.asyncio
    async def test_available_balance_is_zero(self, bot: Bot) -> None:
        member: Member = await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL", "RBEEZAY")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True

        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database.get = Mock()
        betting.database.get.return_value = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=0)

        await dpytest.message(f"!bet {Side.RADIANT} all", 0, member)
        assert dpytest.verify().message().content("cannot bet as they have no available RBUCKS.").contains()

    @pytest.mark.asyncio
    async def test_invalid_side(self, bot: Bot) -> None:
        member: Member = await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL", "RBEEZAY")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True

        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database.get = Mock()
        betting.database.get.return_value = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)

        await dpytest.message("!bet derp all", 0, member)
        assert dpytest.verify().message().content(f"you must bet on either {Side.RADIANT} or {Side.DIRE}.").contains()

    @pytest.mark.asyncio
    async def test_stake_not_valid_int(self, bot: Bot) -> None:
        member: Member = await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL", "RBEEZAY")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True

        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database.get = Mock()
        betting.database.get.return_value = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)

        await dpytest.message(f"!bet {Side.RADIANT} foobar", 0, member)
        assert dpytest.verify().message().content("is not a valid number of RBUCKS").contains()

    @pytest.mark.asyncio
    async def test_stake_negative_int(self, bot: Bot) -> None:
        member: Member = await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL", "RBEEZAY")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True

        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database.get = Mock()
        betting.database.get.return_value = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)

        await dpytest.message(f"!bet {Side.RADIANT} -100", 0, member)
        assert dpytest.verify().message().content("stake must be greater than 0.").contains()

    @pytest.mark.asyncio
    async def test_stake_greater_than_balance(self, bot: Bot) -> None:
        member: Member = await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL", "RBEEZAY")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True

        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database.get = Mock()
        record = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)
        betting.database.get.return_value = record

        stake: int = record.rbucks + 100
        await dpytest.message(f"!bet {Side.RADIANT} {stake:.0f}", 0, member)
        assert dpytest.verify().message().content("Unable to place bet").contains()

    @pytest.mark.asyncio
    async def test_success(self, bot: Bot) -> None:
        member: Member = await dpytest.member_join(name="RBEEZAY")
        await add_ihl_role(bot, "IHL", "RBEEZAY")
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        store.current_game = ClassicGame()
        store.current_game._betting_window_open = True

        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database.get = Mock()
        betting.database.get.return_value = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)
        betting.database.update = Mock()

        with patch("onehead.betting.play_sound"):
            await dpytest.message(f"!bet {Side.RADIANT} all", 0, member)
            assert dpytest.verify().message().content("has placed a bet").contains()


class TestCalculateOdds:
    @pytest.mark.asyncio
    async def test_challenger_favoured(self, bot: Bot) -> None:
        db = MagicMock(spec=Database)
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database = db
        challenger: Member = await dpytest.member_join(name="RBEEZAY")
        opponent: Member = await dpytest.member_join(name="GEE")

        challenger_record: Player = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)
        opponent_record: Player = Player(name="GEE", id=0, mmr=2000, rbucks=100)

        db.get.side_effect = [challenger_record, opponent_record]

        challenge: Challenge = Challenge(0, challenger, opponent)

        challenger_odds, opponent_odds = betting.calculate_challenge_odds(challenge)
        assert challenger_odds == 1.75
        assert opponent_odds == 2.33

    @pytest.mark.asyncio
    async def test_opponent_favoured(self, bot: Bot) -> None:
        db: MagicMock = MagicMock(spec=Database)
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database = db
        challenger: Member = await dpytest.member_join(name="RBEEZAY")
        opponent: Member = await dpytest.member_join(name="GEE")

        challenger_record: Player = Player(name="RBEEZAY", id=0, mmr=2000, rbucks=100)
        opponent_record: Player = Player(name="GEE", id=0, mmr=3000, rbucks=100)

        db.get.side_effect = [challenger_record, opponent_record]

        challenge: Challenge = Challenge(0, challenger, opponent)

        challenger_odds, opponent_odds = betting.calculate_challenge_odds(challenge)
        assert challenger_odds == 2.33
        assert opponent_odds == 1.75

    @pytest.mark.asyncio
    async def test_equal_odds(self, bot: Bot) -> None:
        db = MagicMock(spec=Database)
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database = db
        challenger: Member = await dpytest.member_join(name="RBEEZAY")
        opponent: Member = await dpytest.member_join(name="GEE")

        challenger_record: Player = Player(name="RBEEZAY", id=0, mmr=3000, rbucks=100)
        opponent_record: Player = Player(name="GEE", id=0, mmr=3000, rbucks=100)

        db.get.side_effect = [challenger_record, opponent_record]

        challenge: Challenge = Challenge(0, challenger, opponent)

        challenger_odds, opponent_odds = betting.calculate_challenge_odds(challenge)
        assert challenger_odds == 2.0
        assert opponent_odds == 2.0

    @pytest.mark.asyncio
    async def test_mmr_difference_greater_than_max_diff(self, bot: Bot) -> None:
        db = MagicMock(spec=Database)
        betting: Betting = cast(Betting, bot.get_cog("Betting"))
        betting.database = db
        challenger: Member = await dpytest.member_join(name="RBEEZAY")
        opponent: Member = await dpytest.member_join(name="GEE")

        challenger_record: Player = Player(name="RBEEZAY", id=0, mmr=2000, rbucks=100)
        opponent_record: Player = Player(name="GEE", id=0, mmr=6010, rbucks=100)

        db.get.side_effect = [challenger_record, opponent_record]

        challenge: Challenge = Challenge(0, challenger, opponent)

        challenger_odds, opponent_odds = betting.calculate_challenge_odds(challenge)
        assert challenger_odds == 101.0
        assert opponent_odds == 1.01
