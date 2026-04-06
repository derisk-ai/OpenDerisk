"""SQLAlchemy dialect for StarRocks."""

from sqlalchemy.dialects import registry

registry.register(
    "starrocks",
    "derisk_ext.datasource.rdbms.dialect.starrocks.sqlalchemy.dialect",
    "StarRocksDialect",
)
