import pytest
from sqlalchemy import inspect

from app.config import get_settings
from app.db import init_db, make_engine

pytestmark = pytest.mark.integration


def test_create_all_on_postgres():
    engine = make_engine(get_settings().database_url)
    init_db(engine)
    assert {"contract", "run", "finding", "decision"} <= set(inspect(engine).get_table_names())
