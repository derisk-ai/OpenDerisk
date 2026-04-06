"""Vertica dialect."""

from __future__ import absolute_import, division, print_function

from .base import VerticaDialect as BaseVerticaDialect


# noinspection PyAbstractClass, PyClassHasNoInit
class VerticaDialect(BaseVerticaDialect):
    """Vertica dialect class."""

    driver = "vertica_python"
    supports_statement_cache = False
    postfetch_lastrowid = False

    @classmethod
    def dbapi(cls):
        """Get Driver."""
        vertica_python = __import__("vertica_python")
        return vertica_python
