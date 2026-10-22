import pytest
from sqlalchemy import create_engine, inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.database import Base
from app import models
from app.migrate import migrate, check_revision


def test_fresh_schema_and_repeat_startup():
    engine = create_engine('sqlite://')
    migrate(engine)
    migrate(engine)
    with engine.connect() as connection:
        check_revision(connection)
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_adopt_legacy_schema_without_changing_data():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(models.Story.__table__.insert().values(id=42, category='Test', risk='demo'))
    migrate(engine)
    with engine.connect() as connection:
        check_revision(connection)
        assert connection.scalar(text('SELECT id FROM stories')) == 42


def test_refuse_partial_legacy_schema():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE stories (id INTEGER PRIMARY KEY)'))
    with pytest.raises(RuntimeError, match='differs'):
        migrate(engine)
    assert inspect(engine).get_table_names() == ['stories']


def test_readiness_refuses_unknown_revision():
    engine = create_engine('sqlite://')
    migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='unknown_revision'"))
        with pytest.raises(RuntimeError, match='required'):
            check_revision(connection)
