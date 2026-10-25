import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from dacite import from_dict
from tinydb import Query, TinyDB
from tinydb.table import Document, Table

from onehead.common import ROOT_DIR, Metadata, OneHeadException, Player
from onehead.config import Config
from onehead.interfaces.database import PlayerDatabase


class Database(PlayerDatabase):
    def __init__(self, config: Config) -> None:
        self.db: TinyDB = TinyDB(Path(ROOT_DIR, config.tinydb.path))
        self.players: Table = self.db.table("players")
        self.metadata: Table = self.db.table("metadata")
        if self.metadata.contains(Query().name == "season") is False:
            metadata = Metadata(time.time())
            self.metadata.insert(asdict(metadata))

    def _get_document(self, id: int) -> Document | None:
        User: Query = Query()
        result: Document | None = cast(Document | None, self.players.get(User.id == id))
        return result

    def get(self, id: int) -> Player | None:
        document: Document | None = self._get_document(id)
        if document:
            return from_dict(Player, document)
        return None

    def add(self, id: int, name: str, mmr: int) -> None:
        record: Player | None = self.get(id)
        if record:
            raise OneHeadException(f"{id} is already registered.")

        record = Player(id, name, mmr)
        self.players.insert(asdict(record))

    def remove(self, id: int) -> None:
        player: Document | None = self._get_document(id)
        if player is None:
            raise OneHeadException(f"{id} does not exist in database.")

        self.players.remove(doc_ids=[player.doc_id])

    def update(self, modified: Player) -> None:
        document: Document | None = self._get_document(modified.id)
        if document is None:
            raise OneHeadException(f"{modified.id} does not exist in database.")

        self.players.update(asdict(modified), doc_ids=[document.doc_id])

    def get_all(self) -> list[Player]:
        return [from_dict(Player, dict(document)) for document in self.players.all()]

    def get_metadata(self) -> Metadata:
        q: Query = Query()
        doc: Document | None = cast(Document | None, self.metadata.get(q.name == "season"))
        if doc is None:
            raise OneHeadException("Unable to retrieve metadata from database.")

        document: dict[str, Any] = cast(dict[str, Any], doc)
        metadata: Metadata = from_dict(Metadata, document)
        return metadata

    def update_metadata(self, data: Metadata) -> None:
        q: Query = Query()
        self.metadata.upsert(asdict(data), q.name == "season")
