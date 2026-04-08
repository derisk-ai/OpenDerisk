"""Oracle connector using python-oracledb."""

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple, Type
from urllib.parse import quote, quote_plus

from sqlalchemy import MetaData, text

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.datasource.rdbms.base import RDBMSConnector, RDBMSDatasourceParameters
from derisk.util.i18n_utils import _

logger = logging.getLogger(__name__)


@auto_register_resource(
    label=_("Oracle datasource"),
    category=ResourceCategory.DATABASE,
    tags={"order": TAGS_ORDER_HIGH},
    description=_(
        "Enterprise-grade relational database with oracledb driver (python-oracledb)."
    ),
)
@dataclass
class OracleParameters(RDBMSDatasourceParameters):
    """Oracle connection parameters."""

    __type__ = "oracle"

    driver: str = field(
        default="oracle+oracledb",
        metadata={
            "help": _("Driver name for Oracle, default is oracle+oracledb."),
        },
    )

    service_name: Optional[str] = field(
        default=None,
        metadata={
            "help": _("Oracle service name (alternative to SID)."),
        },
    )

    sid: Optional[str] = field(
        default=None,
        metadata={
            "help": _("Oracle SID (System ID, alternative to service name)."),
        },
    )

    def db_url(self, ssl: bool = False, charset: Optional[str] = None) -> str:
        # Resolve effective service_name / sid.  When neither is explicitly
        # set, fall back to the inherited ``database`` field so that users
        # who simply fill in the "database" input on the UI still get a
        # working connection (treated as service_name).
        effective_service_name = self.service_name
        effective_sid = self.sid
        if not effective_service_name and not effective_sid:
            if getattr(self, "database", None):
                effective_service_name = self.database
            else:
                raise ValueError(
                    "Either service_name, sid, or database must be provided "
                    "for Oracle."
                )

        if effective_service_name:
            dsn = (
                f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={self.host})"
                f"(PORT={self.port}))"
                f"(CONNECT_DATA=(SERVICE_NAME={effective_service_name})))"
            )
        else:
            dsn = (
                f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={self.host})"
                f"(PORT={self.port}))(CONNECT_DATA=(SID={effective_sid})))"
            )

        return (
            f"{self.driver}://{quote(self.user)}:{quote_plus(self.password)}@{dsn}"
        )

    def create_connector(self) -> "OracleConnector":
        return OracleConnector.from_parameters(self)


