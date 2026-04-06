"""Base rule interface for SQL Guard."""

from abc import ABC, abstractmethod

from derisk_serve.sql_guard.models import ParsedSQL, RuleResult, SQLCheckContext


class BaseRule(ABC):
    """Abstract base class for SQL Guard rules.

    Each rule inspects a parsed SQL statement and context, returning
    a RuleResult indicating whether the SQL passes the check.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Rule identifier."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""

    @property
    def enabled(self) -> bool:
        """Whether this rule is active."""
        return True

    @abstractmethod
    def check(self, parsed_sql: ParsedSQL, context: SQLCheckContext) -> RuleResult:
        """Evaluate the SQL against this rule.

        Args:
            parsed_sql: The parsed SQL information.
            context: Execution context (user, mode, datasource, etc.).

        Returns:
            RuleResult with passed=True if allowed, False if blocked.
        """
