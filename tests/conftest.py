import pytest


@pytest.fixture()
def state_db_path(tmp_path):
    return str(tmp_path / "state_test.db")
