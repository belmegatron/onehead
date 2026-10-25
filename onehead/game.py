import asyncio
from datetime import UTC, datetime, timedelta

from discord.ext.commands import Context
from discord.member import Member
from discord.user import User

from onehead.common import Bet, PlayerTransfer, Team


class Game:
    def __init__(self) -> None:
        self._in_progress: bool = False

        self._betting_window_open: bool = False
        self._bets: list[Bet] = []

    def in_progress(self) -> bool:
        return self._in_progress

    def start(self) -> None:
        self._in_progress = True

    def cancel(self) -> None:
        self._in_progress: bool = False

    async def open_betting_window(self, ctx: Context) -> None:
        self._betting_window_open = True

        await ctx.send("Bets are now open for `1` minute!")

        await asyncio.sleep(30)
        await ctx.send("`30` seconds remaining for bets!")
        await asyncio.sleep(30)

        self._betting_window_open = False
        await ctx.send("Bets are now closed!")

    def betting_window_open(self) -> bool:
        return self._betting_window_open

    def get_bets(self) -> list[Bet]:
        return self._bets


class ClassicGame(Game):
    def __init__(self) -> None:
        super().__init__()
        self._transfer_window_open: bool = False
        self._player_transfers: list[PlayerTransfer] = []
        self._commends: dict[str, list[str]] = {}
        self._reports: dict[str, list[str]] = {}

        self.radiant: Team | None = None
        self.dire: Team | None = None

    async def open_transfer_window(self, ctx: Context) -> None:
        self._transfer_window_open = True
        await ctx.send("Player transfer window is now open for `1` minute!")

        await asyncio.sleep(30)
        await ctx.send("`30` seconds remaining for transfers!")
        await asyncio.sleep(30)

        self._transfer_window_open = False
        await ctx.send("Player transfer window has now closed!")

    def transfer_window_open(self) -> bool:
        return self._transfer_window_open

    def get_player_transfers(self) -> list[PlayerTransfer]:
        return self._player_transfers

    def has_been_previously_commended(self, commender: str, commendee: str) -> bool:
        commends: list[str] | None = self._commends.get(commendee)
        return commends is not None and commender in commends

    def has_been_previously_reported(self, reporter: str, reported: str) -> bool:
        reports: list[str] | None = self._reports.get(reported)
        return reports is not None and reporter in reports

    def add_report(self, reporter: str, reported: str) -> None:
        updated_reports: list[str] | None = self._reports.get(reported)
        if updated_reports is None:
            self._reports[reported] = [reporter]
        else:
            updated_reports.append(reporter)

    def add_commend(self, commender: str, commendee: str) -> None:
        updated_commends: list[str] | None = self._commends.get(commendee)
        if updated_commends is None:
            self._commends[commendee] = [commender]
        else:
            updated_commends.append(commender)


class Challenge(Game):
    def __init__(self, id: int, challenger: Member | User, opponent: Member | User) -> None:
        super().__init__()
        self.id: int = id
        self.challenger: Member | User = challenger
        self.opponent: Member | User = opponent
        self.expires: datetime = datetime.now(tz=UTC) + timedelta(hours=24)
        self.handle_expiration_task: asyncio.Task | None = None

    def cancel_expiry(self) -> None:
        """
        Stop the expiry timer, as the challenge is no longer waiting on anyone.

        Not done on acceptance: the expiry task is the only thing that removes a
        challenge from the list, so cancelling it there left an accepted duel that no
        admin ever started sitting in the list forever, blocking its challenger from
        issuing another.
        """
        if self.handle_expiration_task:
            self.handle_expiration_task.cancel()
