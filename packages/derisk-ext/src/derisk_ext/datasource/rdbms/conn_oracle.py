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


# Parent directories to search for instantclient subdirectories
SEARCH_PARENT_DIRS = {
    "Darwin": ["/opt/oracle", "/usr/local/lib", "/usr/lib", "/opt"],
    "Linux": ["/opt/oracle", "/usr/lib/oracle", "/usr/local/lib/oracle", "/opt", "/usr/lib"],
    "Windows": ["C:\\Oracle", "C:\\Program Files\\Oracle", "D:\\Oracle"],
}


def _find_instant_client_paths() -> list:
    """Find potential Oracle Instant Client paths.

    Searches in order:
    1. Environment variables (ORACLE_INSTANT_CLIENT_HOME, ORACLE_HOME)
    2. Library path (LD_LIBRARY_PATH, DYLD_LIBRARY_PATH)
    3. Parent directories for instantclient_* subdirs (e.g. /opt/oracle/instantclient_11_2)
    4. Default fixed paths
    """
    paths = []
    system = platform.system()

    # 1. Environment variables (highest priority)
    for env_var in ["ORACLE_INSTANT_CLIENT_HOME", "ORACLE_HOME"]:
        env_path = os.environ.get(env_var)
        if env_path and os.path.isdir(env_path):
            paths.append(env_path)

    # 2. Library path
    lib_path_env = "DYLD_LIBRARY_PATH" if system == "Darwin" else "LD_LIBRARY_PATH"
    lib_path = os.environ.get(lib_path_env)
    if lib_path:
        for p in lib_path.split(":"):
            p = p.strip()
            if p and os.path.isdir(p) and "oracle" in p.lower():
                paths.append(p)

    # 3. Search parent directories for instantclient subdirs
    # This handles paths like /opt/oracle/instantclient_11_2, /opt/oracle/instantclient_19_8, etc.
    for parent_dir in SEARCH_PARENT_DIRS.get(system, []):
        if not os.path.isdir(parent_dir):
            continue
        try:
            for entry in os.listdir(parent_dir):
                full_path = os.path.join(parent_dir, entry)
                # Match instantclient_11_2, instantclient_19_8, instantclient-basic, etc.
                if "instantclient" in entry.lower() and os.path.isdir(full_path):
                    paths.append(full_path)
        except (PermissionError, OSError):
            continue

    # 4. Default fixed paths (fallback)
    for p in DEFAULT_INSTANT_CLIENT_PATHS.get(system, []):
        expanded = os.path.expanduser(p)
        if os.path.isdir(expanded) and expanded not in paths:
            paths.append(expanded)

    return paths


