import itertools
import random
from logging import Logger
from typing import Any, cast

from discord.ext.commands import Cog, Context, command, has_role
from discord.member import Member
from structlog import get_logger
from tabulate import tabulate

from onehead.common import (
    OneHeadException,
    Player,
    Roles,
    Team,
    TeamCombination,
    get_discord_member_from_name,
)
from onehead.interfaces.database import PlayerDatabase
from onehead.lobby import Lobby
from onehead.rating import Rating

log: Logger = get_logger()


class Matchmaking(Cog):
    def __init__(self, database: PlayerDatabase, lobby: Lobby) -> None:
        self.database: PlayerDatabase = database
        self.lobby: Lobby = lobby

    def _get_player_records(self, ctx: Context) -> list[Player]:
        """
        Obtains player records for all players that have signed up to play.

        :return: Player records for all signed up players.
        """
        players: list[Player] = []
        for player_name in self.lobby.get_signups():
            member: Member | None = get_discord_member_from_name(ctx, player_name)
            if member is None:
                continue
            player: Player | None = self.database.get(member.id)
            if player:
                players.append(player)

        return players

    @staticmethod
    def _calculate_unique_team_combinations(
        profiles: list[Player],
    ) -> list[TeamCombination]:
        """
        Calculates all 5v5 combinations, where the players on each team are unique to that particular team.

        Choosing Radiant determines Dire, as Dire is whoever is left over. Keeping one player on
        Radiant throughout also means each matchup is produced once rather than once per side, so
        there are no duplicates or overlaps to discard afterwards.

        :param profiles: Player profiles for the players that are playing.
        :return: Unique team combinations.
        """
        first: Player = profiles[0]
        rest: list[Player] = profiles[1:]

        unique_combinations: list[TeamCombination] = []

        for remainder in itertools.combinations(rest, 4):
            radiant: Team = cast(Team, (first,) + remainder)
            radiant_ids: set[int] = {player.id for player in radiant}
            dire: Team = cast(Team, tuple(player for player in profiles if player.id not in radiant_ids))
            unique_combinations.append((radiant, dire))

        return unique_combinations

    @staticmethod
    def _calculate_rating_differences(
        unique_combinations: list[TeamCombination],
    ) -> list[int]:
        """
        Calculates the net rating difference for each unique combination of teams based on their adjusted mmr.

        :param all_unique_combinations: All 5v5 unique combinations.
        :return: List total rating difference for each unique combination.
        """

        rating_differences: list[int] = []

        for combination in unique_combinations:
            t1_rating: int = sum([player.adjusted_mmr for player in combination[0] if player.adjusted_mmr])
            t2_rating: int = sum([player.adjusted_mmr for player in combination[1] if player.adjusted_mmr])

            rating_differences.append(abs(t1_rating - t2_rating))

        return rating_differences

    def _calculate_balance(self, ctx: Context) -> TeamCombination:
        """
        Calculate balanced lineups for Radiant/Dire.

        :return: Returns a matchup of two, five-man teams that are evenly (or as close to evenly) matched based on
        a rating value associated with each player.
        """
        profiles: list[Player] = self._get_player_records(ctx)
        profile_count: int = len(profiles)
        if profile_count != 10:
            raise OneHeadException(f"Only `{profile_count}` profiles could be found in database.")

        # Two signups resolving to the same member would otherwise yield a team of fewer
        # than five players, as Dire is whoever is not on Radiant.
        if len({player.id for player in profiles}) != profile_count:
            raise OneHeadException("No valid matchups could be calculated. Possible duplicate player name.")

        Rating.calculate_rating(profiles)
        Rating.calculate_adjusted_mmr(profiles)

        unique_combinations: list[TeamCombination] = self._calculate_unique_team_combinations(profiles)

        rating_differences: list[int] = self._calculate_rating_differences(unique_combinations)

        # Sort by ascending rating difference
        sorted_unique_combinations: list[TeamCombination] = [
            combo for _, combo in sorted(zip(rating_differences, unique_combinations, strict=False))
        ]

        # Take the top 20 that are closest in terms of rating and pick one at random.
        balanced_teams: TeamCombination = random.choice(sorted_unique_combinations[:20])

        return balanced_teams

    async def balance(self, ctx: Context) -> tuple[Team, Team]:
        """
        Returns two balanced 5-man teams from 10 players in the signup pool.

        :param ctx: Discord context.
        :return: Balanced teams.
        """
        signup_count: int = len(self.lobby.get_signups())
        await ctx.send("Balancing teams...")
        if signup_count != 10:
            err: str = f"Only `{signup_count}` Signups, require `{10 - signup_count}` more."
            await ctx.send(err)

        radiant: Team
        dire: Team

        radiant, dire = self._calculate_balance(ctx)

        radiant_mmr: int = sum([player.adjusted_mmr for player in radiant if player.adjusted_mmr])
        dire_mmr: int = sum([player.adjusted_mmr for player in dire if player.adjusted_mmr])

        mmr_message: str = f"Radiant: `{radiant_mmr}` MMR, Dire: `{dire_mmr}` MMR."
        log.info(mmr_message)
        await ctx.send(mmr_message)

        return radiant, dire

    @has_role(Roles.MEMBER)
    @command()
    async def mmr(self, ctx: Context) -> None:
        """
        Shows the internal MMR used for balancing teams.
        """
        scoreboard: list[Player] = self.database.get_all()
        Rating.calculate_rating(scoreboard)
        Rating.calculate_adjusted_mmr(scoreboard)

        ratings: list[dict[str, Any]] = [
            {
                "name": record.name,
                "base": record.mmr,
                "adjusted": record.adjusted_mmr,
            }
            for record in scoreboard
        ]
        sorted_ratings: list[dict[str, Any]] = sorted(ratings, key=lambda k: k["adjusted"], reverse=True)
        tabulated_ratings: str = tabulate(sorted_ratings, headers="keys", tablefmt="simple")
        await ctx.send(f"**Internal MMR** ```\n{tabulated_ratings}```")
