"""Oracle connector with automatic version detection and mode switching.

This connector automatically detects Oracle database version and chooses the
appropriate connection mode:
- Thin mode: For Oracle 12c and later (no Instant Client required)
- Thick mode: For older versions like Oracle 11g (requires Instant Client)
"""

import logging
import os
import platform
import re
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

# Global state for thick mode
_thick_mode_initialized = False
_thick_mode_failed = False

# Oracle versions that require thick mode (11g and earlier)
THIN_MODE_MIN_VERSION = (12, 1)

# Common Oracle Instant Client installation paths
DEFAULT_INSTANT_CLIENT_PATHS = {
    "Darwin": [
        "/usr/local/lib/instantclient",
        "/opt/oracle/instantclient",
        "~/lib/instantclient",
    ],
    "Linux": [
        "/usr/lib/oracle/instantclient",
        "/opt/oracle/instantclient",
        "/usr/local/lib/oracle/instantclient",
    ],
    "Windows": [
        "C:\\Oracle\\instantclient",
        "C:\\Program Files\\Oracle\\instantclient",
    ],
}


def _find_instant_client_paths() -> list:
    """Find potential Oracle Instant Client paths."""
    paths = []

    # 1. Environment variables
    env_path = os.environ.get("ORACLE_INSTANT_CLIENT_HOME")
    if env_path and os.path.isdir(env_path):
        paths.append(env_path)

    oracle_home = os.environ.get("ORACLE_HOME")
    if oracle_home and os.path.isdir(oracle_home):
        paths.append(oracle_home)

    # 2. Platform defaults
    system = platform.system()
    for p in DEFAULT_INSTANT_CLIENT_PATHS.get(system, []):
        expanded = os.path.expanduser(p)
        if os.path.isdir(expanded):
            paths.append(expanded)

    # 3. Library path
    lib_path = os.environ.get("DYLD_LIBRARY_PATH" if system == "Darwin" else "LD_LIBRARY_PATH")
    if lib_path:
        for p in lib_path.split(":"):
            if p and os.path.isdir(p) and "oracle" in p.lower():
                paths.append(p)

    return paths


def _init_thick_mode(lib_dir: Optional[str] = None) -> bool:
    """Initialize Oracle thick mode."""
    global _thick_mode_initialized, _thick_mode_failed

    if _thick_mode_initialized:
        return True
    if _thick_mode_failed:
        return False

    try:
        import oracledb

        # Use provided lib_dir
        if lib_dir and os.path.isdir(lib_dir):
            oracledb.init_oracle_client(lib_dir=lib_dir)
            logger.info(f"Oracle thick mode initialized: {lib_dir}")
            _thick_mode_initialized = True
            return True

        # Auto-find
        for path in _find_instant_client_paths():
            try:
                oracledb.init_oracle_client(lib_dir=path)
                logger.info(f"Oracle thick mode auto-detected: {path}")
                _thick_mode_initialized = True
                return True
            except Exception:
                continue

        # Try system default
        try:
            oracledb.init_oracle_client()
            logger.info("Oracle thick mode: system default")
            _thick_mode_initialized = True
            return True
        except Exception:
            pass

        logger.warning("Could not init thick mode. Install Oracle Instant Client.")
        _thick_mode_failed = True
        return False

    except ImportError:
        logger.warning("oracledb not installed. Run: pip install oracledb")
        _thick_mode_failed = True
        return False


def _parse_version(version_string: str) -> tuple:
    """Parse Oracle version."""
    if not version_string:
        return (0, 0)
    match = re.match(r"(\d+)\.(\d+)", version_string)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def _test_connection(host, port, user, pwd, service, use_thick=False, lib_dir=None) -> tuple:
    """Test connection and get version."""
    try:
        import oracledb

        if use_thick and not _init_thick_mode(lib_dir):
            return (False, "", "thick_init_failed")

        params = oracledb.ConnectParams(host=host, port=port, user=user, password=pwd, service_name=service)
        with oracledb.connect(params=params) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION FROM PRODUCT_COMPONENT_VERSION WHERE PRODUCT LIKE 'Oracle%'")
                row = cur.fetchone()
                return (True, row[0] if row else "", None)
    except oracledb.OperationalError as e:
        msg = str(e)
        if "DPY-3010" in msg or "not supported" in msg.lower():
            return (False, "", "version_not_supported")
        return (False, "", msg)
    except Exception as e:
        return (False, "", str(e))


