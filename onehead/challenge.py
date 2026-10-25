import itertools
from asyncio import create_task, sleep
from datetime import UTC, datetime, timedelta
from logging import Logger
from typing import Any

from discord.ext.commands import Cog, Context, command, has_role
from discord.guild import Guild
from discord.member import Member
from discord.user import User
from pytz import timezone
from structlog import get_logger
from tabulate import tabulate

from onehead.common import (
    OneHeadException,
    Player,
    Roles,
    create_background_task,
    get_discord_member_from_id,
    get_discord_member_from_name,
    play_sound,
    voice_client_disconnect,
)
from onehead.game import Challenge
from onehead.interfaces.database import PlayerDatabase

log: Logger = get_logger()


class ChallengeMode(Cog):
    MAX_RATING_DIFFERENCE: int = 4000

    counter = itertools.count()

    def __init__(self, database: PlayerDatabase) -> None:
        self.database: PlayerDatabase = database
        self.challenges: list[Challenge] = []

    @has_role(Roles.MEMBER)
    @command()
    async def challenge(self, ctx: Context, opponent_name: str) -> None:
        """
        Challenge an opponent to a 1v1 mid duel e.g. !challenge ERIC
        Your opponent can accept by issuing the !accept <Challenger> command e.g. !accept GEE
        An admin can then start the challenge by issuing the `!start <Challenge ID>` command e.g. `!start 0`
        You can check currently active challenges by issuing the `!challenges` command.
        """
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        challenger: Member | User = ctx.author
        opponent: Member | None = get_discord_member_from_name(ctx, opponent_name)

        if opponent is None:
            raise OneHeadException(f"Failed to challenge {opponent_name} as they do not exist in {guild.name}")

        if challenger == opponent:
            await ctx.send("You cannot challenge yourself...")
            return

        for challenge in self.challenges:
            if challenge.challenger.id == challenger.id:
                opponent = get_discord_member_from_id(ctx, challenge.opponent.id)
                if opponent:
                    await ctx.send(
                        f"{challenger.mention} has already issued a challenge to {opponent.mention}!\n Stop sending for man, kmt."
                    )
                return
            elif challenge.opponent.id == opponent.id:
                other_challenger: Member | None = get_discord_member_from_id(ctx, challenge.challenger.id)
                if other_challenger:
                    await ctx.send(f"{opponent.mention} has already been challenged by {other_challenger.mention}!")
                return

        challenger_record: Player | None = self.database.get(challenger.id)
        opponent_record: Player | None = self.database.get(opponent.id)

        if challenger_record is None or opponent_record is None:
            raise OneHeadException(
                f"Failed to obtain database record for {challenger.display_name if challenger_record is None else opponent.display_name}"
            )

        # Deliberately one directional: challenging far above your MMR is allowed, picking
        # on someone far below it is not. Do not be tempted to make this abs().
        if challenger_record.mmr - opponent_record.mmr > self.MAX_RATING_DIFFERENCE:
            await play_sound(ctx, "bully.mp3")
            await ctx.send(
                f"{challenger.mention}, your opponent cannot be more than `{self.MAX_RATING_DIFFERENCE}` "
                "MMR below you. Pick on someone your own size."
            )
            return

        # TODO: Persist challenges to database.
        await play_sound(ctx, "challenger.mp3")

        await ctx.send(f"{challenger.mention} has challenged {opponent.mention} to a 1v1 mid!")
        await ctx.send(
            f"{opponent.mention} has 24 hours to accept this challenge, if they wish to accept, type `!accept` {challenger.mention}."
        )

        challenge: Challenge = Challenge(next(self.counter), challenger=challenger, opponent=opponent)
        challenge.handle_expiration_task = create_task(self.handle_expired_challenge(ctx, challenge))
        create_background_task(voice_client_disconnect(ctx), "voice_client_disconnect")
        self.challenges.append(challenge)

    @has_role(Roles.MEMBER)
    @command(aliases=["challenges"])
    async def list_challenges(self, ctx: Context) -> None:
        """
        Lists all active challenges.
        """
        challenges: list[dict[str, Any]] = []
        for challenge in self.challenges:
            sorted_challenge: dict[str, Any] = {
                "id": challenge.id,
                "challenger": challenge.challenger.display_name,
                "opponent": challenge.opponent.display_name,
                "in_progress": challenge.in_progress(),
                "expires": challenge.expires.astimezone(timezone("Europe/London")).strftime("%d/%m/%Y, %H:%M:%S"),
            }
            challenges.append(sorted_challenge)

        if len(challenges) == 0:
            await ctx.send("There are no active challenges.")
        else:
            sorted: str = tabulate(challenges, headers="keys", tablefmt="simple")
            await ctx.send(f"**Challenges** ```\n{sorted}```")

    @has_role(Roles.MEMBER)
    @command()
    async def accept(self, ctx: Context, name: str) -> None:
        """
        Accept a duel issued by a challenger e.g. `!accept BOBBY`
        """
        challenge: Challenge | None = await self.find_issued_challenge(ctx, name)

        if challenge:
            if challenge.in_progress() is False:
                challenge.start()
                await ctx.send(
                    f"{challenge.opponent.mention} has accepted their duel vs. {challenge.challenger.mention}!"
                )
                await ctx.send(f"Start this 1v1 duel by asking an admin to type `!start {challenge.id}`")
            else:
                await ctx.send(
                    f"{challenge.opponent.mention} has already accepted their duel vs. {challenge.challenger.mention}!"
                )
                await ctx.send(f"To start the game, ask an admin to type `!start {challenge.id}`")
        else:
            await ctx.send(f"Unable to find challenge issued to {ctx.author.mention} by {name}.")

    @has_role(Roles.MEMBER)
    @command()
    async def reject(self, ctx: Context, name: str) -> None:
        """
        Reject a duel issued by a challenger e.g. `!reject BOBBY`
        """
        challenge: Challenge | None = await self.find_issued_challenge(ctx, name)

        if challenge:
            await ctx.send(
                f"{challenge.opponent.mention} has rejected the challenge issued by {challenge.challenger.mention}."
            )
            await play_sound(ctx, "shame.mp3")
            if challenge.handle_expiration_task:
                challenge.handle_expiration_task.cancel()
            self.challenges.remove(challenge)
        else:
            await ctx.send(f"Unable to find challenge issued to {ctx.author.mention} by {name}.")

        create_background_task(voice_client_disconnect(ctx), "voice_client_disconnect")

    async def find_issued_challenge(self, ctx: Context, challenger_name: str) -> Challenge | None:
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        challenged: Member | User = ctx.author
        challenger: Member | None = get_discord_member_from_name(ctx, challenger_name)
        if challenger is None:
            raise OneHeadException(
                f"Unable to find {challenger_name} in {guild.name} when searching for issued challenge"
            )

        for challenge in self.challenges:
            if challenge.opponent.id == challenged.id and challenge.challenger.id == challenger.id:
                return challenge

        return None

    async def handle_expired_challenge(self, ctx: Context, challenge: Challenge) -> None:
        to_wait: timedelta = challenge.expires - datetime.now(UTC)

        # TODO: Maybe break this up and add reminder messages.
        await sleep(to_wait.total_seconds())

        if challenge.complete is False:
            await ctx.send(
                f"{challenge.opponent.mention} has failed to accept {challenge.challenger.mention}'s request to duel (id: `{challenge.id}`) due to it expiring."
            )

        try:
            self.challenges.remove(challenge)
        except ValueError:
            pass
