"""S4 smoke test: checkpointer, SQLModel create_all, Qdrant reachable."""

import sys

from langgraph.checkpoint.postgres import PostgresSaver
from qdrant_client import QdrantClient
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import get_settings


class S4Probe(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    note: str


def check_checkpointer(settings) -> None:
    with PostgresSaver.from_conn_string(settings.checkpoint_db_url) as saver:
        saver.setup()


def check_sqlmodel(settings) -> None:
    engine = create_engine(settings.database_url)
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(S4Probe(id=1, note="hello"))
            session.commit()
            row = session.exec(select(S4Probe)).one()
            assert row.note == "hello"
    finally:
        SQLModel.metadata.drop_all(engine)


def check_qdrant(settings) -> None:
    QdrantClient(url=settings.qdrant_url).get_collections()


def main() -> int:
    settings = get_settings()
    failed = False
    for name, check in (
        ("checkpointer", check_checkpointer),
        ("sqlmodel", check_sqlmodel),
        ("qdrant", check_qdrant),
    ):
        try:
            check(settings)
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure
            failed = True
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
