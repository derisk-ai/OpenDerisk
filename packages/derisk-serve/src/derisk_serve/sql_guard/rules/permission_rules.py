"""Permission-based SQL Guard rules.

Provides table-level and column-level access control via a pluggable
PermissionProvider interface. This allows integration with external
RBAC/ABAC permission systems.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from derisk_serve.sql_guard.models import (
    ParsedSQL,
    RiskLevel,
    RuleResult,
    SQLCheckContext,
)
from derisk_serve.sql_guard.rules.base import BaseRule


class PermissionProvider(ABC):
    """Interface for external permission systems.

    Implement this to integrate SQL Guard with your RBAC/ABAC system.
    """

    @abstractmethod
    def check_table_access(
        self,
        user_id: str,
        datasource_id: int,
        table_name: str,
        operation: str,
    ) -> bool:
        """Check if user has permission for the operation on the table.

        Args:
            user_id: The user identifier.
            datasource_id: The datasource ID.
            table_name: The table to check.
            operation: SQL operation type (SELECT/INSERT/UPDATE/DELETE).

        Returns:
            True if access is allowed.
        """

    @abstractmethod
    def check_column_access(
        self,
        user_id: str,
        datasource_id: int,
        table_name: str,
        column_names: List[str],
    ) -> List[str]:
        """Check column-level access.

        Args:
            user_id: The user identifier.
            datasource_id: The datasource ID.
            table_name: The table name.
            column_names: Columns to check.

        Returns:
            List of column names the user does NOT have access to.
        """

    @abstractmethod
    def get_allowed_tables(
        self,
        user_id: str,
        datasource_id: int,
    ) -> Optional[List[str]]:
        """Get the list of tables the user can access.

        Returns:
            List of allowed table names, or None if no restriction.
        """

    @abstractmethod
    def get_row_filter(
        self,
        user_id: str,
        datasource_id: int,
        table_name: str,
    ) -> Optional[str]:
        """Get row-level filter condition for the user.

        Returns:
            A WHERE clause fragment (e.g., "tenant_id = 'abc'"),
            or None if no row-level filtering.
        """


class DefaultPermissionProvider(PermissionProvider):
    """Default no-op permission provider. Allows all access."""

    def check_table_access(
        self, user_id: str, datasource_id: int, table_name: str, operation: str
    ) -> bool:
        return True

    def check_column_access(
        self,
        user_id: str,
        datasource_id: int,
        table_name: str,
        column_names: List[str],
    ) -> List[str]:
        return []

    def get_allowed_tables(
        self, user_id: str, datasource_id: int
    ) -> Optional[List[str]]:
        return None

    def get_row_filter(
        self, user_id: str, datasource_id: int, table_name: str
    ) -> Optional[str]:
        return None


class TableAccessRule(BaseRule):
    """Enforce table-level access control via PermissionProvider."""

    def __init__(self, provider: Optional[PermissionProvider] = None):
        self._provider = provider or DefaultPermissionProvider()

    @property
    def name(self) -> str:
        return "table_access"

    @property
    def description(self) -> str:
        return "Check table-level access permission via PermissionProvider"

    def set_provider(self, provider: PermissionProvider):
        """Update the permission provider."""
        self._provider = provider

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if not context.user_id or not context.datasource_id:
            return RuleResult(passed=True, rule_name=self.name)

        # Check allowed tables list
        allowed = self._provider.get_allowed_tables(
            context.user_id, context.datasource_id
        )
        if allowed is not None:
            denied_tables = [t for t in parsed_sql.tables if t not in allowed]
            if denied_tables:
                return RuleResult(
                    passed=False,
                    rule_name=self.name,
                    message=(
                        f"Access denied to table(s): {', '.join(denied_tables)}. "
                        f"User '{context.user_id}' does not have permission."
                    ),
                    risk_score=85,
                    risk_level=RiskLevel.HIGH.value,
                )

        # Check per-table operation permission
        for table in parsed_sql.tables:
            if not self._provider.check_table_access(
                context.user_id,
                context.datasource_id,
                table,
                parsed_sql.sql_type,
            ):
                return RuleResult(
                    passed=False,
                    rule_name=self.name,
                    message=(
                        f"User '{context.user_id}' does not have "
                        f"{parsed_sql.sql_type} permission on table '{table}'."
                    ),
                    risk_score=85,
                    risk_level=RiskLevel.HIGH.value,
                )

        return RuleResult(passed=True, rule_name=self.name)


class ColumnAccessRule(BaseRule):
    """Enforce column-level access control via PermissionProvider."""

    def __init__(self, provider: Optional[PermissionProvider] = None):
        self._provider = provider or DefaultPermissionProvider()

    @property
    def name(self) -> str:
        return "column_access"

    @property
    def description(self) -> str:
        return "Check column-level access permission via PermissionProvider"

    def set_provider(self, provider: PermissionProvider):
        """Update the permission provider."""
        self._provider = provider

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if not context.user_id or not context.datasource_id:
            return RuleResult(passed=True, rule_name=self.name)

        if not parsed_sql.columns or not parsed_sql.tables:
            return RuleResult(passed=True, rule_name=self.name)

        # Check columns against each table
        for table in parsed_sql.tables:
            denied_cols = self._provider.check_column_access(
                context.user_id,
                context.datasource_id,
                table,
                parsed_sql.columns,
            )
            if denied_cols:
                return RuleResult(
                    passed=False,
                    rule_name=self.name,
                    message=(
                        f"Access denied to column(s) {denied_cols} "
                        f"in table '{table}' for user '{context.user_id}'."
                    ),
                    risk_score=75,
                    risk_level=RiskLevel.HIGH.value,
                )

        return RuleResult(passed=True, rule_name=self.name)
