from dataclasses import asdict, dataclass
from logging import Logger
from typing import cast

from discord.ext.commands import Cog, Context, command, has_role
from discord.member import Member
from structlog import get_logger
from tabulate import tabulate

from onehead.challenge import ChallengeMode
from onehead.common import (
    Bet,
    OneHeadException,
    Player,
    Roles,
    Side,
    get_discord_member_from_name,
    play_sound,
)
from onehead.game import Challenge, ClassicGame, Game
from onehead.interfaces.database import PlayerDatabase
from onehead.lobby import Lobby
from onehead.store import GameStore

log: Logger = get_logger()


@dataclass
class BetResult:
    win: bool
    stake: float = 0
    winnings: float = 0


class Betting(Cog):
    INITIAL_BALANCE: int = 100
    REWARD_ON_WIN: int = 100
    REWARD_ON_LOSS: int = 50

    def __init__(self, store: GameStore, database: PlayerDatabase, lobby: Lobby) -> None:
        self.store: GameStore = store
        self.database: PlayerDatabase = database
        self.lobby: Lobby = lobby

    def get_bet_results(self, winner: Side | Member) -> dict[str, list[BetResult]]:
        current_game: Game | None = self.store.current_game

        bet_results: dict[str, list[BetResult]] = {}

        if current_game is None:
            return bet_results

        active_bets: list[Bet] = current_game.get_bets()

        for bet in active_bets:
            if bet_results.get(bet.bettor) is None:
                bet_results[bet.bettor] = []

            if isinstance(winner, Member):
                winner = cast(Member, winner)
                winner_name: str = winner.display_name
            else:
                winner_name = winner

            if bet.selection == winner_name:
                bet_result: BetResult = BetResult(
                    win=True,
                    stake=bet.stake,
                    winnings=(bet.stake * bet.price) - bet.stake,
                )
            else:
                bet_result: BetResult = BetResult(win=False, winnings=(-1 * bet.stake))
            bet_results[bet.bettor].append(bet_result)

        return bet_results

    @has_role(Roles.MEMBER)
    @command()
    async def bets(self, ctx: Context) -> None:
        """
        Lists active bets for the current game.
        """
        current_game: Game | None = self.store.current_game

        if current_game is None:
            await ctx.send("There is no active game to currently bet on.")
            return

        active_bets: list[Bet] = current_game.get_bets()
        bets: list[dict[str, str | int | float]] = [asdict(bet) for bet in active_bets]

        table_of_bets: str = tabulate(bets, headers="keys", tablefmt="simple")

        await ctx.send(f"**Bets** ```\n{table_of_bets}```")

    @has_role(Roles.MEMBER)
    @command(aliases=["bet"])
    async def place_bet(self, ctx: Context, first: str, second: str) -> None:
        """
        Place a bet on the match that is about to happen.

        e.g. !bet radiant 500 or !bet dire all or !bet 500 radiant or bet all dire
        """

        current_game: Game | None = self.store.current_game

        if current_game is None:
            await ctx.send("Unable to bet as there is currently no game being played.")
            return

        if current_game.betting_window_open() is False:
            await ctx.send("Betting window closed.")
            return

        record: Player | None = self.database.get(ctx.author.id)
        if record is None:
            await ctx.send(f"Unable to find {ctx.author.mention} in database.")
            return None

        available_balance: int = record.rbucks
        if available_balance == 0:
            await ctx.send(f"{ctx.author.mention} cannot bet as they have no available RBUCKS.")
            return

        bet: Bet | None = await self.parse_bet_arguments(ctx, current_game, first, second, record)
        if bet is None:
            return

        if bet.stake <= 0:
            await ctx.send(f"{ctx.author.mention} - Bet stake must be greater than 0.")
            return

        if bet.stake > available_balance:
            await ctx.send(
                f"Unable to place bet - {ctx.author.mention} tried to stake `{bet.stake:.0f}` RBUCKS but only has `{available_balance:.0f}` RBUCKS available."
            )
            return

        if isinstance(current_game, Challenge):
            if ctx.author in (current_game.challenger, current_game.opponent):
                await ctx.send(f"{ctx.author.mention} cannot place a bet on this duel as they are participating in it!")
                return

            challenger_price, opponent_price = self.calculate_challenge_odds(current_game)

            if bet.selection == current_game.challenger.display_name:
                bet.price = challenger_price
            else:
                bet.price = opponent_price

        bets: list[Bet] = current_game.get_bets()
        bets.append(bet)

        record.rbucks -= bet.stake
        self.database.update(record)

        await play_sound(ctx, "bet.mp3")

        log.info(
            f"{ctx.author.display_name} has placed a bet of {bet.stake:.0f} RBUCKS on {bet.selection} at a price of {bet.price}."
        )

        await ctx.send(
            f"{ctx.author.mention} has placed a bet of `{bet.stake:.0f}` RBUCKS on {bet.selection} at a price of `{bet.price}`."
        )

    @has_role(Roles.MEMBER)
    @command()
    async def rbucks(self, ctx: Context) -> None:
        """
        Lists the number of rbucks each member of the IHL has.
        """
        subset: list = []

        table: list[Player] = self.database.get_all()

        for player in table:
            subset.append({"name": player.name, "RBUCKS": player.rbucks})

        subset = sorted(subset, key=lambda d: d["RBUCKS"], reverse=True)  # type: ignore
        bucks_board: str = tabulate(subset, headers="keys", tablefmt="simple")
        await ctx.send(f"**RBUCKS** ```\n{bucks_board}```")

    @staticmethod
    def create_bet_report(bet_results: dict[str, list[BetResult]]) -> str:
        contents: str = ""

        for name, results in bet_results.items():
            for result in results:
                won_or_lost: str = "won" if result.win else "lost"
                line: str = f"{name} {won_or_lost} {abs(result.winnings):.0f} RBUCKS!"
                log.info(line)
                contents += line
                contents += "\n"

        return f"**Bet results**\n```{contents}```"

    async def refund_all_bets(self, ctx: Context) -> None:
        current_game: Game | None = self.store.current_game

        if current_game is None:
            return

        active_bets: list[Bet] = current_game.get_bets()

        if len(active_bets) == 0:
            return

        for bet in active_bets:
            member: Member | None = get_discord_member_from_name(ctx, bet.bettor)
            if member:
                record: Player | None = self.database.get(member.id)
                if record:
                    record.rbucks += bet.stake
                    self.database.update(record)

        log.info("Refunded all bets.")
        await ctx.send("All bets have been refunded.")

    async def parse_bet_arguments(
        self, ctx: Context, current_game: Game, first: str, second: str, record: Player
    ) -> Bet | None:
        selection: str = ""
        amount: str = ""

        if isinstance(current_game, ClassicGame):
            if first in Side:
                selection = first
                amount = second
            elif second in Side:
                selection = second
                amount = first
            else:
                await ctx.send(f"{ctx.author.mention}, you must bet on either {Side.RADIANT} or {Side.DIRE}.")
                return None
        elif isinstance(current_game, Challenge):
            member: Member | None = get_discord_member_from_name(ctx, first)
            if member in (current_game.challenger, current_game.opponent):
                selection = member.display_name
                amount = second
            else:
                member = get_discord_member_from_name(ctx, second)
                if member in (current_game.challenger, current_game.opponent):
                    selection = member.display_name
                    amount = first

            if selection == "":
                await ctx.send(
                    f"{ctx.author.mention}, you must specify either {current_game.challenger.mention} or {current_game.opponent.mention}."
                )
                return None

        available_balance: int = record.rbucks
        stake: int = 0

        if amount == "all":
            stake = available_balance
        else:
            try:
                stake = int(amount)
            except ValueError:
                await ctx.send(
                    f"{ctx.author.mention} - `{amount}` is not a valid number of RBUCKS to place a bet with."
                )

        return Bet(bettor=ctx.author.display_name, selection=selection, stake=stake)

    @staticmethod
    def convert_decimal_odds_to_percentage_odds(decimal_odds: float) -> float:
        return (1.0 / decimal_odds) * 100

    @staticmethod
    def convert_percentage_odds_to_decimal(percentage_odds: float) -> float:
        return 1.0 / (percentage_odds / 100.0)

    def calculate_challenge_odds(self, challenge: Challenge) -> tuple[float, float]:
        challenger: Player | None = self.database.get(challenge.challenger.id)
        opponent: Player | None = self.database.get(challenge.opponent.id)

        if challenger is None or opponent is None:
            raise OneHeadException(
                f"Cannot calculate odds for challenge {challenge.id} as "
                f"{challenge.challenger.display_name} or {challenge.opponent.display_name} "
                "is no longer in the database."
            )

        mmr_difference: int = challenger.mmr - opponent.mmr

        challenger_decimal_odds: float = 2.0
        opponent_decimal_odds: float = 2.0
        scaled_difference: float = abs(float(mmr_difference / ChallengeMode.MAX_RATING_DIFFERENCE))

        # Ensure that this does not exceed 0.99, otherwise we may calculate the favourted runner to have odds of <= 1.0.
        scaled_difference = min(scaled_difference, 0.99)

        # Challenger is favoured
        if mmr_difference > 0:
            challenger_decimal_odds -= scaled_difference
            challenger_percentage_odds = self.convert_decimal_odds_to_percentage_odds(challenger_decimal_odds)
            opponent_percentage_odds = 100 - challenger_percentage_odds
            opponent_decimal_odds: float = self.convert_percentage_odds_to_decimal(opponent_percentage_odds)

        # Opponent is favoured.
        elif mmr_difference < 0:
            opponent_decimal_odds -= scaled_difference
            opponent_percentage_odds = self.convert_decimal_odds_to_percentage_odds(opponent_decimal_odds)
            challenger_percentage_odds = 100 - opponent_percentage_odds
            challenger_decimal_odds: float = self.convert_percentage_odds_to_decimal(challenger_percentage_odds)

        return round(challenger_decimal_odds, 2), round(opponent_decimal_odds, 2)
