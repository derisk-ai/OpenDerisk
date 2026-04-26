import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from functools import wraps

from derisk._private.config import Config
from derisk.component import SystemApp
from derisk.configs.model_config import resolve_root_path
from derisk.core.interface.parameter import BaseServerParameters
from derisk.datasource.parameter import BaseDatasourceParameters
from derisk.datasource.rdbms.base import RDBMSConnector, RDBMSDatasourceParameters
from derisk_app.config import ApplicationConfig, ServiceConfig

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)

logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    print("in order to avoid chroma db atexit problem")
    os._exit(0)


def server_init(param: ApplicationConfig, system_app: SystemApp):
    # logger.info(f"args: {args}")
    # init config
    cfg = Config()
    cfg.SYSTEM_APP = system_app
    # Initialize db storage first
    _initialize_db_storage(param.service, system_app)

    # load_native_plugins(cfg)
    signal.signal(signal.SIGINT, signal_handler)


def _create_model_start_listener(system_app: SystemApp):
    def startup_event(wh):
        print("begin run _add_app_startup_event")

    return startup_event


def _initialize_db_storage(param: ServiceConfig, system_app: SystemApp):
    """Initialize the db storage.

    Now just support sqlite and mysql. If db type is sqlite, the db path is
    `pilot/meta_data/{db_name}.db`.
    """
    from derisk_ext.datasource.rdbms.conn_sqlite import SQLiteConnectorParameters

    db_config: BaseDatasourceParameters = param.web.database
    if isinstance(db_config, SQLiteConnectorParameters):
        db_config.path = resolve_root_path(db_config.path)
        db_dir = os.path.dirname(db_config.path)
        os.makedirs(db_dir, exist_ok=True)
        # Parse the db name from the db path
        db_name = os.path.basename(db_config.path).split(".")[0]
    elif isinstance(db_config, RDBMSDatasourceParameters):
        db_name = db_config.database
    else:
        raise ValueError(
            "DERISK only support SQLite, MySQL and OceanBase database as metadata "
            "storage database"
        )

    disable_alembic_upgrade = param.web.disable_alembic_upgrade
    db_ssl_verify = param.web.db_ssl_verify
    # connector = db_config.create_connector()
    # if not isinstance(connector, RDBMSConnector):
    #     raise ValueError("Only support RDBMSConnector")
    db_url = db_config.db_url(ssl=db_ssl_verify, charset="utf8mb4")
    # db_type = connector.db_type
    db_engine_args: Optional[Dict[str, Any]] = db_config.engine_args()

    _initialize_db(
        db_url,
        # db_type,
        db_name,
        db_engine_args,
        try_to_create_db=not disable_alembic_upgrade,
        system_app=system_app,
    )
    _migrate_mysql_chat_tables_utf8mb4(db_url)


