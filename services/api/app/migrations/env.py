from alembic import context
from app.database import Base
from app import models
connection = context.config.attributes['connection']
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
