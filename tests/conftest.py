"""Location of the log folder and the old-system module (build_dashboard.py) for comparison tests."""
import glob, importlib, os, sys

import pytest

V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(V2)  # log folder + build_dashboard.py


@pytest.fixture(scope='session')
def log_root(): return ROOT


@pytest.fixture(scope='session')
def old():
    """Old module; tests are skipped (not failed) when it is missing, e.g. inside the image."""
    if not os.path.exists(os.path.join(ROOT, 'build_dashboard.py')): pytest.skip('build_dashboard.py tidak ada')
    sys.path.insert(0, ROOT)
    try: return importlib.import_module('build_dashboard')
    finally: sys.path.remove(ROOT)


def log_files(service, folders=('2026-09-29', '2026-10-06')):
    return sorted(f for d in folders for f in glob.glob(os.path.join(ROOT, d, '**', service, '*.log'), recursive=True))


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
