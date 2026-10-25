import itertools

import pytest

from onehead.common import Player, Team, TeamCombination
from onehead.matchmaking import Matchmaking


def make_profiles(count: int = 10) -> list[Player]:
    """
    Build a set of player profiles with distinct ids and ratings.

    :param count: How many profiles to build.
    :return: The profiles.
    """
    profiles: list[Player] = []
    for i in range(count):
        player: Player = Player(id=i + 1, name=f"PLAYER{i}", mmr=1000 + (i * 350))
        player.adjusted_mmr = player.mmr
        profiles.append(player)

    return profiles


def brute_force_combinations(profiles: list[Player]) -> list[TeamCombination]:
    """
    The previous implementation, kept here as the reference to compare against.

    Every pair of five-man teams is generated and those sharing a player discarded.

    :param profiles: Player profiles for the players that are playing.
    :return: Unique team combinations.
    """
    teams: list[Team] = list(itertools.combinations(profiles, 5))
    matchups: list[TeamCombination] = list(itertools.combinations(teams, 2))

    unique: list[TeamCombination] = []
    for matchup in matchups:
        if not any(player in matchup[1] for player in matchup[0]):
            unique.append(matchup)

    return unique


def as_matchup_set(combinations: list[TeamCombination]) -> set[frozenset[frozenset[int]]]:
    """
    Reduce combinations to comparable form, ignoring which side is which and player order.

    :param combinations: The team combinations to reduce.
    :return: One entry per matchup, each holding the two sets of player ids.
    """
    return {
        frozenset((frozenset(p.id for p in radiant), frozenset(p.id for p in dire))) for radiant, dire in combinations
    }


class TestCalculateUniqueTeamCombinations:
    def test_matches_the_brute_force_result(self) -> None:
        profiles: list[Player] = make_profiles()

        actual: list[TeamCombination] = Matchmaking._calculate_unique_team_combinations(profiles)

        assert as_matchup_set(actual) == as_matchup_set(brute_force_combinations(profiles))

    def test_produces_every_matchup_exactly_once(self) -> None:
        profiles: list[Player] = make_profiles()

        combinations: list[TeamCombination] = Matchmaking._calculate_unique_team_combinations(profiles)

        # 10 players split into two fixed teams of five gives C(9,4) distinct matchups.
        assert len(combinations) == 126
        assert len(as_matchup_set(combinations)) == 126

    def test_teams_are_five_a_side_and_share_nobody(self) -> None:
        profiles: list[Player] = make_profiles()
        expected_ids: set[int] = {player.id for player in profiles}

        for radiant, dire in Matchmaking._calculate_unique_team_combinations(profiles):
            radiant_ids: set[int] = {player.id for player in radiant}
            dire_ids: set[int] = {player.id for player in dire}

            assert len(radiant) == 5
            assert len(dire) == 5
            assert radiant_ids.isdisjoint(dire_ids)
            assert radiant_ids | dire_ids == expected_ids

    def test_rating_differences_line_up_with_the_combinations(self) -> None:
        profiles: list[Player] = make_profiles()

        combinations: list[TeamCombination] = Matchmaking._calculate_unique_team_combinations(profiles)
        differences: list[int] = Matchmaking._calculate_rating_differences(combinations)

        assert len(differences) == len(combinations)
        for (radiant, dire), difference in zip(combinations, differences, strict=True):
            radiant_mmr: int = sum(p.adjusted_mmr for p in radiant if p.adjusted_mmr)
            dire_mmr: int = sum(p.adjusted_mmr for p in dire if p.adjusted_mmr)
            assert difference == abs(radiant_mmr - dire_mmr)


class TestDuplicateProfiles:
    def test_duplicate_ids_are_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from onehead.common import OneHeadException

        profiles: list[Player] = make_profiles()
        profiles[-1] = profiles[0]

        mm: Matchmaking = Matchmaking(database=None, lobby=None)  # type: ignore[arg-type]
        monkeypatch.setattr(mm, "_get_player_records", lambda ctx: profiles)

        with pytest.raises(OneHeadException, match="Possible duplicate player name"):
            mm._calculate_balance(ctx=None)  # type: ignore[arg-type]