def _migrate_mysql_chat_tables_utf8mb4(db_url: str) -> None:
    """Ensure chat history tables use utf8mb4 (fixes DataError 1366 on emoji).

    New installs get correct DDL from assets/schema/derisk.sql. Legacy MySQL
    databases may still have utf8/utf8mb3 tables; migrate them automatically.
    """
    if "mysql" not in (db_url or "").lower():
        return
    try:
        from sqlalchemy import text
        from derisk.storage.metadata.db_manager import db

        if not db.is_initialized:
            return

        engine = db.engine
        with engine.connect() as conn:
            tables = conn.execute(
                text(
                    """
                    SELECT TABLE_NAME, TABLE_COLLATION
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME IN ('chat_history', 'chat_history_message')
                    """
                )
            ).fetchall()

            if not tables:
                return

            def _collation_ok(collation: object) -> bool:
                return str(collation or "").lower().startswith("utf8mb4")

            bad_tables = [name for name, coll in tables if not _collation_ok(coll)]

            msg_detail_charset = None
            row = conn.execute(
                text(
                    """
                    SELECT CHARACTER_SET_NAME
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'chat_history_message'
                      AND COLUMN_NAME = 'message_detail'
                    """
                )
            ).fetchone()
            if row:
                msg_detail_charset = (row[0] or "").lower()

            bad_column = msg_detail_charset and msg_detail_charset != "utf8mb4"

            if not bad_tables and not bad_column:
                return

            schema = conn.execute(text("SELECT DATABASE()")).scalar()
            if not schema:
                return

        # DDL auto-commits; use begin() for a clean transaction boundary per statement.
        migrated = False
        with engine.begin() as conn:
            db_coll = conn.execute(
                text(
                    """
                    SELECT DEFAULT_COLLATION_NAME
                    FROM information_schema.SCHEMATA
                    WHERE SCHEMA_NAME = :schema
                    """
                ),
                {"schema": schema},
            ).scalar()
            if db_coll and not str(db_coll).lower().startswith("utf8mb4"):
                conn.execute(
                    text(
                        "ALTER DATABASE `{schema}` CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci".format(schema=schema)
                    )
                )
                migrated = True

            if "chat_history" in bad_tables:
                conn.execute(
                    text(
                        "ALTER TABLE `chat_history` CONVERT TO CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci"
                    )
                )
                migrated = True
            if "chat_history_message" in bad_tables:
                conn.execute(
                    text(
                        "ALTER TABLE `chat_history_message` "
                        "CONVERT TO CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci"
                    )
                )
                migrated = True
            elif bad_column:
                conn.execute(
                    text(
                        "ALTER TABLE `chat_history_message` "
                        "MODIFY COLUMN `message_detail` LONGTEXT "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL "
                        "COMMENT 'Message details, json format'"
                    )
                )
                migrated = True

        if migrated:
            logger.info(
                "MySQL chat_history / chat_history_message migrated to utf8mb4."
            )
    except Exception as e:
        logger.error("MySQL utf8mb4 migration for chat tables failed: %s", e)


def _add_missing_columns(db):
    """Add missing columns to existing tables (ALTER TABLE ADD COLUMN).

    SQLAlchemy's create_all() only creates new tables; it won't add columns to
    existing ones. This function inspects the current schema and adds any column
    that is defined in a mapped model but absent from the actual table.
    Works for both SQLite and MySQL.
    """
    from sqlalchemy import inspect as sa_inspect, text

    engine = db.engine
    dialect_name = engine.dialect.name
    inspector = sa_inspect(engine)
    existing_tables = inspector.get_table_names()

    existing_cols_map = {}
    for table in db.Model.metadata.sorted_tables:
        if table.name in existing_tables:
            existing_cols_map[table.name] = {
                c["name"] for c in inspector.get_columns(table.name)
            }

    with engine.connect() as conn:
        for table in db.Model.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = existing_cols_map[table.name]
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL"
                default_clause = ""
                if col.default is not None and col.default.is_scalar:
                    default_clause = f" DEFAULT '{col.default.arg}'"
                comment_clause = ""
                if dialect_name == "mysql" and col.comment:
                    escaped = col.comment.replace("'", "\\'")
                    comment_clause = f" COMMENT '{escaped}'"
                try:
                    stmt = text(
                        f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type} {nullable}{default_clause}{comment_clause}"
                    )
                    conn.execute(stmt)
                    conn.commit()
                    logger.info(
                        f"[schema migration] Added column '{col.name}' to table '{table.name}'"
                    )
                except Exception as e:
                    logger.warning(
                        f"[schema migration] Failed to add column '{col.name}' to '{table.name}': {e}"
                    )


