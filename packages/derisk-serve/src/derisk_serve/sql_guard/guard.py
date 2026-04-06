"""SQL Guard engine — core SQL security checker."""

import logging
import re
import time
from typing import Dict, List, Optional

from derisk_serve.sql_guard.config import SQLGuardConfig
from derisk_serve.sql_guard.models import (
    ParsedSQL,
    RiskLevel,
    RuleResult,
    SQLCheckContext,
    SQLCheckResult,
    SQLGuardMode,
    SQLType,
)
from derisk_serve.sql_guard.rules.base import BaseRule
from derisk_serve.sql_guard.rules.permission_rules import (
    ColumnAccessRule,
    DefaultPermissionProvider,
    PermissionProvider,
    TableAccessRule,
)
from derisk_serve.sql_guard.rules.scope_rules import RequireWhereRule, SelectLimitRule
from derisk_serve.sql_guard.rules.syntax_rules import (
    BlockDDLRule,
    BlockGrantRevokeRule,
    BlockTruncateRule,
    ReadonlyModeRule,
)

logger = logging.getLogger(__name__)

# Regex patterns for SQL parsing
_TABLE_PATTERN = re.compile(
    r"(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+`?(\w+)`?", re.IGNORECASE
)
_WHERE_PATTERN = re.compile(r"\bWHERE\b", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)", re.IGNORECASE)
_SQL_TYPE_PATTERNS = [
    (re.compile(r"^\s*SELECT\b", re.IGNORECASE), SQLType.SELECT.value),
    (re.compile(r"^\s*INSERT\b", re.IGNORECASE), SQLType.INSERT.value),
    (re.compile(r"^\s*UPDATE\b", re.IGNORECASE), SQLType.UPDATE.value),
    (re.compile(r"^\s*DELETE\b", re.IGNORECASE), SQLType.DELETE.value),
    (re.compile(r"^\s*WITH\b", re.IGNORECASE), SQLType.WITH.value),
    (re.compile(r"^\s*SHOW\b", re.IGNORECASE), SQLType.SHOW.value),
    (re.compile(r"^\s*(DESC|DESCRIBE)\b", re.IGNORECASE), SQLType.DESCRIBE.value),
    (re.compile(r"^\s*EXPLAIN\b", re.IGNORECASE), SQLType.EXPLAIN.value),
    (re.compile(r"^\s*(CREATE|ALTER|DROP|TRUNCATE)\b", re.IGNORECASE), SQLType.DDL.value),
    (re.compile(r"^\s*(GRANT|REVOKE)\b", re.IGNORECASE), SQLType.DCL.value),
]


class SQLGuardError(Exception):
    """Raised when SQL is blocked by guard."""

    def __init__(self, message: str, check_result: Optional[SQLCheckResult] = None):
        super().__init__(message)
        self.check_result = check_result