def _init_thick_mode(lib_dir: Optional[str] = None) -> bool:
    """Initialize Oracle thick mode.

    IMPORTANT: This can only be called ONCE per process, BEFORE any Oracle connection.
    Once initialized, ALL subsequent connections in this process will use thick mode.

    For multi-worker deployments (e.g., uvicorn --workers N):
    - Each worker process is independent and needs its own initialization
    - This function is called during component initialization, which runs in each worker
    - The global state _thick_mode_initialized is per-process, not shared

    Args:
        lib_dir: Optional path to Oracle Instant Client directory

    Returns:
        True if thick mode is available (initialized or already was), False otherwise
    """
    global _thick_mode_initialized, _thick_mode_failed

    logger.info(f"[ThickMode] _init_thick_mode called with lib_dir={lib_dir}")
    logger.info(f"[ThickMode] Current state: initialized={_thick_mode_initialized}, failed={_thick_mode_failed}")

    # Check if already initialized in this process
    if _thick_mode_initialized:
        logger.info("[ThickMode] Already initialized in this process, returning True")
        return True
    if _thick_mode_failed:
        logger.info("[ThickMode] Previously failed in this process, returning False")
        return False

    try:
        import oracledb

        logger.info(f"[ThickMode] oracledb imported, version={oracledb.__version__}")

        # Check if thick mode is already active (via library state, not just Python global)
        # This handles cases where init was called in parent process before fork
        try:
            # is_thin_mode() returns False if thick mode is active
            if hasattr(oracledb, 'is_thin_mode'):
                is_thin = oracledb.is_thin_mode()
                logger.info(f"[ThickMode] oracledb.is_thin_mode() = {is_thin}")
                if not is_thin:
                    logger.info("[ThickMode] Thick mode already active (detected via is_thin_mode)")
                    _thick_mode_initialized = True
                    return True
        except Exception as e:
            logger.debug(f"[ThickMode] Could not check is_thin_mode: {e}")

        # Attempt to initialize thick mode
        # Use provided lib_dir
        logger.info(f"[ThickMode] Checking lib_dir={lib_dir}, is_dir={os.path.isdir(lib_dir) if lib_dir else 'N/A'}")
        if lib_dir and os.path.isdir(lib_dir):
            try:
                oracledb.init_oracle_client(lib_dir=lib_dir)
                logger.info(f"[ThickMode] Oracle thick mode initialized with lib_dir: {lib_dir}")
                _thick_mode_initialized = True
                return True
            except Exception as e:
                # Check if error indicates thick mode is already initialized
                if "already initialized" in str(e).lower() or "can only be called once" in str(e).lower():
                    logger.info("[ThickMode] Oracle thick mode already initialized (detected via error)")
                    _thick_mode_initialized = True
                    return True
                logger.warning(f"[ThickMode] Failed to init thick mode with lib_dir={lib_dir}: {e}")
        elif lib_dir:
            logger.warning(f"[ThickMode] Provided lib_dir={lib_dir} is not a valid directory or does not exist")

        # Auto-find Instant Client
        found_paths = _find_instant_client_paths()
        logger.debug(f"Found potential Instant Client paths: {found_paths}")
        for path in found_paths:
            try:
                oracledb.init_oracle_client(lib_dir=path)
                logger.info(f"Oracle thick mode auto-detected at: {path}")
                _thick_mode_initialized = True
                return True
            except Exception as e:
                # Check if error indicates thick mode is already initialized
                if "already initialized" in str(e).lower() or "can only be called once" in str(e).lower():
                    logger.info("Oracle thick mode already initialized (detected via error)")
                    _thick_mode_initialized = True
                    return True
                logger.debug(f"Failed to init thick mode at {path}: {e}")
                continue

        # Try system default (no lib_dir specified)
        try:
            oracledb.init_oracle_client()
            logger.info("Oracle thick mode initialized with system default")
            _thick_mode_initialized = True
            return True
        except Exception as e:
            # Check if error indicates thick mode is already initialized
            if "already initialized" in str(e).lower() or "can only be called once" in str(e).lower():
                logger.info("Oracle thick mode already initialized (detected via error)")
                _thick_mode_initialized = True
                return True
            logger.warning(f"Failed to init thick mode with system default: {e}")

        logger.warning(
            "Could not initialize Oracle thick mode. "
            "For Oracle 11g and earlier, please install Oracle Instant Client "
            "and set ORACLE_INSTANT_CLIENT_HOME environment variable."
        )
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