def _migration_db_storage(
    db_params: BaseDatasourceParameters, disable_alembic_upgrade: bool
):
    """Migration the db storage."""
    # Import all models to make sure they are registered with SQLAlchemy.
    from derisk.configs.model_config import PILOT_PATH
    from derisk_app.initialization.db_model_initialization import _MODELS  # noqa: F401
    from derisk_ext.datasource.rdbms.conn_sqlite import SQLiteConnectorParameters

    default_meta_data_path = os.path.join(PILOT_PATH, "meta_data")
    if not disable_alembic_upgrade:
        from derisk.storage.metadata.db_manager import db
        from derisk.util._db_migration_utils import _ddl_init_and_upgrade

        # Try to create all tables, when the dbtype is sqlite, it will auto create and
        # upgrade system schema,
        # Otherwise, you need to execute initialization scripts to create schemas.
        if (
            isinstance(db_params, SQLiteConnectorParameters)
            or db_params.get_type_value() == "sqlite"
        ):
            try:
                db.create_all()
            except Exception as e:
                logger.warning(
                    f"Create all tables stored in this metadata error: {str(e)}"
                )

            _add_missing_columns(db)

            db.engine.dispose()

            _ddl_init_and_upgrade(default_meta_data_path, disable_alembic_upgrade)
        else:
            # MySQL: create new tables + auto-add missing columns
            try:
                db.create_all()
            except Exception as e:
                logger.warning(
                    f"Create all tables stored in this metadata error: {str(e)}"
                )

            _add_missing_columns(db)

            db.engine.dispose()

            _ddl_init_and_upgrade(default_meta_data_path, disable_alembic_upgrade)


def _initialize_db(
    db_url: str,
    # db_type: str,
    db_name: str,
    db_engine_args: Optional[Dict[str, Any]] = None,
    try_to_create_db: Optional[bool] = False,
    system_app: Optional[SystemApp] = None,
) -> str:
    """Initialize the database

    Now just support sqlite and MySQL. If db type is sqlite, the db path is
    `pilot/meta_data/{db_name}.db`.
    """

    from derisk.configs.model_config import PILOT_PATH
    from derisk.storage.metadata.db_manager import initialize_db
    from derisk_ext.datasource.rdbms.dialect.oceanbase.ob_dialect import (  # noqa: F401
        OBDialect,
    )

    default_meta_data_path = os.path.join(PILOT_PATH, "meta_data")
    # if db_type == "mysql":
    #     # Try to create database, if failed, will raise exception
    #     _create_mysql_database(db_name, db_url, try_to_create_db)
    # elif db_type == "oceanbase":
    #     _create_mysql_database(db_name, db_url, try_to_create_db)

    if not db_engine_args:
        db_engine_args = {}

    is_sqlite = "sqlite" in (db_url or "").lower()
    if is_sqlite:
        from sqlalchemy.pool import NullPool

        # 使用 NullPool 避免连接池竞争，每个操作独立连接
        db_engine_args.setdefault("poolclass", NullPool)
        db_engine_args.setdefault("pool_pre_ping", True)
        db_engine_args.setdefault("connect_args", {})
        db_engine_args["connect_args"].setdefault("check_same_thread", False)
        db_engine_args["connect_args"].setdefault("timeout", 60)
    else:
        db_engine_args.setdefault("pool_size", 100)
        db_engine_args.setdefault("max_overflow", 100)
        db_engine_args.setdefault("pool_timeout", 30)
        db_engine_args.setdefault("pool_recycle", 3600)
        db_engine_args.setdefault("pool_pre_ping", True)

    db = initialize_db(db_url, db_name, db_engine_args)

    if is_sqlite:
        _enable_sqlite_wal_mode(db)

    if system_app:
        from derisk.storage.metadata import UnifiedDBManagerFactory

        system_app.register(UnifiedDBManagerFactory, db)
    return default_meta_data_path


def _enable_sqlite_wal_mode(db) -> None:
    """Enable WAL mode for SQLite to improve concurrent performance.

    WAL mode allows concurrent reads and writes, reducing lock contention.
    """
    try:
        from sqlalchemy import text

        engine = db.engine
        with engine.connect() as conn:
            # 启用 WAL 模式 - 支持读写并发
            conn.execute(text("PRAGMA journal_mode=WAL"))
            # 同步模式设为 NORMAL，平衡性能和安全性
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            # 增加缓存大小到 64MB
            conn.execute(text("PRAGMA cache_size=-64000"))
            # 设置忙碌超时为 30 秒（SQLite 级别）
            conn.execute(text("PRAGMA busy_timeout=30000"))
            # 设置 WAL 自动检查点，防止 WAL 文件过大
            conn.execute(text("PRAGMA wal_autocheckpoint=1000"))
            conn.commit()
        logger.info("SQLite WAL mode enabled successfully with optimized settings")
    except Exception as e:
        logger.warning(f"Failed to enable SQLite WAL mode: {e}")


