from datetime import datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import discord.ext.test as dpytest
import pytest
from conftest import add_ihl_role, create_fake_player, create_fake_team
from discord.ext.commands import Bot

from onehead.betting import Betting
from onehead.common import Metadata, OneHeadException, Player
from onehead.coordinator import GameCoordinator
from onehead.game import Challenge, ClassicGame
from onehead.lobby import Lobby
from onehead.matchmaking import Matchmaking
from onehead.registration import Registration
from onehead.store import GameStore


def make_ctx() -> AsyncMock:
    """
    Build a context with no voice client, so voice_client_disconnect returns at once
    rather than parking on a mock that never stops playing.

    :return: The context.
    """
    ctx = AsyncMock()
    ctx.voice_client = None

    return ctx


class TestResetWithoutTeams:
    """
    reset built its move_back_to_lobby arguments eagerly, and get_discord_members raises
    when the teams are None - reachable whenever a game dies before being balanced. reset
    then propagated, so current_game stayed set and !start reported "Game already in
    progress" until the process was restarted.
    """

    @pytest.mark.asyncio
    async def test_reset_completes_when_the_game_was_never_balanced(self, bot: Bot) -> None:
        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        game: ClassicGame = ClassicGame()
        game._in_progress = True
        assert game.radiant is None and game.dire is None
        store.current_game = game

        await coordinator.reset(make_ctx())

        assert store.current_game is None

    @pytest.mark.asyncio
    async def test_a_game_can_be_started_again_afterwards(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")

        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        game: ClassicGame = ClassicGame()
        game._in_progress = True
        store.current_game = game

        await coordinator.reset(make_ctx())
        await dpytest.message("!start")

        # Reaching the signup check at all means current_game was cleared properly.
        assert dpytest.verify().message().content("There are currently no signups.")

    @pytest.mark.asyncio
    async def test_a_challenge_missing_from_the_list_does_not_raise(self, bot: Bot) -> None:
        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))

        challenge: Challenge = Challenge(1, MagicMock(), MagicMock())
        store.current_game = challenge
        assert challenge not in coordinator.challenge_mode.challenges

        await coordinator.reset(make_ctx())

        assert store.current_game is None


class TestConcurrentStart:
    @pytest.mark.asyncio
    async def test_a_second_start_is_rejected_while_the_first_is_running(self, bot: Bot) -> None:
        await add_ihl_role(bot, "IHL Admin")

        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        # max_concurrency cannot see this - the command returns before the work is done.
        coordinator.start_tasks.add(MagicMock())

        await dpytest.message("!start")

        assert dpytest.verify().message().content("Game is already starting...")


class TestBetPayoutResilience:
    @pytest.mark.asyncio
    async def test_a_deregistered_bettor_does_not_block_the_others(self, bot: Bot) -> None:
        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        present: Player = coordinator.database.get_all()[0]
        starting_rbucks: int = present.rbucks

        coordinator.betting.get_bet_results = MagicMock(
            return_value={
                "GHOST": [MagicMock(win=True, stake=100, winnings=100)],
                present.name: [MagicMock(win=True, stake=50, winnings=50)],
            }
        )
        coordinator.betting.create_bet_report = MagicMock(return_value="report")

        def resolve(ctx, name):
            member = MagicMock()
            member.id = 0 if name == "GHOST" else present.id
            return member

        import onehead.coordinator as coordinator_module

        original = coordinator_module.get_discord_member_from_name
        coordinator_module.get_discord_member_from_name = resolve
        try:
            await coordinator.handle_bet_results(AsyncMock(), MagicMock())
        finally:
            coordinator_module.get_discord_member_from_name = original

        # The present bettor is paid even though the ghost could not be.
        assert coordinator.database.get(present.id).rbucks == starting_rbucks + 100


class TestBalanceSignupCount:
    @pytest.mark.asyncio
    async def test_balance_stops_rather_than_pressing_on(self, bot: Bot) -> None:
        matchmaking: Matchmaking = cast(Matchmaking, bot.get_cog("Matchmaking"))
        matchmaking.lobby = MagicMock()
        matchmaking.lobby.get_signups.return_value = ["ONE", "TWO"]

        with pytest.raises(OneHeadException, match="require `8` more"):
            await matchmaking.balance(AsyncMock())


