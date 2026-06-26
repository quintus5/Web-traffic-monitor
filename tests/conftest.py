"""
Configure an in-memory SQLite database for all tests.
Must be loaded before any api.* imports so the engine is patched first.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # share one connection so :memory: db persists across sessions
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch before any downstream import resolves these names
import api.database as _db
_db.engine = test_engine
_db.SessionLocal = TestSessionLocal

# Disable dashboard auth for the API tests (auth is covered by its own test)
from config.settings import settings as _settings
_settings.AUTH_ENABLED = False

# Now import Base and models to register ORM mappings
from api.database import Base  # noqa
from api import models  # noqa