def _create_mysql_database(db_name: str, db_url: str, try_to_create_db: bool = False):
    """Create mysql database if not exists

    Args:
        db_name (str): The database name
        db_url (str): The database url, include host, port, user, password and database
            name
        try_to_create_db (bool, optional): Whether to try to create database. Defaults
            to False.

    Raises:
        Exception: Raise exception if database operation failed
    """
    from sqlalchemy import DDL, create_engine
    from sqlalchemy.exc import OperationalError, SQLAlchemyError

    if not try_to_create_db:
        logger.info(f"Skipping creation of database {db_name}")
        return
    engine = create_engine(db_url)

    try:
        # Try to connect to the database
        with engine.connect() as conn:
            logger.info(f"Database {db_name} already exists")
            return
    except OperationalError as oe:
        # If the error indicates that the database does not exist, try to create it
        if "Unknown database" in str(oe):
            try:
                # Create the database
                no_db_name_url = db_url.rsplit("/", 1)[0]
                engine_no_db = create_engine(no_db_name_url)
                with engine_no_db.connect() as conn:
                    conn.execute(
                        DDL(
                            f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE "
                            f"utf8mb4_unicode_ci"
                        )
                    )
                    logger.info(f"Database {db_name} successfully created")
            except SQLAlchemyError as e:
                logger.error(f"Failed to create database {db_name}: {e}")
                raise
        else:
            logger.error(f"Error connecting to database {db_name}: {oe}")
            raise


@dataclass
class WebServerParameters(BaseServerParameters):
    host: Optional[str] = field(
        default="0.0.0.0", metadata={"help": "Webserver deploy host"}
    )
    port: Optional[int] = field(
        default=None, metadata={"help": "Webserver deploy port"}
    )
    daemon: Optional[bool] = field(
        default=False, metadata={"help": "Run Webserver in background"}
    )
    controller_addr: Optional[str] = field(
        default=None,
        metadata={
            "help": "The Model controller address to connect. If None, read model "
            "controller address from environment key `MODEL_SERVER`."
        },
    )
    model_name: str = field(
        default=None,
        metadata={
            "help": "The default model name to use. If None, read model name from "
            "environment key `LLM_MODEL`.",
            "tags": "fixed",
        },
    )
    share: Optional[bool] = field(
        default=False,
        metadata={
            "help": "Whether to create a publicly shareable link for the interface. "
            "Creates an SSH tunnel to make your UI accessible from anywhere. "
        },
    )
    remote_embedding: Optional[bool] = field(
        default=False,
        metadata={
            "help": "Whether to enable remote embedding models. If it is True, you need"
            " to start a embedding model through `derisk start worker --worker_type "
            "text2vec --model_name xxx --model_path xxx`"
        },
    )
    remote_rerank: Optional[bool] = field(
        default=False,
        metadata={
            "help": "Whether to enable remote rerank models. If it is True, you need"
            " to start a rerank model through `derisk start worker --worker_type "
            "text2vec --rerank --model_name xxx --model_path xxx`"
        },
    )

    light: Optional[bool] = field(default=False, metadata={"help": "enable light mode"})
    log_file: Optional[str] = field(
        default="derisk_webserver.log",
        metadata={
            "help": "The filename to store log",
        },
    )
    tracer_file: Optional[str] = field(
        default="derisk_webserver_tracer.jsonl",
        metadata={
            "help": "The filename to store tracer span records",
        },
    )
    tracer_storage_cls: Optional[str] = field(
        default=None,
        metadata={
            "help": "The storage class to storage tracer span records",
        },
    )
    disable_alembic_upgrade: Optional[bool] = field(
        default=False,
        metadata={
            "help": "Whether to disable alembic to initialize and upgrade database "
            "metadata",
        },
    )
    awel_dirs: Optional[str] = field(
        default=None,
        metadata={
            "help": "The directories to search awel files, split by `,`",
        },
    )
    default_thread_pool_size: Optional[int] = field(
        default=32,
        metadata={
            "help": "The default thread pool size, If None, "
            "use default config of python thread pool. "
            "Recommended: 32 for SQLite, 64+ for MySQL/PostgreSQL",
        },
    )