@auto_register_resource(
    label=_("Oracle datasource"),
    category=ResourceCategory.DATABASE,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("Enterprise database with auto version detection (thin/thick mode)."),
)
@dataclass
class OracleParameters(RDBMSDatasourceParameters):
    """Oracle connection parameters."""

    __type__ = "oracle"

    driver: str = field(default="oracle+oracledb", metadata={"help": _("Driver, default oracle+oracledb.")})
    service_name: Optional[str] = field(default=None, metadata={"help": _("Service name.")})
    sid: Optional[str] = field(default=None, metadata={"help": _("SID.")})
    oracle_client_lib: Optional[str] = field(default=None, metadata={"help": _("Instant Client path (for Oracle 11g).")})
    force_thick_mode: bool = field(default=False, metadata={"help": _("Force thick mode.")})

    def db_url(self, ssl: bool = False, charset: Optional[str] = None) -> str:
        svc = self.service_name or self.sid
        if not svc and getattr(self, "database", None):
            svc = self.database
        if not svc:
            raise ValueError("service_name, sid, or database required")

        dsn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={self.host})(PORT={self.port}))(CONNECT_DATA=(SERVICE_NAME={svc})))" if self.service_name or not self.sid else f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={self.host})(PORT={self.port}))(CONNECT_DATA=(SID={self.sid})))"
        return f"{self.driver}://{quote(self.user)}:{quote_plus(self.password)}@{dsn}"

    def create_connector(self) -> "OracleConnector":
        return OracleConnector.from_parameters_auto(self)