class TestEndOfSeason:
    @pytest.mark.parametrize(
        ("game_id", "expected"),
        [(1, False), (49, False), (50, False), (51, True), (52, True)],
    )
    def test_the_season_ends_after_the_full_count_of_games(self, bot: Bot, game_id: int, expected: bool) -> None:
        coordinator: GameCoordinator = cast(GameCoordinator, bot.get_cog("GameCoordinator"))
        coordinator.database = MagicMock()
        coordinator.database.get_metadata.return_value = Metadata(
            timestamp=0.0, season=1, game_id=game_id, max_game_count=50
        )

        assert coordinator.is_end_of_season() is expected


class TestCleanupInactivePlayers:
    @pytest.mark.asyncio
    async def test_stale_signups_are_reaped_when_no_game_is_running(self, bot: Bot, monkeypatch) -> None:
        """
        current_game was snapshotted before the loop, when it is almost always None, and the
        sweep was skipped unless it was truthy - so stale signups were never reaped.
        """
        import onehead.lobby as lobby_module

        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))
        lobby.store.current_game = None
        lobby._signups = {
            "STALE": datetime.now() - timedelta(hours=5),
            "FRESH": datetime.now(),
        }

        async def stop_after_one_pass(_: float) -> None:
            raise StopAsyncIteration

        monkeypatch.setattr(lobby_module, "sleep", stop_after_one_pass)

        with pytest.raises(StopAsyncIteration):
            await lobby.cleanup_inactive_players(AsyncMock())

        assert "STALE" not in lobby._signups
        assert "FRESH" in lobby._signups

    @pytest.mark.asyncio
    async def test_the_flag_is_cleared_so_a_new_sweep_can_start(self, bot: Bot, monkeypatch) -> None:
        import onehead.lobby as lobby_module

        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))
        lobby.store.current_game = None
        lobby._signups = {}

        async def stop_after_one_pass(_: float) -> None:
            raise StopAsyncIteration

        monkeypatch.setattr(lobby_module, "sleep", stop_after_one_pass)

        with pytest.raises(StopAsyncIteration):
            await lobby.cleanup_inactive_players(AsyncMock())

        assert lobby._cleanup_is_running is False


class TestSummonWithoutTheRole:
    """
    The role was looked up with `[x for x in guild.roles if ...][0]`, which raises
    IndexError when no IHL role exists, and the `if not ihl_role` guard beneath it was
    dead code - a Role is always truthy.
    """

    @pytest.mark.asyncio
    async def test_a_missing_ihl_role_is_reported_rather_than_raising(self, bot: Bot) -> None:
        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))

        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.name = "Test Guild"
        ctx.guild.roles = []

        await lobby.summon.callback(lobby, ctx)

        assert "No `IHL` role exists" in ctx.send.await_args.args[0]

    @pytest.mark.asyncio
    async def test_the_role_is_mentioned_when_it_exists(self, bot: Bot) -> None:
        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))

        role = MagicMock()
        role.name = "IHL"
        role.mention = "<@&1>"

        ctx = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.roles = [role]

        await lobby.summon.callback(lobby, ctx)

        assert "<@&1>" in ctx.send.await_args.args[0]


class TestRecalibrateValidation:
    @pytest.mark.parametrize("mmr", [str(Registration.MIN_MMR - 1), str(Registration.MAX_MMR + 1), "derp"])
    @pytest.mark.asyncio
    async def test_out_of_range_or_junk_mmr_is_rejected(self, bot: Bot, mmr: str) -> None:
        registration: Registration = cast(Registration, bot.get_cog("Registration"))
        player: Player = registration.database.get_all()[0]
        starting_mmr: int = player.mmr

        import onehead.registration as registration_module

        member = MagicMock()
        member.id = player.id
        monkey = registration_module.get_discord_member_from_name
        registration_module.get_discord_member_from_name = lambda ctx, name: member
        try:
            await registration.recalibrate.callback(registration, AsyncMock(), player.name, mmr)
        finally:
            registration_module.get_discord_member_from_name = monkey

        assert registration.database.get(player.id).mmr == starting_mmr


