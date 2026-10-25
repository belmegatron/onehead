from asyncio import sleep
from datetime import datetime, timedelta
from logging import Logger
from typing import Any

from discord.ext.commands import (
    BucketType,
    Cog,
    Command,
    Context,
    command,
    cooldown,
    has_role,
    max_concurrency,
)
from discord.guild import Guild
from discord.member import Member
from discord.role import Role
from discord.utils import get
from structlog import get_logger
from tabulate import tabulate

from onehead.common import (
    OneHeadException,
    Player,
    Roles,
    create_background_task,
    get_discord_member_from_name,
    play_sound,
)
from onehead.game import Game
from onehead.interfaces.database import PlayerDatabase
from onehead.store import GameStore

log: Logger = get_logger()


class Lobby(Cog):
    def __init__(self, store: GameStore, database: PlayerDatabase) -> None:
        self.store: GameStore = store
        self.database: PlayerDatabase = database
        self._signups: dict[str, datetime] = {}
        self._players_ready: list[str] = []
        self._ready_check_in_progress: bool = False
        self._context: Context | None = None
        self._signups_disabled: bool = False
        self._cleanup_is_running: bool = False

    def disable_signups(self) -> None:
        self._signups_disabled = True

    def clear_signups(self) -> None:
        self._signups = {}
        self._signups_disabled = False

    def get_signups(self) -> list[str]:
        return list(self._signups.keys())

    def remove_player_from_signups(self, name: str) -> None:
        del self._signups[name]

    @has_role(Roles.ADMIN)
    @command()
    async def summon(self, ctx: Context) -> None:
        """
        Messages all registered players of the IHL to come and sign up.
        """
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord context.")

        ihl_role: Role | None = get(guild.roles, name=str(Roles.MEMBER))
        if ihl_role is None:
            await ctx.send(f"No `{Roles.MEMBER}` role exists in {guild.name}.")
            return

        await ctx.send(f"IHL DOTA - LET'S GO! {ihl_role.mention}")

    async def signup_check(self, ctx: Context) -> bool:
        signup_count: int = len(self._signups)
        if signup_count < 10:
            if signup_count == 0:
                await ctx.send("There are currently no signups.")
            else:
                await ctx.send(f"Only `{signup_count}` signup(s), require `{10 - signup_count}` more.")
        else:
            return True

        return False

    @has_role(Roles.ADMIN)
    @command()
    async def clear(self, ctx: Context) -> None:
        """
        Clears all current signups.
        """
        self._signups.clear()
        await ctx.send("Cleared signups.")

    async def select_players(self, ctx: Context) -> None:
        """
        Handle the case where there are less than 10 signups, exactly 10 signups or more than 10 signups. If there are
        more, then players will be randomly removed until there are only 10 players in self.signups.

        :param ctx: Discord context
        """
        number_of_signups: int = len(self._signups)
        if number_of_signups <= 10:
            return

        await ctx.send(
            f"`{number_of_signups}` Players have signed up and therefore `{number_of_signups - 10}` players will be benched."
        )

        if len(self._signups) > 10:
            await ctx.send(
                "More than `10` signups identified, selecting the top `10` players with the highest behaviour score."
            )

            original_signups: list[str] = self.get_signups()

            # Keep each signup alongside the member and record it resolved to. Selecting on
            # the database name instead would drop anyone who changed their Discord
            # nickname after registering, as the signups are keyed by display name.
            candidates: list[tuple[str, Member, Player]] = []

            for signup in original_signups:
                member: Member | None = get_discord_member_from_name(ctx, signup)
                if member is None:
                    continue

                player: Player | None = self.database.get(member.id)

                if player is None:
                    raise OneHeadException(f"Unable to find {signup} in database.")

                candidates.append((signup, member, player))

            top_10_by_behaviour_score: list[tuple[str, Member, Player]] = sorted(
                candidates, key=lambda candidate: candidate[2].behaviour, reverse=True
            )[:10]
            selected_signups: set[str] = {signup for signup, _, _ in top_10_by_behaviour_score}

            self._signups = {name: ts for name, ts in self._signups.items() if name in selected_signups}

            benched_players: list[str] = [
                member.mention for signup, member, _ in candidates if signup not in selected_signups
            ]
            selected_players: list[str] = [member.mention for _, member, _ in top_10_by_behaviour_score]

            await ctx.send(f"**Benched Players:** \n{', '.join(benched_players)}")
            await ctx.send(f"**Selected Players:** \n{', '.join(selected_players)}")

    @has_role(Roles.MEMBER)
    @command()
    async def who(self, ctx: Context) -> None:
        """
        Shows all players currently signed up to play in the IHL.
        """
        await ctx.send(f"There are currently `{len(self._signups)}` players signed up.")
        signups: list[dict[str, Any]] = [{"#": i, "name": name} for i, name in enumerate(self._signups, start=1)]
        if len(signups) > 0:
            signups_table: str = tabulate(signups, headers="keys", tablefmt="simple")
            await ctx.send(f"**Current Signups** ```\n{signups_table}```")

    @cooldown(1, 10, BucketType.user)
    @has_role(Roles.MEMBER)
    @command(aliases=["su"])
    async def signup(self, ctx: Context) -> None:
        """
        Signup to join a game in the IHL.
        """
        if self._signups_disabled:
            await ctx.send("Game in progress - `!su` command unavailable.")
            return

        name: str = ctx.author.display_name
        player: Player | None = self.database.get(ctx.author.id)
        if player is None:
            await ctx.send("Please register first using the `!register` command.")
            return

        if name in self._signups:
            await ctx.send(f"{ctx.author.mention} is already signed up.")
            return
        else:
            self._signups[name] = datetime.now()

        if self._context is None:
            self._context = ctx

        log.info(f"{name} has signed up.")

        if self._cleanup_is_running is False:
            create_background_task(self.cleanup_inactive_players(ctx), "cleanup_inactive_players")

        await Command.invoke(self.who, ctx)

    @cooldown(1, 10, BucketType.user)
    @has_role(Roles.MEMBER)
    @command(aliases=["so"])
    async def signout(self, ctx: Context) -> None:
        """
        Remove yourself from the current pool of signed up players.
        """
        if self._signups_disabled:
            await ctx.send("Game in progress - `!so` command unavailable.")
            return

        name: str = ctx.author.display_name

        if name not in self._signups:
            await ctx.send(f"{ctx.author.mention} is not currently signed up.")
        else:
            self.remove_player_from_signups(name)

        log.info(f"{name} has signed out.")

        await Command.invoke(self.who, ctx)

    @has_role(Roles.ADMIN)
    @command(aliases=["rm"])
    async def remove(self, ctx: Context, name: str) -> None:
        """
        Remove a player who is currently signed up.
        """
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        if name not in self._signups:
            await ctx.send(f"{name} is not currently signed up.")
            return

        self.remove_player_from_signups(name)

        log.info(f"{name} has been removed from the signup pool by {ctx.author.display_name}.")

        member: Member | None = get_discord_member_from_name(ctx, name)
        if member is None:
            await ctx.send(f"{name} could not be found in the {guild.name} guild.")
            return

        await ctx.send(f"{member.mention} has been removed from the signup pool.")

    @has_role(Roles.MEMBER)
    @command(aliases=["r"])
    async def ready(self, ctx: Context) -> None:
        """
        Use this command in response to a ready check.
        """
        name: str = ctx.author.display_name

        if name not in self._signups:
            await ctx.send(f"{ctx.author.mention} needs to sign in first.")
            return

        if self._ready_check_in_progress is False:
            await ctx.send("No ready check initiated.")
            return

        self._players_ready.append(name)

        log.info(f"{name} is ready.")

        await ctx.send(f"{ctx.author.mention} is ready.")

    @has_role(Roles.MEMBER)
    @command(aliases=["rc"])
    @max_concurrency(1, per=BucketType.default, wait=False)
    async def ready_check(self, ctx: Context) -> None:
        """
        Initiates a ready check, after approx. 30s the result of the check will be displayed.
        """
        if await self.signup_check(ctx):
            await play_sound(ctx, "ready.mp3")

            log.info(f"{ctx.author.display_name} initiated a ready check.")
            await ctx.send("Ready check started - `30s` remaining - type `!ready` to ready up.")
            self._ready_check_in_progress = True
            await sleep(30)

            players_not_ready: list[str] = [name for name in self._signups if name not in self._players_ready]
            mentions_not_ready: list[str] = []
            for name in players_not_ready:
                member: Member | None = get_discord_member_from_name(ctx, name)
                if member:
                    mentions_not_ready.append(member.mention)

            if len(players_not_ready) == 0:
                await ctx.send("Ready check complete.")
            else:
                log.info(f"{len(players_not_ready)} not ready: {', '.join(players_not_ready)}.")
                await ctx.send(f"Still waiting on `{len(players_not_ready)}` players: {', '.join(mentions_not_ready)}.")

        self._ready_check_in_progress = False
        self._players_ready = []

    async def cleanup_inactive_players(self, ctx: Context) -> None:
        """
        This task runs periodically to check for if there are any 'stale' signups in the lobby.
        Some players never seem to trigger an 'Idle' or 'Offline' status change and therefore
        the `on_presence_update` callback never gets called for them.
        """
        max_signup_period: timedelta = timedelta(hours=4)
        self._cleanup_is_running = True

        try:
            while True:
                # Read the game each time round. Snapshotting it before the loop pinned it
                # to whatever was going on at the first signup - almost always nothing - so
                # the sweep below never ran. Stale signups matter precisely when no game is
                # running, so a missing game must not skip it either.
                current_game: Game | None = self.store.current_game

                to_remove: list[str] = []

                if current_game is None or current_game.in_progress() is False:
                    for name, signup_time in self._signups.items():
                        if datetime.now() >= (signup_time + max_signup_period):
                            to_remove.append(name)

                for name in to_remove:
                    self.remove_player_from_signups(name)
                    member: Member | None = get_discord_member_from_name(ctx, name)
                    log.debug(
                        f"{name} was removed from the signup pool by {ctx.bot.user.name} due to being inactive for over {max_signup_period}."
                    )
                    if member:
                        await ctx.send(
                            f"{member.mention} has been removed from the signup pool by {ctx.bot.user.mention} due to being inactive for over `{max_signup_period}`."
                        )

                await sleep(3600)
        finally:
            # Let the next signup start a fresh sweep if this one died or was cancelled.
            self._cleanup_is_running = False
