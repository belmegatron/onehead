from logging import Logger
from typing import cast

from discord.ext.commands import Cog, Context, command, has_role
from discord.guild import Guild
from discord.member import Member
from discord.user import User
from structlog import get_logger

from onehead.common import (
    OneHeadException,
    Player,
    Roles,
    get_discord_member_from_name,
)
from onehead.game import ClassicGame, Game
from onehead.interfaces.database import PlayerDatabase
from onehead.store import GameStore

log: Logger = get_logger()


class Behaviour(Cog):
    MAX_BEHAVIOUR_SCORE = 10000
    MIN_BEHAVIOUR_SCORE = 0
    COMMEND_MODIFIER = 100
    REPORT_MODIFIER = -200

    def __init__(self, store: GameStore, database: PlayerDatabase) -> None:
        self.store: GameStore = store
        self.database: PlayerDatabase = database

    @has_role(Roles.MEMBER)
    @command()
    async def commend(self, ctx: Context, target: str) -> None:
        """
        Commend a player for playing well.
        """
        previous_game: Game | None = self.store.previous_game
        if previous_game is None:
            await ctx.send("Unable to commend as a game is yet to be played.")
            return

        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        if isinstance(previous_game, ClassicGame):
            previous_game = cast(ClassicGame, previous_game)

            if previous_game.radiant is None or previous_game.dire is None:
                return

            commender: Member | User = ctx.author

            # Match on id rather than name - the teams hold registered names, which a
            # player who has since changed their Discord nickname no longer matches.
            participants: set[int] = {player.id for player in previous_game.radiant + previous_game.dire}

            if commender.id not in participants:
                await ctx.send(
                    f"{commender.mention} did not participate in the previous game and therefore cannot commend another player."
                )
                return

            commendee: Member | None = get_discord_member_from_name(ctx, target)

            if commendee is None:
                await ctx.send(f"Unable to commend {target} as they do not exist in the {guild.name} guild.")
                return

            if commender.id == commendee.id:
                await ctx.send(f"{commender.mention} you cannot commend yourself, nice try...")
                return

            if commendee.id not in participants:
                await ctx.send(
                    f"{commendee.mention} cannot be commended as they did not participate in the previous game."
                )
                return

            if previous_game.has_been_previously_commended(commender.display_name, commendee.display_name):
                await ctx.send(f"{commendee.mention} has already been commended by {commender.mention}.")
                return

            commendee_record: Player | None = self.database.get(commendee.id)
            if commendee_record is None:
                await ctx.send(f"{commendee.mention} could not be found in the database.")
                return

            current_behaviour_score: int = commendee_record.behaviour
            new_score: int = min(
                current_behaviour_score + self.COMMEND_MODIFIER,
                self.MAX_BEHAVIOUR_SCORE,
            )

            commendee_record.behaviour = new_score
            commendee_record.commends += 1
            self.database.update(commendee_record)

            previous_game.add_commend(commender.display_name, commendee.display_name)

            log.info(f"{commender.display_name} commended {commendee.display_name}.")

            await ctx.send(f"{commendee.mention} has been commended by {commender.mention}.")

    @has_role(Roles.MEMBER)
    @command()
    async def report(self, ctx: Context, target: str, reason: str) -> None:
        """
        Report a player for intentionally ruining the game experience.
        """
        previous_game: Game | None = self.store.previous_game
        if previous_game is None:
            await ctx.send("Unable to report as a game is yet to be played.")
            return

        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        if isinstance(previous_game, ClassicGame) is False:
            raise OneHeadException("Attempted to report a player in a game which was not a ClassicGame")

        previous_game = cast(ClassicGame, previous_game)

        if previous_game.radiant is None or previous_game.dire is None:
            raise OneHeadException("Failed to report a player due to invalid game state in previous game")

        reporter: Member | User = ctx.author

        # Match on id rather than name, as above.
        participants: set[int] = {player.id for player in previous_game.radiant + previous_game.dire}

        if reporter.id not in participants:
            await ctx.send(
                f"{reporter.mention} did not participate in the previous game and therefore cannot report another player."
            )
            return

        reported: Member | None = get_discord_member_from_name(ctx, target)
        if reported is None:
            await ctx.send(f"Unable to report {target} as they do not exist in {guild.name}")
            return

        if reporter.id == reported.id:
            await ctx.send(
                f"{reporter.mention} has brought dishonour upon themselves and has attempted to commit seppuku. OneHead will now allow it... UWU!"
            )
            return

        if reported.id not in participants:
            await ctx.send(f"{reported.mention} cannot be reported as they did not participate in the previous game.")
            return

        if previous_game.has_been_previously_reported(reporter.display_name, reported.display_name):
            await ctx.send(f"{reported.mention} has already been reported by {reporter.mention}.")
            return

        reported_record: Player | None = self.database.get(reported.id)
        if reported_record is None:
            await ctx.send(f"{reported.mention} could not be found in the database.")
            return

        current_behaviour_score: int = reported_record.behaviour
        new_score: int = max(current_behaviour_score + self.REPORT_MODIFIER, self.MIN_BEHAVIOUR_SCORE)

        reported_record.behaviour = new_score
        reported_record.reports += 1
        self.database.update(reported_record)

        previous_game.add_report(reporter.display_name, reported.display_name)

        log.info(f"{reporter.display_name} reported {reported.display_name} for the following reason: {reason}.")

        await ctx.send(f"{reported.mention} has been reported.")
