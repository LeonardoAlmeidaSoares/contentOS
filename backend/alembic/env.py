from alembic import context
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.db import Base
from app.lab import models as _lab  # noqa: F401
from app.providers import models as _prov  # noqa: F401
from app.runs import models  # noqa: F401

target_metadata = Base.metadata

with create_engine(settings.database_url).connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
