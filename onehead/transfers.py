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
from structlog import get_logger

from onehead.common import (
    OneHeadException,
    Player,
    PlayerTransfer,
    Roles,
    Team,
    get_command_from_cog,
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
    # The draw picks at random from the 20 closest matchups, so a repeat is uncommon and a
    # run of them vanishingly so. Give up after this many and hand over what we drew.
    MAX_SHUFFLE_ATTEMPTS: int = 10

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

        refunded: int = 0

        for transfer in transfers:
            record: Player | None = self.database.get(transfer.buyer_id)
            if record is None:
                log.error(f"Unable to refund {transfer.amount} RBUCKS as buyer {transfer.buyer_id} is not in database.")
                continue

            record.rbucks += transfer.amount
            self.database.update(record)
            refunded += 1

        # Do not claim everyone got their money back when someone did not.
        if refunded == len(transfers):
            message: str = "All player transactions have been refunded."
        else:
            message = f"`{refunded}` of `{len(transfers)}` player transactions have been refunded."

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

        # Check the teams rather than the signups, which are keyed by display name - a
        # player who renamed after signing up is still on a team.
        participants: set[int] = {player.id for player in current_game.radiant + current_game.dire}

        if ctx.author.id not in participants:
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
        # Draw again if we landed on the teams we already had. calculate_balance rather than
        # balance, so a redraw does not repeat the "Balancing teams..." and MMR messages,
        # and bounded, because this used to loop until the dice obliged.
        attempts: int = 0
        while current_teams_names_only == shuffled_teams_names_only and attempts < self.MAX_SHUFFLE_ATTEMPTS:
            shuffled_teams = self.matchmaking.calculate_balance(ctx)
            shuffled_teams_names_only = get_player_names(shuffled_teams[0], shuffled_teams[1])
            attempts += 1

        # Charge only once there is a shuffle to hand over. balance raises whenever the
        # signups have changed since the teams were picked - an admin using !rm during the
        # transfer window is enough - and charging beforehand left the player out of pocket
        # with the teams untouched until someone stopped the game.
        record.rbucks -= Transfers.SHUFFLE_COST
        self.database.update(record)
        transfers.append(PlayerTransfer(ctx.author.id, Transfers.SHUFFLE_COST))

        current_game.radiant, current_game.dire = shuffled_teams

        await ctx.send(f"{ctx.author.mention} has spent **{Transfers.SHUFFLE_COST}** RBUCKS to **shuffle** the teams!")

        command: Command | None = get_command_from_cog(self.store, "status")
        if command:
            await Command.invoke(command, ctx)
