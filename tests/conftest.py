"""Shared test settings: the JWT secret and the account database of one test."""
import os

import pytest

JWT_SECRET = 'rahasia-jwt-untuk-uji-minimal-32-karakter'


@pytest.fixture
def auth_url(tmp_path):
    """Account database URL for one test, in an EMPTY state.

    Default: a new SQLite file. With S4_TEST_AUTH_URL=postgresql+psycopg://… the same tests run against a real
    PostgreSQL (its tables are dropped and recreated for each test).
    """
    url = os.environ.get('S4_TEST_AUTH_URL')
    if not url: return 'sqlite:///' + str(tmp_path / 'auth.db')
    from sqlalchemy import create_engine
    from monishield.infrastructure import auth
    e = create_engine(url); auth.Base.metadata.drop_all(e); e.dispose()
    return url
