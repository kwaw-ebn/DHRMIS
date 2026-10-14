import os
from alembic import context
from sqlalchemy import create_engine, pool
from app.db import Base, database_url
from app import models
config=context.config
target_metadata=Base.metadata
url=database_url(os.getenv('DATABASE_URL_UNPOOLED',os.getenv('DATABASE_URL','sqlite:///./staffhub.db')))
if context.is_offline_mode():
    context.configure(url=url,target_metadata=target_metadata,literal_binds=True)
    with context.begin_transaction():context.run_migrations()
else:
    engine=create_engine(url,poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