class TestChallengeOddsWithMissingPlayer:
    def test_a_missing_player_raises_a_usable_error(self, bot: Bot) -> None:
        betting: Betting = cast(Betting, bot.get_cog("Betting"))

        challenger = MagicMock()
        challenger.id = 0
        challenger.display_name = "GHOST"
        opponent = MagicMock()
        opponent.id = 0
        opponent.display_name = "ALSO_GHOST"

        challenge: Challenge = Challenge(7, challenger, opponent)

        # A bare `raise` here used to produce RuntimeError: No active exception to re-raise.
        with pytest.raises(OneHeadException, match="no longer in the database"):
            betting.calculate_challenge_odds(challenge)


class TestSelectPlayersWithRenamedMember:
    @pytest.mark.asyncio
    async def test_a_renamed_player_is_still_selectable(self, bot: Bot) -> None:
        """
        Selection compared the database name against signups keyed by display name, so a
        player who changed their nickname after registering was dropped even when they were
        in the top ten - leaving fewer than ten selected and wedging the start.
        """
        import onehead.lobby as lobby_module

        lobby: Lobby = cast(Lobby, bot.get_cog("Lobby"))
        players: list[Player] = lobby.database.get_all()[:11]

        # The player signed up under a new nickname, while the database still has the old one.
        renamed: Player = players[0]
        signups: dict[str, datetime] = {"NEW_NICKNAME": datetime.now()}
        signups.update({player.name: datetime.now() for player in players[1:]})
        lobby._signups = dict(signups)

        by_signup: dict[str, Player] = {"NEW_NICKNAME": renamed}
        by_signup.update({player.name: player for player in players[1:]})

        def resolve(ctx, name):
            member = MagicMock()
            member.id = by_signup[name].id
            member.display_name = name
            member.mention = f"<@{by_signup[name].id}>"
            return member

        original = lobby_module.get_discord_member_from_name
        lobby_module.get_discord_member_from_name = resolve
        try:
            await lobby.select_players(AsyncMock())
        finally:
            lobby_module.get_discord_member_from_name = original

        assert len(lobby._signups) == 10
        # Highest behaviour scores win; whoever is dropped must be the lowest scorer, not
        # simply the renamed player.
        dropped: set[str] = set(signups) - set(lobby._signups)
        lowest: Player = min(players, key=lambda p: p.behaviour)
        assert dropped == {name for name, player in by_signup.items() if player.id == lowest.id}


class TestBehaviourWithRenamedMember:
    """
    commend and report checked participation by comparing the author's display name
    against the registered names held in the teams, so a player who changed their
    Discord nickname after registering was told they had not played.
    """

    @pytest.mark.asyncio
    async def test_a_renamed_participant_can_still_commend(self, bot: Bot) -> None:
        from conftest import join_member

        store: GameStore = cast(GameStore, bot.get_cog("GameStore"))
        behaviour = bot.get_cog("Behaviour")

        author = list(bot.get_all_members())[0]
        target = await join_member(bot, "RBEEZAY")

        game: ClassicGame = ClassicGame()
        # The author played, but their record still carries the name they registered under.
        game.radiant = (
            Player(id=author.id, name="NAME_FROM_BEFORE_THE_RENAME", mmr=3000),
            Player(id=target.id, name="RBEEZAY", mmr=3000),
            create_fake_player(),
            create_fake_player(),
            create_fake_player(),
        )
        game.dire = create_fake_team()
        store.previous_game = game

        behaviour.database.get = MagicMock(return_value=Player(id=target.id, name="RBEEZAY", mmr=3000, behaviour=5000))
        behaviour.database.update = MagicMock()

        await add_ihl_role(bot, "IHL")
        await dpytest.message("!commend RBEEZAY")

        assert dpytest.verify().message().content("has been commended").contains()
