"""SQLAlchemy data types for StarRocks."""

import logging
import re
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import Float, Integer, Numeric
from sqlalchemy.sql import sqltypes
from sqlalchemy.sql.type_api import TypeEngine

logger = logging.getLogger(__name__)


class TINYINT(Integer):
    """StarRocks TINYINT type."""

    __visit_name__ = "TINYINT"


class LARGEINT(Integer):
    """StarRocks LARGEINT type."""

    __visit_name__ = "LARGEINT"


class DOUBLE(Float):
    """StarRocks DOUBLE type."""

    __visit_name__ = "DOUBLE"


class HLL(Numeric):
    """StarRocks HLL type."""

    __visit_name__ = "HLL"


class BITMAP(Numeric):
    """StarRocks BITMAP type."""

    __visit_name__ = "BITMAP"


class PERCENTILE(Numeric):
    """StarRocks PERCENTILE type."""

    __visit_name__ = "PERCENTILE"


class ARRAY(TypeEngine):
    """StarRocks ARRAY type."""

    __visit_name__ = "ARRAY"

    @property
    def python_type(self) -> Optional[Type[List[Any]]]:
        """Return the Python type for this SQL type."""
        return list


class MAP(TypeEngine):
    """StarRocks MAP type."""

    __visit_name__ = "MAP"

    @property
    def python_type(self) -> Optional[Type[Dict[Any, Any]]]:
        """Return the Python type for this SQL type."""
        return dict


class STRUCT(TypeEngine):
    """StarRocks STRUCT type."""

    __visit_name__ = "STRUCT"

    @property
    def python_type(self) -> Optional[Type[Any]]:
        """Return the Python type for this SQL type."""
        return None


_type_map = {
    # === Boolean ===
    "boolean": sqltypes.BOOLEAN,
    # === Integer ===
    "tinyint": sqltypes.SMALLINT,
    "smallint": sqltypes.SMALLINT,
    "int": sqltypes.INTEGER,
    "bigint": sqltypes.BIGINT,
    "largeint": LARGEINT,
    # === Floating-point ===
    "float": sqltypes.FLOAT,
    "double": DOUBLE,
    # === Fixed-precision ===
    "decimal": sqltypes.DECIMAL,
    # === String ===
    "varchar": sqltypes.VARCHAR,
    "char": sqltypes.CHAR,
    "json": sqltypes.JSON,
    # === Date and time ===
    "date": sqltypes.DATE,
    "datetime": sqltypes.DATETIME,
    "timestamp": sqltypes.DATETIME,
    # === Structural ===
    "array": ARRAY,
    "map": MAP,
    "struct": STRUCT,
    "hll": HLL,
    "percentile": PERCENTILE,
    "bitmap": BITMAP,
}


def parse_sqltype(type_str: str) -> TypeEngine:
    """Parse a SQL type string into a SQLAlchemy type object."""
    type_str = type_str.strip().lower()
    match = re.match(r"^(?P<type>\w+)\s*(?:\((?P<options>.*)\))?", type_str)
    if not match:
        logger.warning(f"Could not parse type name '{type_str}'")
        return sqltypes.NULLTYPE
    type_name = match.group("type")

    if type_name not in _type_map:
        logger.warning(f"Did not recognize type '{type_name}'")
        return sqltypes.NULLTYPE
    type_class = _type_map[type_name]
    return type_class()
