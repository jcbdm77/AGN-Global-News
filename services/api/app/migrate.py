"""Transactional migrations with strict adoption of the existing v0.2 schema."""
from pathlib import Path
from sqlalchemy import inspect, text
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from alembic.script import ScriptDirectory

BASELINE = '0001_initial'

def configuration(connection):
    cfg = Config()
    cfg.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
    cfg.attributes['connection'] = connection
    return cfg

def migrate(engine):
    with engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(731947120)"))
        cfg = configuration(connection)
        tables = set(inspect(connection).get_table_names())
        if 'alembic_version' not in tables and tables:
            # Build the frozen baseline separately; never infer a version from
            # current ORM models or stamp an unknown/partial legacy database.
            import importlib.util
            baseline_path = Path(__file__).parent / 'migrations' / 'versions' / '0001_initial.py'
            spec = importlib.util.spec_from_file_location('agn_baseline', baseline_path)
            baseline = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(baseline)
            diff = compare_metadata(MigrationContext.configure(connection), baseline.baseline_metadata())
            if diff:
                raise RuntimeError('Existing schema differs from the AGN baseline; migration stopped without changing data')
            command.stamp(cfg, BASELINE)
        command.upgrade(cfg, 'head')

def check_revision(connection):
    current = set(MigrationContext.configure(connection).get_current_heads())
    expected = set(ScriptDirectory.from_config(configuration(connection)).get_heads())
    if current != expected:
        raise RuntimeError('Database migration is required')