class OracleConnector(RDBMSConnector):
    db_type: str = "oracle"
    db_dialect: str = "oracle"
    driver: str = "oracle+oracledb"

    @classmethod
    def param_class(cls) -> Type[RDBMSDatasourceParameters]:
        return OracleParameters

    @classmethod
    def from_uri_db(
        cls,
        host: str,
        port: int,
        user: str,
        pwd: str,
        sid: Optional[str] = None,
        service_name: Optional[str] = None,
        engine_args: Optional[dict] = None,
        **kwargs,
    ) -> "OracleConnector":
        if not sid and not service_name:
            raise ValueError("Must provide either sid or service_name")

        if service_name:
            dsn = (
                f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)"
                f"(HOST={host})(PORT={port}))"
                f"(CONNECT_DATA=(SERVICE_NAME={service_name})))"
            )
        else:
            dsn = (
                f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})"
                f"(PORT={port}))(CONNECT_DATA=(SID={sid})))"
            )

        bm_pwd = quote_plus(pwd)
        bm_user = quote(user)
        db_url = f"{cls.driver}://{bm_user}:{bm_pwd}@{dsn}"

        return cls.from_uri(db_url, engine_args=engine_args, **kwargs)

    # ================================================================
    # Dialect-specific overrides
    # ================================================================

    def quote_identifier(self, identifier: str) -> str:
        """Oracle uses double-quote for identifier quoting."""
        return f'"{identifier}"'

    def limit_sql(self, sql: str, limit: int, offset: int = 0) -> str:
        """Oracle 12c+ row-limiting clause."""
        if offset > 0:
            return f"{sql} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
        return f"{sql} FETCH FIRST {limit} ROWS ONLY"

    def _get_schema_for_inspection(self) -> Optional[str]:
        """Oracle: use connected user's default schema (None lets SQLAlchemy decide)."""
        return None

    def _switch_to_db(self, session, db_name: str):
        """Oracle does not support USE statement. No-op."""
        pass

    def _sync_tables_from_db(self) -> Iterable[str]:
        """Read table information from Oracle using user_tables/user_views."""
        with self.session_scope() as session:
            table_results = session.execute(
                text("SELECT table_name FROM user_tables")
            )
            tables: Set[str] = {row[0] for row in table_results}

            if self.view_support:
                view_results = session.execute(
                    text("SELECT view_name FROM user_views")
                )
                tables.update(row[0] for row in view_results)

        self._all_tables = tables
        self._metadata = MetaData()
        self._metadata.reflect(bind=self._engine)
        return self._all_tables

    def get_current_db_name(self) -> str:
        """Get current database name for Oracle."""
        with self.session_scope() as session:
            cursor = session.execute(
                text("SELECT sys_context('USERENV', 'DB_NAME') FROM dual")
            )
            return cursor.scalar()

    def table_simple_info(self):
        """Return table simple info using Oracle-specific SQL."""
        _sql = """
            SELECT table_name || '(' || LISTAGG(column_name, ',')
                   WITHIN GROUP (ORDER BY column_id) || ')' AS schema_info
            FROM user_tab_columns
            GROUP BY table_name
        """
        with self.session_scope() as session:
            cursor = session.execute(text(_sql))
            return cursor.fetchall()

    def get_show_create_table(self, table_name: str) -> str:
        """Synthesize CREATE TABLE DDL from Oracle metadata."""
        with self.session_scope() as session:
            cursor = session.execute(text(f"""
                SELECT column_name, data_type, data_length, data_precision,
                       data_scale, nullable, data_default
                FROM user_tab_columns
                WHERE table_name = '{table_name.upper()}'
                ORDER BY column_id
            """))
            rows = cursor.fetchall()

        if not rows:
            return f'-- Table "{table_name.upper()}" not found or no columns'

        lines = []
        for row in rows:
            col_name = row[0]
            data_type = row[1]
            data_length = row[2]
            data_precision = row[3]
            data_scale = row[4]
            nullable = row[5]
            data_default = row[6]

            if data_precision is not None:
                if data_scale is not None and data_scale > 0:
                    data_type = f"{data_type}({data_precision},{data_scale})"
                else:
                    data_type = f"{data_type}({data_precision})"
            elif data_length and data_type in (
                "VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR", "RAW",
            ):
                data_type = f"{data_type}({data_length})"

            parts = [f'    "{col_name}" {data_type}']
            if data_default:
                parts.append(f"DEFAULT {str(data_default).strip()}")
            if nullable == "N":
                parts.append("NOT NULL")
            lines.append(" ".join(parts))

        create_table = f'CREATE TABLE "{table_name.upper()}" (\n'
        create_table += ",\n".join(lines)
        create_table += "\n)"
        return create_table

    def get_simple_fields(self, table_name):
        """Get column fields about specified table."""
        return self.get_fields(table_name)

    def get_fields(self, table_name: str, db_name=None) -> List[Tuple]:
        with self.session_scope() as session:
            query = f"""
                SELECT col.column_name,
                       col.data_type,
                       col.data_default,
                       col.nullable,
                       comm.comments
                FROM user_tab_columns col
                LEFT JOIN user_col_comments comm
                ON col.table_name = comm.table_name
                AND col.column_name = comm.column_name
                WHERE col.table_name = '{table_name.upper()}'
            """
            result = session.execute(text(query))
            return result.fetchall()

    def _write(self, write_sql: str):
        """Oracle write: no db-switch needed after commit."""
        logger.info(f"Write[{write_sql}]")
        with self.session_scope(commit=False) as session:
            result = session.execute(text(write_sql))
            session.commit()
            logger.info(f"SQL[{write_sql}], result:{result.rowcount}")
            return result.rowcount

    def query_table_schema(self, table_name: str):
        """Query table schema with Oracle row-limiting syntax."""
        sql = f'SELECT * FROM "{table_name.upper()}" FETCH FIRST 1 ROWS ONLY'
        return self._query(sql)

    def get_charset(self) -> str:
        with self.session_scope() as session:
            cursor = session.execute(
                text(
                    "SELECT VALUE FROM NLS_DATABASE_PARAMETERS "
                    "WHERE PARAMETER = 'NLS_CHARACTERSET'"
                )
            )
            return cursor.fetchone()[0]

    def get_grants(self):
        with self.session_scope() as session:
            cursor = session.execute(text("SELECT privilege FROM user_sys_privs"))
            return cursor.fetchall()

    def get_users(self) -> List[Tuple[str, None]]:
        with self.session_scope() as session:
            cursor = session.execute(text("SELECT username FROM all_users"))
            return [(row[0], None) for row in cursor.fetchall()]

    def get_database_names(self) -> List[str]:
        with self.session_scope() as session:
            try:
                is_cdb = session.execute(
                    text("SELECT CDB FROM V$DATABASE")
                ).fetchone()[0]
            except Exception:
                # Non-DBA user may lack access to V$DATABASE
                return [self.get_current_db_name()]

            if is_cdb == "YES":
                pdbs = session.execute(
                    text("SELECT NAME FROM V$PDBS WHERE OPEN_MODE = 'READ WRITE'")
                ).fetchall()
                return [name[0] for name in pdbs]
            else:
                return [
                    session.execute(
                        text(
                            "SELECT sys_context('USERENV', 'CON_NAME') FROM dual"
                        )
                    ).fetchone()[0]
                ]

    def get_table_comments(self, db_name: str) -> List[Tuple[str, str]]:
        with self.session_scope() as session:
            result = session.execute(
                text("SELECT table_name, comments FROM user_tab_comments")
            )
            return [(row[0], row[1]) for row in result.fetchall()]

    def get_table_comment(self, table_name: str) -> Dict:
        with self.session_scope() as session:
            cursor = session.execute(
                text(
                    f"SELECT comments FROM user_tab_comments "
                    f"WHERE table_name = '{table_name.upper()}'"
                )
            )
            row = cursor.fetchone()
            return {"text": row[0] if row else ""}

    def get_column_comments(
        self, db_name: str, table_name: str
    ) -> List[Tuple[str, str]]:
        with self.session_scope() as session:
            cursor = session.execute(
                text(f"""
                    SELECT column_name, comments
                    FROM user_col_comments
                    WHERE table_name = '{table_name.upper()}'
                """)
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_collation(self) -> str:
        with self.session_scope() as session:
            cursor = session.execute(
                text(
                    "SELECT value FROM NLS_DATABASE_PARAMETERS "
                    "WHERE parameter = 'NLS_SORT'"
                )
            )
            return cursor.fetchone()[0]