class OracleConnector(RDBMSConnector):
    """Oracle connector with auto version detection."""

    db_type = "oracle"
    db_dialect = "oracle"
    driver = "oracle+oracledb"
    _oracle_version = None
    _using_thick_mode = False

    @classmethod
    def param_class(cls) -> Type[OracleParameters]:
        return OracleParameters

    @classmethod
    def from_uri_db(cls, host, port, user, pwd, sid=None, service_name=None, engine_args=None, oracle_client_lib=None, force_thick_mode=False, **kwargs) -> "OracleConnector":
        if not sid and not service_name:
            raise ValueError("sid or service_name required")

        if force_thick_mode and not _init_thick_mode(oracle_client_lib):
            raise ValueError("Thick mode init failed. Install Instant Client.")
        cls._using_thick_mode = force_thick_mode

        svc = service_name or sid
        dsn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SERVICE_NAME={svc})))" if service_name else f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SID={sid})))"
        url = f"{cls.driver}://{quote(user)}:{quote_plus(pwd)}@{dsn}"
        return cls.from_uri(url, engine_args=engine_args, **kwargs)

    @classmethod
    def from_parameters_auto(cls, params: OracleParameters) -> "OracleConnector":
        """Auto-detect mode."""
        svc = params.service_name or params.sid or params.database
        if not svc:
            raise ValueError("service_name/sid/database required")

        if params.force_thick_mode:
            if not _init_thick_mode(params.oracle_client_lib):
                raise ValueError("Thick mode failed. Install Instant Client.")
            cls._using_thick_mode = True
            return cls.from_uri_db(params.host, params.port, params.user, params.password, params.sid, params.service_name, params.engine_args(), force_thick_mode=True)

        # Try thin mode
        ok, ver, err = _test_connection(params.host, params.port, params.user, params.password, svc)
        if ok:
            cls._oracle_version = _parse_version(ver)
            logger.info(f"Thin mode OK, version: {ver}")
            return cls.from_uri_db(params.host, params.port, params.user, params.password, params.sid, params.service_name, params.engine_args())

        # Switch to thick mode
        if err == "version_not_supported":
            logger.info("Switching to thick mode")
            if not _init_thick_mode(params.oracle_client_lib):
                raise ValueError("Oracle <12c needs thick mode. Install Instant Client or set ORACLE_INSTANT_CLIENT_HOME.")
            ok, ver, err = _test_connection(params.host, params.port, params.user, params.password, svc, use_thick=True, lib_dir=params.oracle_client_lib)
            if ok:
                cls._oracle_version = _parse_version(ver)
                cls._using_thick_mode = True
                logger.info(f"Thick mode OK, version: {ver}")
                return cls.from_uri_db(params.host, params.port, params.user, params.password, params.sid, params.service_name, params.engine_args(), force_thick_mode=True)
            raise ValueError(f"Thick mode failed: {err}")
        raise ValueError(f"Connection failed: {err}")

    @property
    def oracle_version(self) -> Optional[tuple]:
        return self._oracle_version

    @property
    def using_thick_mode(self) -> bool:
        return self._using_thick_mode

    # --- Dialect overrides (from upstream) ---
    def quote_identifier(self, id: str) -> str:
        return f'"{id}"'

    def limit_sql(self, sql: str, limit: int, offset: int = 0) -> str:
        return f"{sql} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY" if offset else f"{sql} FETCH FIRST {limit} ROWS ONLY"

    def _get_schema_for_inspection(self) -> Optional[str]:
        return None

    def _switch_to_db(self, session, db_name: str):
        pass

    def _sync_tables_from_db(self) -> Iterable[str]:
        with self.session_scope() as s:
            tables = {r[0] for r in s.execute(text("SELECT table_name FROM user_tables"))}
            if self.view_support:
                tables.update(r[0] for r in s.execute(text("SELECT view_name FROM user_views")))
        self._all_tables = tables
        self._metadata = MetaData()
        self._metadata.reflect(bind=self._engine)
        return self._all_tables

    def get_current_db_name(self) -> str:
        with self.session_scope() as s:
            return s.execute(text("SELECT sys_context('USERENV', 'DB_NAME') FROM dual")).scalar()

    def table_simple_info(self):
        with self.session_scope() as s:
            return s.execute(text("SELECT table_name FROM user_tables WHERE table_name NOT LIKE 'BIN$%'")).fetchall()

    def get_show_create_table(self, table_name: str) -> str:
        with self.session_scope() as s:
            rows = s.execute(text(f"SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, data_default FROM user_tab_columns WHERE table_name = '{table_name.upper()}' ORDER BY column_id")).fetchall()
        if not rows:
            return f'-- Table "{table_name.upper()}" not found'
        lines = []
        for r in rows:
            dt = r[1]
            if r[3] is not None:
                dt = f"{dt}({r[3]}{',' + str(r[4]) if r[4] and r[4] > 0 else ''})"
            elif r[2] and r[1] in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR", "RAW"):
                dt = f"{dt}({r[2]})"
            parts = [f'    "{r[0]}" {dt}']
            if r[6]:
                parts.append(f"DEFAULT {str(r[6]).strip()}")
            if r[5] == "N":
                parts.append("NOT NULL")
            lines.append(" ".join(parts))
        return f'CREATE TABLE "{table_name.upper()}" (\n' + ",\n".join(lines) + "\n)"

    def get_simple_fields(self, table_name):
        return self.get_fields(table_name)

    def get_fields(self, table_name: str, db_name=None) -> List[Tuple]:
        with self.session_scope() as s:
            return s.execute(text(f"SELECT col.column_name, col.data_type, col.data_default, col.nullable, comm.comments FROM user_tab_columns col LEFT JOIN user_col_comments comm ON col.table_name = comm.table_name AND col.column_name = comm.column_name WHERE col.table_name = '{table_name.upper()}'")).fetchall()

    def _write(self, sql: str):
        logger.info(f"Write[{sql}]")
        with self.session_scope(commit=False) as s:
            r = s.execute(text(sql))
            s.commit()
            logger.info(f"SQL[{sql}], rows: {r.rowcount}")
            return r.rowcount

    def query_table_schema(self, table_name: str):
        return self._query(f'SELECT * FROM "{table_name.upper()}" FETCH FIRST 1 ROWS ONLY')

    def get_charset(self) -> str:
        with self.session_scope() as s:
            return s.execute(text("SELECT VALUE FROM NLS_DATABASE_PARAMETERS WHERE PARAMETER = 'NLS_CHARACTERSET'")).fetchone()[0]

    def get_grants(self):
        with self.session_scope() as s:
            return s.execute(text("SELECT privilege FROM user_sys_privs")).fetchall()

    def get_users(self) -> List[Tuple[str, None]]:
        with self.session_scope() as s:
            return [(r[0], None) for r in s.execute(text("SELECT username FROM all_users")).fetchall()]

    def get_database_names(self) -> List[str]:
        with self.session_scope() as s:
            try:
                cdb = s.execute(text("SELECT CDB FROM V$DATABASE")).fetchone()[0]
            except Exception:
                return [self.get_current_db_name()]
            if cdb == "YES":
                return [n[0] for n in s.execute(text("SELECT NAME FROM V$PDBS WHERE OPEN_MODE = 'READ WRITE'")).fetchall()]
            return [s.execute(text("SELECT sys_context('USERENV', 'CON_NAME') FROM dual")).fetchone()[0]]

    def get_table_comments(self, db_name: str) -> List[Tuple[str, str]]:
        with self.session_scope() as s:
            return [(r[0], r[1]) for r in s.execute(text("SELECT table_name, comments FROM user_tab_comments")).fetchall()]

    def get_table_comment(self, table_name: str) -> Dict:
        with self.session_scope() as s:
            r = s.execute(text(f"SELECT comments FROM user_tab_comments WHERE table_name = '{table_name.upper()}'")).fetchone()
            return {"text": r[0] if r else ""}

    def get_column_comments(self, db_name: str, table_name: str) -> List[Tuple[str, str]]:
        with self.session_scope() as s:
            return [(r[0], r[1]) for r in s.execute(text(f"SELECT column_name, comments FROM user_col_comments WHERE table_name = '{table_name.upper()}'")).fetchall()]

    def get_collation(self) -> str:
        with self.session_scope() as s:
            return s.execute(text("SELECT value FROM NLS_DATABASE_PARAMETERS WHERE parameter = 'NLS_SORT'")).fetchone()[0]

    def get_oracle_version_info(self) -> dict:
        with self.session_scope() as s:
            rows = s.execute(text("SELECT PRODUCT, VERSION, STATUS FROM PRODUCT_COMPONENT_VERSION WHERE PRODUCT LIKE 'Oracle%' OR PRODUCT LIKE 'PL/SQL%'")).fetchall()
            return {"components": [{"product": r[0], "version": r[1], "status": r[2]} for r in rows], "major_version": self._oracle_version, "using_thick_mode": self._using_thick_mode}