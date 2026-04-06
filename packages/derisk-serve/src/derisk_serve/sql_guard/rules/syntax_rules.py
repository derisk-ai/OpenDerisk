"""Syntax-level SQL Guard rules.

Block dangerous DDL/DCL statements and enforce mode restrictions.
"""

import re

from derisk_serve.sql_guard.models import (
    ParsedSQL,
    RiskLevel,
    RuleResult,
    SQLCheckContext,
    SQLGuardMode,
    SQLType,
)
from derisk_serve.sql_guard.rules.base import BaseRule

# Statements allowed in readonly mode
_READONLY_TYPES = {
    SQLType.SELECT.value,
    SQLType.SHOW.value,
    SQLType.DESCRIBE.value,
    SQLType.EXPLAIN.value,
    SQLType.WITH.value,
}


class ReadonlyModeRule(BaseRule):
    """In readonly mode, only allow query-type statements."""

    @property
    def name(self) -> str:
        return "readonly_mode"

    @property
    def description(self) -> str:
        return "Only SELECT/SHOW/DESCRIBE/EXPLAIN/WITH allowed in readonly mode"

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if context.mode != SQLGuardMode.READONLY.value:
            return RuleResult(passed=True, rule_name=self.name)

        if parsed_sql.sql_type in _READONLY_TYPES:
            return RuleResult(passed=True, rule_name=self.name)

        return RuleResult(
            passed=False,
            rule_name=self.name,
            message=(
                f"Statement type '{parsed_sql.sql_type}' is not allowed "
                f"in readonly mode. Only query statements are permitted."
            ),
            risk_score=80,
            risk_level=RiskLevel.HIGH.value,
        )


class BlockDDLRule(BaseRule):
    """Block destructive DDL statements."""

    _DDL_PATTERNS = [
        (
            re.compile(
                r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|TRIGGER|PROCEDURE|FUNCTION)\b",
                re.IGNORECASE,
            ),
            "DROP",
        ),
        (
            re.compile(r"\bALTER\s+TABLE\b.*\bDROP\b", re.IGNORECASE),
            "ALTER TABLE ... DROP",
        ),
    ]

    @property
    def name(self) -> str:
        return "block_ddl"

    @property
    def description(self) -> str:
        return "Block destructive DDL: DROP TABLE/DATABASE/INDEX/VIEW, ALTER TABLE DROP"

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if context.mode == SQLGuardMode.ADMIN.value:
            return RuleResult(passed=True, rule_name=self.name)

        sql = parsed_sql.normalized_sql
        for pattern, label in self._DDL_PATTERNS:
            if pattern.search(sql):
                return RuleResult(
                    passed=False,
                    rule_name=self.name,
                    message=f"Destructive DDL '{label}' is blocked.",
                    risk_score=95,
                    risk_level=RiskLevel.CRITICAL.value,
                )
        return RuleResult(passed=True, rule_name=self.name)


class BlockTruncateRule(BaseRule):
    """Block TRUNCATE TABLE statements."""

    _PATTERN = re.compile(r"\bTRUNCATE\b", re.IGNORECASE)

    @property
    def name(self) -> str:
        return "block_truncate"

    @property
    def description(self) -> str:
        return "Block TRUNCATE TABLE statements"

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if context.mode == SQLGuardMode.ADMIN.value:
            return RuleResult(passed=True, rule_name=self.name)

        if self._PATTERN.search(parsed_sql.normalized_sql):
            return RuleResult(
                passed=False,
                rule_name=self.name,
                message="TRUNCATE is blocked.",
                risk_score=95,
                risk_level=RiskLevel.CRITICAL.value,
            )
        return RuleResult(passed=True, rule_name=self.name)


class BlockGrantRevokeRule(BaseRule):
    """Block privilege management statements."""

    _PATTERNS = [
        re.compile(r"\bGRANT\b", re.IGNORECASE),
        re.compile(r"\bREVOKE\b", re.IGNORECASE),
        re.compile(r"\bCREATE\s+USER\b", re.IGNORECASE),
        re.compile(r"\bDROP\s+USER\b", re.IGNORECASE),
        re.compile(r"\bALTER\s+USER\b", re.IGNORECASE),
    ]

    @property
    def name(self) -> str:
        return "block_grant_revoke"

    @property
    def description(self) -> str:
        return "Block GRANT/REVOKE/CREATE USER/DROP USER/ALTER USER"

    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        if context.mode == SQLGuardMode.ADMIN.value:
            return RuleResult(passed=True, rule_name=self.name)

        sql = parsed_sql.normalized_sql
        for pattern in self._PATTERNS:
            if pattern.search(sql):
                return RuleResult(
                    passed=False,
                    rule_name=self.name,
                    message="Privilege management statements are blocked.",
                    risk_score=90,
                    risk_level=RiskLevel.CRITICAL.value,
                )
        return RuleResult(passed=True, rule_name=self.name)
