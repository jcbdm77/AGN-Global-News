from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

from .auth import secret
DATABASE_URL = secret('DATABASE_URL') or 'sqlite:///./agn.db'
if os.getenv('APP_ENV') == 'staging' and not DATABASE_URL.startswith('postgresql'):
    raise RuntimeError('Staging requires PostgreSQL')
connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass
