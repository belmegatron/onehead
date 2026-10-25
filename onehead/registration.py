from logging import Logger

from discord.ext.commands import Cog, Context, command, has_role
from discord.guild import Guild
from discord.member import Member
from structlog import get_logger

from onehead.common import OneHeadException, Player, Roles, get_discord_member_from_name
from onehead.interfaces.database import PlayerDatabase

log: Logger = get_logger()


class Registration(Cog):
    MIN_MMR: int = 1000
    MAX_MMR: int = 10000

    def __init__(self, database: PlayerDatabase) -> None:
        self.database: PlayerDatabase = database

    async def _validate_mmr(self, ctx: Context, mmr: str, usage: str) -> int | None:
        """
        Check an MMR argument is a number within the bounds the IHL accepts.

        :param ctx: Discord context.
        :param mmr: The MMR as the user typed it.
        :param usage: Example of correct usage, shown when the MMR is not a number.
        :return: The MMR, or None if it was not usable - the caller has been told why.
        """
        try:
            mmr_int: int = int(mmr)
        except ValueError:
            await ctx.send(f"{ctx.author.mention}, the command you are looking for is {usage}")
            return None

        if mmr_int < self.MIN_MMR:
            await ctx.send(f"`{mmr}` MMR is too low, must be greater or equal to `{self.MIN_MMR}`.")
            return None

        if mmr_int > self.MAX_MMR:
            await ctx.send(f"`{mmr}` MMR is too high, must be less than or equal to `{self.MAX_MMR}`.")
            return None

        return mmr_int

    @has_role(Roles.MEMBER)
    @command(aliases=["reg"])
    async def register(self, ctx: Context, mmr: str) -> None:
        """
        Register yourself to the IHL by typing !register <your mmr>.
        """
        mmr_int: int | None = await self._validate_mmr(ctx, mmr, "`!register <MMR>` (e.g. `!register 9000`)")
        if mmr_int is None:
            return

        player: Player | None = self.database.get(ctx.author.id)
        if player is None:
            self.database.add(ctx.author.id, ctx.author.display_name, mmr_int)
            log.info(f"{ctx.author.display_name} registered with an MMR of {mmr}.")
            await ctx.send(f"{ctx.author.mention} successfully registered.")
        else:
            await ctx.send(f"{ctx.author.mention} is already registered.")

    @has_role(Roles.ADMIN)
    @command(aliases=["dereg"])
    async def deregister(self, ctx: Context, name: str) -> None:
        """
        Removes a player from the internal IHL database.
        """
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        member: Member | None = get_discord_member_from_name(ctx, name)
        if member is None:
            await ctx.send(f"{name} could not be found in the {guild.name} guild.")
            return

        player: Player | None = self.database.get(member.id)

        if player and member:
            self.database.remove(member.id)
            log.info(f"{name} has been deregistered by {ctx.author.display_name}.")
            await ctx.send(f"{member.mention} has been deregistered.")
        else:
            await ctx.send(f"{member.mention} could not be found in the database.")

    @has_role(Roles.ADMIN)
    @command(aliases=["recal"])
    async def recalibrate(self, ctx: Context, name: str, new_mmr: str) -> None:
        """
        Update a player's in-house MMR to reflect a recent change in Dota 2 MMR.
        """
        member: Member | None = get_discord_member_from_name(ctx, name)

        if member is None:
            await ctx.send(f"{name} is not a registered member.")
            return

        record: Player | None = self.database.get(member.id)
        if record is None:
            await ctx.send(f"Unable to recalibrate {member.mention} as they do not exist in the database.")
            return

        # An out of range MMR here would corrupt team balancing just as surely as one
        # given to !register, so hold it to the same bounds.
        mmr_int: int | None = await self._validate_mmr(
            ctx, new_mmr, f"`!recalibrate <name> <MMR>` (e.g. `!recalibrate {name} 9000`)"
        )
        if mmr_int is None:
            return

        record.mmr = mmr_int
        self.database.update(record)

        log.info(f"{name} has had their MMR changed to {new_mmr} by {ctx.author.name}.")
        await ctx.send(f"{member.mention} has had their MMR changed to `{new_mmr}` by {ctx.author.mention}.")
