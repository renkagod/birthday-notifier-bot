import pytest
from bot import database


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "birthdays.db"
    monkeypatch.setenv(database.DB_PATH_ENV, str(db_file))
    database.init_db()
    yield db_file