class SQLGuard:
    """SQL security audit engine.

    Independent module that can be called from any SQL execution path.
    Supports pluggable rules and external permission system integration.
    """

    def __init__(self, config: Optional[SQLGuardConfig] = None):
        self._config = config or SQLGuardConfig()
        self._rules: List[BaseRule] = []
        self._permission_provider: PermissionProvider = DefaultPermissionProvider()
        self._audit_dao = None
        self._load_default_rules()

    def _load_default_rules(self):
        """Load the default built-in rules."""
        self._rules = [
            ReadonlyModeRule(),
            BlockDDLRule(),
            BlockTruncateRule(),
            BlockGrantRevokeRule(),
            RequireWhereRule(),
            SelectLimitRule(
                default_limit=self._config.default_select_limit,
                max_limit=self._config.max_select_limit,
            ),
            TableAccessRule(self._permission_provider),
            ColumnAccessRule(self._permission_provider),
        ]

    @property
    def config(self) -> SQLGuardConfig:
        """Return the current configuration."""
        return self._config

    def update_config(self, config: SQLGuardConfig):
        """Update configuration and reload rules."""
        self._config = config
        self._load_default_rules()

    def register_rule(self, rule: BaseRule):
        """Register a custom rule."""
        self._rules.append(rule)

    def set_permission_provider(self, provider: PermissionProvider):
        """Set the external permission provider.

        This updates all permission-based rules to use the new provider.
        """
        self._permission_provider = provider
        for rule in self._rules:
            if isinstance(rule, (TableAccessRule, ColumnAccessRule)):
                rule.set_provider(provider)

    def get_rules(self) -> List[Dict]:
        """Return information about all registered rules."""
        return [
            {
                "name": rule.name,
                "description": rule.description,
                "enabled": (
                    rule.enabled and rule.name not in self._config.disabled_rules
                ),
            }
            for rule in self._rules
        ]

    def parse_sql(self, sql: str) -> ParsedSQL:
        """Parse SQL into structured information for rule evaluation."""
        normalized = sql.strip()

        # Detect SQL type
        sql_type = SQLType.UNKNOWN.value
        for pattern, stype in _SQL_TYPE_PATTERNS:
            if pattern.match(normalized):
                sql_type = stype
                break

        # Extract tables
        tables = list(set(_TABLE_PATTERN.findall(normalized)))

        # Detect WHERE and LIMIT
        has_where = bool(_WHERE_PATTERN.search(normalized))
        limit_match = _LIMIT_PATTERN.search(normalized)
        has_limit = bool(limit_match)
        limit_value = int(limit_match.group(1)) if limit_match else None

        return ParsedSQL(
            raw_sql=sql,
            normalized_sql=normalized,
            sql_type=sql_type,
            tables=tables,
            has_where=has_where,
            has_limit=has_limit,
            limit_value=limit_value,
        )

    def check(
        self,
        sql: str,
        *,
        user_id: Optional[str] = None,
        datasource_id: Optional[int] = None,
        db_name: Optional[str] = None,
        mode: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> SQLCheckResult:
        """Check SQL against all registered rules.

        Args:
            sql: The SQL statement to check.
            user_id: The user executing the SQL.
            datasource_id: The target datasource ID.
            db_name: The target database name.
            mode: Override the execution mode. If None, determined from config.
            session_id: The conversation session ID.
            agent_name: The agent executing the SQL.
            context: Additional context dict.

        Returns:
            SQLCheckResult indicating whether the SQL is allowed.
        """
        if not self._config.enabled:
            return SQLCheckResult(allowed=True)

        start_time = time.time()

        # Determine effective mode
        effective_mode = mode or self._config.get_effective_mode(
            user_id=user_id, datasource_id=datasource_id
        )

        # Parse SQL
        parsed = self.parse_sql(sql)

        # Build context
        check_ctx = SQLCheckContext(
            user_id=user_id,
            datasource_id=datasource_id,
            db_name=db_name,
            mode=effective_mode,
            session_id=session_id,
            agent_name=agent_name,
            extra=context or {},
        )

        # Run all rules
        blocked_rules = []
        warnings = []
        details = []
        max_risk_score = 0
        max_risk_level = RiskLevel.SAFE.value
        rewritten_sql = None

        for rule in self._rules:
            if rule.name in self._config.disabled_rules:
                continue
            if not rule.enabled:
                continue

            try:
                result = rule.check(parsed, check_ctx)
                details.append(result)

                if not result.passed:
                    blocked_rules.append(result.rule_name)
                elif result.message:
                    warnings.append(result.message)

                if result.risk_score > max_risk_score:
                    max_risk_score = result.risk_score
                    max_risk_level = result.risk_level

                # Handle rewrite rules (e.g., SelectLimitRule)
                if (
                    result.passed
                    and hasattr(rule, "rewrite")
                    and rewritten_sql is None
                ):
                    rw = rule.rewrite(sql, parsed)
                    if rw:
                        rewritten_sql = rw

            except Exception as e:
                logger.error(f"Rule '{rule.name}' failed: {e}")
                warnings.append(f"Rule '{rule.name}' error: {str(e)}")

        allowed = len(blocked_rules) == 0
        duration_ms = (time.time() - start_time) * 1000

        check_result = SQLCheckResult(
            allowed=allowed,
            risk_level=max_risk_level,
            risk_score=max_risk_score,
            blocked_rules=blocked_rules,
            warnings=warnings,
            rewritten_sql=rewritten_sql if allowed else None,
            sql_type=parsed.sql_type,
            details=details,
        )

        # Audit logging (async, non-blocking)
        if self._config.audit_enabled:
            self._log_audit(
                sql=sql,
                parsed=parsed,
                check_result=check_result,
                context=check_ctx,
                duration_ms=duration_ms,
            )

        return check_result

    def check_batch(
        self, sqls: List[str], **kwargs
    ) -> List[SQLCheckResult]:
        """Check multiple SQL statements."""
        return [self.check(sql, **kwargs) for sql in sqls]

    def _log_audit(
        self,
        sql: str,
        parsed: ParsedSQL,
        check_result: SQLCheckResult,
        context: SQLCheckContext,
        duration_ms: float,
    ):
        """Log the SQL check to audit storage."""
        try:
            if self._audit_dao is None:
                from derisk_serve.sql_guard.audit.dao import SqlAuditLogDao

                self._audit_dao = SqlAuditLogDao()

            self._audit_dao.create({
                "user_id": context.user_id,
                "session_id": context.session_id,
                "datasource_id": context.datasource_id,
                "db_name": context.db_name,
                "agent_name": context.agent_name,
                "sql_text": sql[:4000],
                "sql_type": parsed.sql_type,
                "guard_mode": context.mode,
                "check_result": "allowed" if check_result.allowed else "blocked",
                "risk_level": check_result.risk_level,
                "risk_score": check_result.risk_score,
                "blocked_rules": (
                    ",".join(check_result.blocked_rules)
                    if check_result.blocked_rules
                    else None
                ),
                "duration_ms": duration_ms,
            })
        except Exception as e:
            logger.warning(f"Failed to write SQL audit log: {e}")


# Module-level singleton
_guard_instance: Optional[SQLGuard] = None


def get_sql_guard(config: Optional[SQLGuardConfig] = None) -> SQLGuard:
    """Get the module-level SQLGuard singleton."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = SQLGuard(config)
    return _guard_instance


def reset_sql_guard():
    """Reset the singleton (for testing)."""
    global _guard_instance
    _guard_instance = None