def _test_connection(host, port, user, pwd, service, use_thick=False, lib_dir=None, is_sid=False) -> tuple:
    """Test connection and get version.

    Args:
        host: Database host
        port: Database port
        user: Database user
        pwd: Database password
        service: Service name or SID
        use_thick: Whether to use thick mode
        lib_dir: Oracle Instant Client path
        is_sid: If True, use SID instead of service_name
    """
    try:
        import oracledb

        if use_thick and not _init_thick_mode(lib_dir):
            return (False, "", "thick_init_failed")

        # Use correct parameter based on whether it's SID or service_name
        if is_sid:
            params = oracledb.ConnectParams(host=host, port=port, user=user, password=pwd, sid=service)
        else:
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
        # Check if force_thick_mode is explicitly set to True
        # If not, check global config from ConfigManager
        if not self.force_thick_mode:
            try:
                from derisk_core.config import ConfigManager
                config = ConfigManager.get()
                if config and config.datasource and config.datasource.oracle_enable_thick_mode:
                    self.force_thick_mode = True
                    logger.info(
                        "[OracleParameters] Using global thick mode config "
                        "(oracle_enable_thick_mode=True from System Config)"
                    )
                    # Also set oracle_client_lib from global config if not set
                    if not self.oracle_client_lib and config.datasource.oracle_instant_client_path:
                        self.oracle_client_lib = config.datasource.oracle_instant_client_path
            except Exception as e:
                logger.debug(f"[OracleParameters] Failed to read global config: {e}")
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
    def from_uri_db(cls, host, port, user, pwd, sid=None, service_name=None, engine_args=None, oracle_client_lib=None, force_thick_mode=None, auto_detect=True, **kwargs) -> "OracleConnector":
        """Create connector from URI params with auto version detection.

        Args:
            host: Database host
            port: Database port
            user: Database user
            pwd: Database password
            sid: Oracle SID
            service_name: Oracle service name
            engine_args: SQLAlchemy engine args
            oracle_client_lib: Optional Instant Client path
            force_thick_mode: Force thick mode (None = auto detect)
            auto_detect: If True and force_thick_mode is None, auto detect version
        """
        if not sid and not service_name:
            raise ValueError("sid or service_name required")

        svc = service_name or sid
        # Determine if svc is SID or service_name for connection testing
        is_sid_param = sid is not None and service_name is None

        # If force_thick_mode is explicitly set, use it
        if force_thick_mode is True:
            if not _init_thick_mode(oracle_client_lib):
                raise ValueError("Thick mode init failed. Install Instant Client.")
            cls._using_thick_mode = True
        elif force_thick_mode is None and auto_detect:
            # Auto detect version and switch to thick mode if needed
            # IMPORTANT: Try thick mode FIRST for older Oracle versions
            # because init_oracle_client() can only be called ONCE before any connection
            # Once thick mode is initialized, ALL subsequent connections will use thick mode

            logger.info(f"Auto-detecting Oracle version: {host}:{port}/{svc}")

            # Step 1: Check if Instant Client is available
            # If available, initialize thick mode (this can only be done ONCE per process)
            thick_initialized = _init_thick_mode(oracle_client_lib)

            if thick_initialized:
                # Thick mode is now permanently enabled for this process
                # Test connection with thick mode (use correct SID/service_name parameter)
                ok, ver, err = _test_connection(host, port, user, pwd, svc, use_thick=True, lib_dir=oracle_client_lib, is_sid=is_sid_param)
                if ok:
                    cls._oracle_version = _parse_version(ver)
                    cls._using_thick_mode = True
                    logger.info(f"Thick mode OK, Oracle version: {ver}")
                    # Build connection URL - all subsequent connections will use thick mode
                    dsn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SERVICE_NAME={svc})))" if service_name else f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SID={sid})))"
                    url = f"{cls.driver}://{quote(user)}:{quote_plus(pwd)}@{dsn}"
                    return cls.from_uri(url, engine_args=engine_args, **kwargs)
                else:
                    # Thick mode initialized but connection failed
                    # This could be due to wrong credentials or other issues
                    logger.error(f"Thick mode initialized but connection test failed: {err}")
                    raise ValueError(f"Connection test failed after thick mode init: {err}")

            # Step 2: Thick mode not available (Instant Client not found)
            # Try thin mode (for Oracle 12c+)
            logger.info("Thick mode not available (Instant Client not found), trying thin mode...")
            ok, ver, err = _test_connection(host, port, user, pwd, svc, is_sid=is_sid_param)
            if ok:
                cls._oracle_version = _parse_version(ver)
                logger.info(f"Thin mode OK, Oracle version: {ver}")
            elif err == "version_not_supported":
                # Oracle version requires thick mode but thick mode not available
                raise ValueError(
                    "Oracle <12c needs thick mode but Instant Client not found. "
                    "Install Instant Client or set ORACLE_INSTANT_CLIENT_HOME env variable, "
                    "or set force_thick_mode=True and oracle_client_lib parameter."
                )
            else:
                raise ValueError(f"Connection test failed: {err}")

        # Build connection URL
        dsn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SERVICE_NAME={svc})))" if service_name else f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={host})(PORT={port}))(CONNECT_DATA=(SID={sid})))"
        url = f"{cls.driver}://{quote(user)}:{quote_plus(pwd)}@{dsn}"
        return cls.from_uri(url, engine_args=engine_args, **kwargs)

    @classmethod
    def from_parameters_auto(cls, params: OracleParameters) -> "OracleConnector":
        """Auto-detect mode."""
        svc = params.service_name or params.sid or params.database
        if not svc:
            raise ValueError("service_name/sid/database required")

        # Determine if svc is SID or service_name for connection testing
        is_sid_param = params.sid is not None and params.service_name is None

        if params.force_thick_mode:
            if not _init_thick_mode(params.oracle_client_lib):
                raise ValueError("Thick mode failed. Install Instant Client.")
            cls._using_thick_mode = True
            return cls.from_uri_db(params.host, params.port, params.user, params.password, params.sid, params.service_name, params.engine_args(), force_thick_mode=True)

        # IMPORTANT: Try thick mode FIRST for older Oracle versions
        # because init_oracle_client() can only be called ONCE before any connection

        logger.info(f"Auto-detecting Oracle version for params: {params.host}:{params.port}/{svc}")

        # Step 1: Check if Instant Client is available
        thick_initialized = _init_thick_mode(params.oracle_client_lib)

        if thick_initialized:
            # Thick mode is now permanently enabled for this process
            ok, ver, err = _test_connection(params.host, params.port, params.user, params.password, svc, use_thick=True, lib_dir=params.oracle_client_lib, is_sid=is_sid_param)
            if ok:
                cls._oracle_version = _parse_version(ver)
                cls._using_thick_mode = True
                logger.info(f"Thick mode OK, version: {ver}")
                return cls.from_uri_db(params.host, params.port, params.user, params.password, params.sid, params.service_name, params.engine_args())
            else:
                logger.error(f"Thick mode initialized but connection test failed: {err}")
                raise ValueError(f"Connection test failed after thick mode init: {err}")

        # Step 2: Thick mode not available, try thin mode
        logger.info("Thick mode not available (Instant Client not found), trying thin mode...")
        ok, ver, err = _test_connection(params.host, params.port, params.user, params.password, svc, is_sid=is_sid_param)
        if ok:
            cls._oracle_version = _parse_version(ver)
            logger.info(f"Thin mode OK, version: {ver}")
            return cls.from_uri_db(params.host, params.port, params.user, params.password, params.sid, params.service_name, params.engine_args())

        # Thin mode failed
        if err == "version_not_supported":
            raise ValueError(
                "Oracle <12c needs thick mode but Instant Client not found. "
                "Install Instant Client or set ORACLE_INSTANT_CLIENT_HOME env variable."
            )
        raise ValueError(f"Connection failed: {err}")

    @property
    def oracle_version(self) -> Optional[tuple]:
        return self._oracle_version

    @property
    def using_thick_mode(self) -> bool:
        return self._using_thick_mode

    # --- Dialect overrides (from upstream) ---
    def quote_identifier(self, id: str) -> str:
        """Quote identifier, handling 'owner.table_name' format."""
        if '.' in id:
            owner, tbl = id.split('.', 1)
            return f'"{owner}"."{tbl}"'
        return f'"{id}"'

    def limit_sql(self, sql: str, limit: int, offset: int = 0) -> str:
        """Limit SQL based on Oracle version.

        Oracle 12c+: use FETCH FIRST syntax
        Oracle 11g and earlier: use ROWNUM with subquery
        """
        # Get version from instance or class attribute
        version = getattr(self, '_oracle_version', None) or OracleConnector._oracle_version or (0, 0)

        if version >= (12, 1):
            # Oracle 12c+ supports ANSI FETCH syntax
            if offset:
                return f"{sql} OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
            return f"{sql} FETCH FIRST {limit} ROWS ONLY"
        else:
            # Oracle 11g and earlier: use ROWNUM
            if offset:
                # Need nested subquery for offset
                return f"SELECT * FROM (SELECT a.*, ROWNUM rnum FROM ({sql}) a WHERE ROWNUM <= {offset + limit}) WHERE rnum > {offset}"
            return f"SELECT * FROM ({sql}) WHERE ROWNUM <= {limit}"

    def _get_schema_for_inspection(self) -> Optional[str]:
        return None

    def _switch_to_db(self, session, db_name: str):
        pass

    def _sync_tables_from_db(self) -> Iterable[str]:
        with self.session_scope() as s:
            # Use all_tables to get tables from all accessible schemas
            tables = {f"{r[0]}.{r[1]}" for r in s.execute(text("SELECT owner, table_name FROM all_tables WHERE owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC')"))}
            if self.view_support:
                tables.update(f"{r[0]}.{r[1]}" for r in s.execute(text("SELECT owner, view_name FROM all_views WHERE owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC')")))
        self._all_tables = tables
        self._metadata = MetaData()
        self._metadata.reflect(bind=self._engine)
        return self._all_tables

    def get_current_db_name(self) -> str:
        with self.session_scope() as s:
            return s.execute(text("SELECT sys_context('USERENV', 'DB_NAME') FROM dual")).scalar()

    def table_simple_info(self):
        with self.session_scope() as s:
            # Use all_tables to get tables from all accessible schemas
            return s.execute(text("SELECT owner, table_name FROM all_tables WHERE table_name NOT LIKE 'BIN$%' AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC')")).fetchall()

    def get_show_create_table(self, table_name: str) -> str:
        """Get CREATE TABLE statement using Oracle DBMS_METADATA.

        Args:
            table_name: Can be just table_name or 'owner.table_name' format
        """
        # Parse owner and table_name
        if '.' in table_name:
            owner, tbl = table_name.split('.', 1)
            owner = owner.upper()
            tbl = tbl.upper()
        else:
            owner = None
            tbl = table_name.upper()

        with self.session_scope() as s:
            # If owner not provided, query the real owner from all_tables
            if owner is None:
                real_owner = s.execute(text(f"SELECT owner FROM all_tables WHERE table_name = '{tbl}' AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC') ORDER BY owner")).fetchone()
                if real_owner:
                    owner = real_owner[0]

            # Try DBMS_METADATA.GET_DDL for full CREATE TABLE statement
            try:
                if owner:
                    result = s.execute(text(f"SELECT DBMS_METADATA.GET_DDL('TABLE', '{tbl}', '{owner}') FROM dual")).fetchone()
                else:
                    result = s.execute(text(f"SELECT DBMS_METADATA.GET_DDL('TABLE', '{tbl}') FROM dual")).fetchone()
                if result and result[0]:
                    return str(result[0].read()) if hasattr(result[0], 'read') else str(result[0])
            except Exception as e:
                logger.warning(f"DBMS_METADATA.GET_DDL failed: {e}, falling back to manual method")

            # Fallback: manual column info from all_tab_columns
            if owner:
                rows = s.execute(text(f"SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, data_default FROM all_tab_columns WHERE table_name = '{tbl}' AND owner = '{owner}' ORDER BY column_id")).fetchall()
            else:
                rows = s.execute(text(f"SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, data_default FROM user_tab_columns WHERE table_name = '{tbl}' ORDER BY column_id")).fetchall()

        if not rows:
            return f'-- Table "{tbl}" not found'

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
        return f'CREATE TABLE "{tbl}" (\n' + ",\n".join(lines) + "\n)"

    def get_simple_fields(self, table_name):
        return self.get_fields(table_name)

    def get_fields(self, table_name: str, db_name=None) -> List[Tuple]:
        """Get field information for a table.

        Args:
            table_name: Can be just table_name or 'owner.table_name' format
            db_name: Optional owner/schema name
        """
        # Parse owner and table_name
        if '.' in table_name:
            owner, tbl = table_name.split('.', 1)
            owner = owner.upper()
            tbl = tbl.upper()
        else:
            owner = db_name.upper() if db_name else None
            tbl = table_name.upper()

        with self.session_scope() as s:
            # If owner not provided, query the real owner from all_tables
            if owner is None:
                real_owner = s.execute(text(f"SELECT owner FROM all_tables WHERE table_name = '{tbl}' AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC') ORDER BY owner")).fetchone()
                if real_owner:
                    owner = real_owner[0]

            if owner:
                return s.execute(text(f"SELECT col.column_name, col.data_type, col.data_default, col.nullable, comm.comments FROM all_tab_columns col LEFT JOIN all_col_comments comm ON col.table_name = comm.table_name AND col.column_name = comm.column_name AND col.owner = comm.owner WHERE col.table_name = '{tbl}' AND col.owner = '{owner}'")).fetchall()
            else:
                return s.execute(text(f"SELECT col.column_name, col.data_type, col.data_default, col.nullable, comm.comments FROM user_tab_columns col LEFT JOIN user_col_comments comm ON col.table_name = comm.table_name AND col.column_name = comm.column_name WHERE col.table_name = '{tbl}'")).fetchall()

    def _write(self, sql: str):
        logger.info(f"Write[{sql}]")
        with self.session_scope(commit=False) as s:
            r = s.execute(text(sql))
            s.commit()
            logger.info(f"SQL[{sql}], rows: {r.rowcount}")
            return r.rowcount

    def query_table_schema(self, table_name: str):
        """Query table schema by selecting first row.

        Args:
            table_name: Can be just table_name or 'owner.table_name' format
        """
        if '.' in table_name:
            owner, tbl = table_name.split('.', 1)
            return self._query(f'SELECT * FROM "{owner.upper()}"."{tbl.upper()}" FETCH FIRST 1 ROWS ONLY')
        else:
            # Query real owner from all_tables if not provided
            tbl = table_name.upper()
            with self.session_scope() as s:
                real_owner = s.execute(text(f"SELECT owner FROM all_tables WHERE table_name = '{tbl}' AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC') ORDER BY owner")).fetchone()
                if real_owner:
                    return self._query(f'SELECT * FROM "{real_owner[0]}"."{tbl}" FETCH FIRST 1 ROWS ONLY')
            return self._query(f'SELECT * FROM "{tbl}" FETCH FIRST 1 ROWS ONLY')

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
        """Get table comments for all tables in accessible schemas."""
        with self.session_scope() as s:
            return [(f"{r[0]}.{r[1]}", r[2]) for r in s.execute(text("SELECT owner, table_name, comments FROM all_tab_comments WHERE comments IS NOT NULL AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC')")).fetchall()]

    def get_table_comment(self, table_name: str) -> Dict:
        """Get comment for a specific table.

        Args:
            table_name: Can be just table_name or 'owner.table_name' format
        """
        if '.' in table_name:
            owner, tbl = table_name.split('.', 1)
            owner = owner.upper()
            tbl = tbl.upper()
        else:
            owner = None
            tbl = table_name.upper()

        with self.session_scope() as s:
            # If owner not provided, query the real owner from all_tables
            if owner is None:
                real_owner = s.execute(text(f"SELECT owner FROM all_tables WHERE table_name = '{tbl}' AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC') ORDER BY owner")).fetchone()
                if real_owner:
                    owner = real_owner[0]

            if owner:
                r = s.execute(text(f"SELECT comments FROM all_tab_comments WHERE table_name = '{tbl}' AND owner = '{owner}'")).fetchone()
            else:
                r = s.execute(text(f"SELECT comments FROM user_tab_comments WHERE table_name = '{tbl}'")).fetchone()
            return {"text": r[0] if r else ""}

    def get_column_comments(self, db_name: str, table_name: str) -> List[Tuple[str, str]]:
        """Get column comments for a table.

        Args:
            db_name: Owner/schema name
            table_name: Can be just table_name or 'owner.table_name' format
        """
        if '.' in table_name:
            owner, tbl = table_name.split('.', 1)
            owner = owner.upper()
            tbl = tbl.upper()
        else:
            owner = db_name.upper() if db_name else None
            tbl = table_name.upper()

        with self.session_scope() as s:
            # If owner not provided, query the real owner from all_tables
            if owner is None:
                real_owner = s.execute(text(f"SELECT owner FROM all_tables WHERE table_name = '{tbl}' AND owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'ORDDATA', 'ORDSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER', 'FLOWS_FILES', 'APEX_030200', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS', 'MDSYS', 'PUBLIC') ORDER BY owner")).fetchone()
                if real_owner:
                    owner = real_owner[0]

            if owner:
                return [(r[0], r[1]) for r in s.execute(text(f"SELECT column_name, comments FROM all_col_comments WHERE table_name = '{tbl}' AND owner = '{owner}'")).fetchall()]
            else:
                return [(r[0], r[1]) for r in s.execute(text(f"SELECT column_name, comments FROM user_col_comments WHERE table_name = '{tbl}'")).fetchall()]

    def get_collation(self) -> str:
        with self.session_scope() as s:
            return s.execute(text("SELECT value FROM NLS_DATABASE_PARAMETERS WHERE parameter = 'NLS_SORT'")).fetchone()[0]

    def get_oracle_version_info(self) -> dict:
        with self.session_scope() as s:
            rows = s.execute(text("SELECT PRODUCT, VERSION, STATUS FROM PRODUCT_COMPONENT_VERSION WHERE PRODUCT LIKE 'Oracle%' OR PRODUCT LIKE 'PL/SQL%'")).fetchall()
            return {"components": [{"product": r[0], "version": r[1], "status": r[2]} for r in rows], "major_version": self._oracle_version, "using_thick_mode": self._using_thick_mode}

    def get_db_version(self) -> Optional[str]:
        """Get Oracle database version string.

        Returns:
            Version string (e.g., '11.2', '12.1', '19.0') or None.
        """
        version = getattr(self, '_oracle_version', None) or OracleConnector._oracle_version
        if version and version != (0, 0):
            return f"{version[0]}.{version[1]}"
        return None

    def _parse_table_name_with_schema(self, table_name: str) -> Tuple[str, Optional[str]]:
        """Parse table_name that may contain owner prefix.

        Args:
            table_name: Either 'table_name' or 'owner.table_name' format

        Returns:
            Tuple of (pure_table_name, owner/schema or None)
        """
        if '.' in table_name:
            owner, tbl = table_name.split('.', 1)
            return tbl.upper(), owner.upper()
        return table_name.upper(), None

    def get_columns(self, table_name: str) -> List[Dict]:
        """Get columns about specified table.

        Handles 'owner.table_name' format by passing schema to SQLAlchemy inspector.
        """
        tbl, schema = self._parse_table_name_with_schema(table_name)
        return self._inspector.get_columns(tbl, schema=schema)

    def get_indexes(self, table_name: str) -> List[Dict]:
        """Get indexes about specified table.

        Handles 'owner.table_name' format by passing schema to SQLAlchemy inspector.
        """
        tbl, schema = self._parse_table_name_with_schema(table_name)
        return self._inspector.get_indexes(tbl, schema=schema)

    def get_pk_constraint(self, table_name: str) -> Dict:
        """Get primary key constraint for specified table.

        Handles 'owner.table_name' format by passing schema to SQLAlchemy inspector.
        """
        tbl, schema = self._parse_table_name_with_schema(table_name)
        return self._inspector.get_pk_constraint(tbl, schema=schema)

    def get_foreign_keys(self, table_name: str) -> List[Dict]:
        """Get foreign keys for specified table.

        Handles 'owner.table_name' format by passing schema to SQLAlchemy inspector.
        """
        tbl, schema = self._parse_table_name_with_schema(table_name)
        return self._inspector.get_foreign_keys(tbl, schema=schema)