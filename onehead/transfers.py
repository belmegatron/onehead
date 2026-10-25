from logging import Logger
from typing import cast

from discord.ext.commands import (
    BucketType,
    Cog,
    Command,
    Context,
    command,
    has_role,
    max_concurrency,
)
from discord.member import Member
from structlog import get_logger

from onehead.common import (
    OneHeadException,
    Player,
    PlayerTransfer,
    Roles,
    Team,
    get_command_from_cog,
    get_discord_member_from_name,
    get_player_names,
    play_sound,
)
from onehead.game import ClassicGame
from onehead.interfaces.database import PlayerDatabase
from onehead.lobby import Lobby
from onehead.matchmaking import Matchmaking
from onehead.store import GameStore

log: Logger = get_logger()


class Transfers(Cog):
    SHUFFLE_COST: int = 500

    def __init__(
        self,
        store: GameStore,
        database: PlayerDatabase,
        lobby: Lobby,
        matchmaking: Matchmaking,
    ) -> None:
        self.store: GameStore = store
        self.database: PlayerDatabase = database
        self.lobby: Lobby = lobby
        self.matchmaking: Matchmaking = matchmaking

    async def refund_transfers(self, ctx: Context) -> None:
        if isinstance(self.store.current_game, ClassicGame) is False:
            return

        current_game: ClassicGame = cast(ClassicGame, self.store.current_game)

        transfers: list[PlayerTransfer] = current_game.get_player_transfers()

        if len(transfers) == 0:
            return

        for transfer in transfers:
            member: Member | None = get_discord_member_from_name(ctx, transfer.buyer)
            if member:
                record: Player | None = self.database.get(member.id)
                if record is None:
                    continue

                record.rbucks += transfer.amount
                self.database.update(record)

        message: str = "All player transactions have been refunded."
        log.info(message)
        await ctx.send(message)

    @has_role(Roles.MEMBER)
    @command()
    # Unlike !start this does its work inline, so the slot is held for the whole shuffle.
    # Without it two quick !shuffles both read the same balance and both write it
    # decremented once, giving two shuffles for the price of one.
    @max_concurrency(1, per=BucketType.default, wait=False)
    async def shuffle(self, ctx: Context) -> None:
        """
        Shuffles teams (costs 500 RBUCKS)
        """
        if isinstance(self.store.current_game, ClassicGame) is False:
            return

        current_game: ClassicGame = cast(ClassicGame, self.store.current_game)

        transfers: list[PlayerTransfer] = current_game.get_player_transfers()

        if current_game.transfer_window_open() is False:
            await ctx.send("Unable to shuffle as player transfer window is closed.")
            return

        if current_game.radiant is None or current_game.dire is None:
            raise OneHeadException(f"Expected valid teams: {current_game.radiant}, {current_game.dire}")

        name: str = ctx.author.display_name

        if name not in self.lobby.get_signups():
            await ctx.send(
                f"{ctx.author.mention} is unable to shuffle as they are not participating in the current game."
            )
            return

        record: Player | None = self.database.get(ctx.author.id)
        if record is None:
            await ctx.send(f"Unable to find {ctx.author.mention} in database.")
            return

        current_balance: int = record.rbucks

        if current_balance < self.SHUFFLE_COST:
            await ctx.send(
                f"{ctx.author.mention} cannot shuffle as they only have {current_balance} "
                f"RBUCKS. A shuffle costs {Transfers.SHUFFLE_COST} RBUCKS."
            )
            return

        await play_sound(ctx, "transfer.mp3")

        current_teams_names_only: tuple[tuple[str, ...], tuple[str, ...]] = get_player_names(
            current_game.radiant, current_game.dire
        )

        shuffled_teams: tuple[Team, Team] = await self.matchmaking.balance(ctx)

        shuffled_teams_names_only: tuple[tuple[str, ...], tuple[str, ...]] = get_player_names(
            shuffled_teams[0], shuffled_teams[1]
        )

        # TODO: Can we try and ensure at least 2 players have changed from the previous 2 shuffles?
        while current_teams_names_only == shuffled_teams_names_only:
            shuffled_teams = await self.matchmaking.balance(ctx)
            shuffled_teams_names_only = get_player_names(shuffled_teams[0], shuffled_teams[1])

        # Charge only once there is a shuffle to hand over. balance raises whenever the
        # signups have changed since the teams were picked - an admin using !rm during the
        # transfer window is enough - and charging beforehand left the player out of pocket
        # with the teams untouched until someone stopped the game.
        record.rbucks -= Transfers.SHUFFLE_COST
        self.database.update(record)
        transfers.append(PlayerTransfer(name, Transfers.SHUFFLE_COST))

        current_game.radiant, current_game.dire = shuffled_teams

        await ctx.send(f"{ctx.author.mention} has spent **{Transfers.SHUFFLE_COST}** RBUCKS to **shuffle** the teams!")

        command: Command | None = get_command_from_cog(self.store, "status")
        if command:
            await Command.invoke(command, ctx)
