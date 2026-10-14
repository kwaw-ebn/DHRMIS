import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def database_url(value):
    if value.startswith('postgres://'):
        value = value.replace('postgres://', 'postgresql://', 1)
    if value.startswith('postgresql://'):
        value = value.replace('postgresql://', 'postgresql+psycopg://', 1)
    return value

url = database_url(os.getenv('DATABASE_URL', 'sqlite:///./staffhub.db'))
engine = create_engine(url, pool_pre_ping=True, **({'connect_args': {'check_same_thread': False}} if url.startswith('sqlite') else {'pool_size': 5, 'max_overflow': 5}))
if url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as session:
        yield session
