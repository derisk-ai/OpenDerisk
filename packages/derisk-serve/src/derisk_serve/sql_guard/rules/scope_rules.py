"""Scope-level SQL Guard rules.

Enforce data-safety constraints like requiring WHERE clauses and LIMIT.
"""

import re
from typing import Optional

from derisk_serve.sql_guard.models import (
    ParsedSQL,
    RiskLevel,
    RuleResult,
    SQLCheckContext,
    SQLGuardMode,
    SQLType,
)
from derisk_serve.sql_guard.rules.base import BaseRule


class RequireWhereRule(BaseRule):
    """Require WHERE clause for DELETE and UPDATE statements."""

    @property
    def name(self) -> str:
        return "require_where"

    @property
    def description(self) -> str:
        return "DELETE/UPDATE must include a WHERE clause"

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if context.mode == SQLGuardMode.ADMIN.value:
            return RuleResult(passed=True, rule_name=self.name)

        if parsed_sql.sql_type in (SQLType.DELETE.value, SQLType.UPDATE.value):
            if not parsed_sql.has_where:
                return RuleResult(
                    passed=False,
                    rule_name=self.name,
                    message=(
                        f"{parsed_sql.sql_type} without WHERE clause is dangerous "
                        f"and not allowed."
                    ),
                    risk_score=90,
                    risk_level=RiskLevel.CRITICAL.value,
                )
        return RuleResult(passed=True, rule_name=self.name)


class SelectLimitRule(BaseRule):
    """Add default LIMIT to SELECT queries without one.

    This rule does not block — it rewrites the SQL to include a LIMIT
    clause when missing, preventing unbounded result sets.
    """

    def __init__(self, default_limit: int = 1000, max_limit: int = 10000):
        self._default_limit = default_limit
        self._max_limit = max_limit

    @property
    def name(self) -> str:
        return "select_limit"

    @property
    def description(self) -> str:
        return "Auto-add LIMIT to SELECT without one; cap excessive LIMIT values"

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if parsed_sql.sql_type != SQLType.SELECT.value:
            return RuleResult(passed=True, rule_name=self.name)

        if self._default_limit <= 0:
            return RuleResult(passed=True, rule_name=self.name)

        if not parsed_sql.has_limit:
            return RuleResult(
                passed=True,
                rule_name=self.name,
                message=f"Auto-adding LIMIT {self._default_limit}",
                risk_score=10,
                risk_level=RiskLevel.LOW.value,
            )

        if (
            self._max_limit > 0
            and parsed_sql.limit_value
            and parsed_sql.limit_value > self._max_limit
        ):
            return RuleResult(
                passed=True,
                rule_name=self.name,
                message=(
                    f"LIMIT {parsed_sql.limit_value} exceeds max "
                    f"{self._max_limit}, will be capped."
                ),
                risk_score=20,
                risk_level=RiskLevel.LOW.value,
            )

        return RuleResult(passed=True, rule_name=self.name)

    def rewrite(self, sql: str, parsed_sql: ParsedSQL) -> Optional[str]:
        """Rewrite SQL to add or cap LIMIT.

        Returns None if no rewrite is needed.
        """
        if parsed_sql.sql_type != SQLType.SELECT.value:
            return None
        if self._default_limit <= 0:
            return None

        if not parsed_sql.has_limit:
            cleaned = sql.rstrip().rstrip(";")
            return f"{cleaned} LIMIT {self._default_limit}"

        if (
            self._max_limit > 0
            and parsed_sql.limit_value
            and parsed_sql.limit_value > self._max_limit
        ):
            pattern = re.compile(
                r"\bLIMIT\s+" + str(parsed_sql.limit_value), re.IGNORECASE
            )
            return pattern.sub(f"LIMIT {self._max_limit}", sql)

        return None
