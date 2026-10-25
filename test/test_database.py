import shutil
from pathlib import Path

import pytest

from onehead.common import Metadata
from onehead.config import Config, DiscordChannelConfig, DiscordConfig, TinyDBConfig
from onehead.database import Database

EXISTING_DB: Path = Path(__file__).parent / "test_db.json"


def make_database(path: Path) -> Database:
    """
    Build a Database backed by the given file, creating it if it does not exist.

    :param path: Where the TinyDB json file lives.
    :return: The database.
    """
    config: Config = Config(
        tinydb=TinyDBConfig(str(path)),
        discord=DiscordConfig("token", DiscordChannelConfig("lobby", "match")),
    )

    return Database(config)


class TestMetadata:
    """
    The metadata table is queried by `name`, but the Metadata dataclass stopped carrying
    one when it replaced the TypedDict. A fresh database therefore inserted a row the
    queries could not find: `get_metadata` raised, and `update_metadata` inserted a
    duplicate instead of updating. Existing databases were unaffected only because their
    rows still held the legacy key.
    """

    def test_metadata_is_queryable_on_a_fresh_database(self, tmp_path: Path) -> None:
        database: Database = make_database(tmp_path / "db.json")

        metadata: Metadata = database.get_metadata()

        assert metadata.name == "season"
        assert metadata.season == 1
        assert metadata.game_id == 1

    def test_update_replaces_the_row_rather_than_adding_one(self, tmp_path: Path) -> None:
        database: Database = make_database(tmp_path / "db.json")

        metadata: Metadata = database.get_metadata()
        metadata.game_id += 1
        database.update_metadata(metadata)

        assert len(database.metadata.all()) == 1
        assert database.get_metadata().game_id == 2

    def test_repeated_updates_do_not_accumulate_rows(self, tmp_path: Path) -> None:
        database: Database = make_database(tmp_path / "db.json")

        for _ in range(5):
            metadata: Metadata = database.get_metadata()
            metadata.game_id += 1
            database.update_metadata(metadata)

        assert len(database.metadata.all()) == 1
        assert database.get_metadata().game_id == 6

    def test_an_existing_database_still_loads(self, tmp_path: Path) -> None:
        path: Path = tmp_path / "db.json"
        shutil.copy(EXISTING_DB, path)

        database: Database = make_database(path)
        metadata: Metadata = database.get_metadata()

        assert metadata.name == "season"
        assert metadata.season == 12
        assert len(database.metadata.all()) == 1

    def test_an_existing_database_updates_in_place(self, tmp_path: Path) -> None:
        path: Path = tmp_path / "db.json"
        shutil.copy(EXISTING_DB, path)

        database: Database = make_database(path)
        metadata: Metadata = database.get_metadata()
        starting_game_id: int = metadata.game_id

        metadata.game_id += 1
        database.update_metadata(metadata)

        assert len(database.metadata.all()) == 1
        assert database.get_metadata().game_id == starting_game_id + 1


class TestPlayers:
    # Always work on a copy - Database.__init__ writes to the file if the metadata row is
    # missing, and the fixture is checked in.
    def test_get_all_returns_every_player(self, tmp_path: Path) -> None:
        path: Path = tmp_path / "db.json"
        shutil.copy(EXISTING_DB, path)

        players = make_database(path).get_all()

        assert len(players) == 24
        assert all(player.id for player in players)

    def test_get_returns_none_for_an_unknown_player(self, tmp_path: Path) -> None:
        path: Path = tmp_path / "db.json"
        shutil.copy(EXISTING_DB, path)

        assert make_database(path).get(1) is None


@pytest.mark.parametrize("season", [1, 12])
def test_metadata_round_trips_through_the_database(tmp_path: Path, season: int) -> None:
    database: Database = make_database(tmp_path / "db.json")

    metadata: Metadata = database.get_metadata()
    metadata.season = season
    metadata.game_id = 7
    database.update_metadata(metadata)

    reloaded: Metadata = make_database(tmp_path / "db.json").get_metadata()

    assert reloaded.season == season
    assert reloaded.game_id == 7
