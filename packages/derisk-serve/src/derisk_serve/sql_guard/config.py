"""SQL Guard configuration."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from derisk_serve.sql_guard.models import SQLGuardMode


@dataclass
class SQLGuardConfig:
    """Configuration for SQL Guard."""

    # Default execution mode
    default_mode: str = SQLGuardMode.READONLY.value

    # Whether to enable SQL Guard
    enabled: bool = True

    # Whether to enable audit logging
    audit_enabled: bool = True

    # Default LIMIT to add to SELECT without LIMIT (0 = disabled)
    default_select_limit: int = 1000

    # Max allowed LIMIT value (0 = no restriction)
    max_select_limit: int = 10000

    # Rules to disable (by rule name)
    disabled_rules: List[str] = field(default_factory=list)

    # Per-datasource mode overrides: {datasource_id: mode}
    datasource_modes: Dict[int, str] = field(default_factory=dict)

    # Per-user mode overrides: {user_id: mode}
    user_modes: Dict[str, str] = field(default_factory=dict)

    def get_effective_mode(
        self,
        user_id: Optional[str] = None,
        datasource_id: Optional[int] = None,
    ) -> str:
        """Get the effective mode considering overrides.

        Priority: user_modes > datasource_modes > default_mode
        """
        if user_id and user_id in self.user_modes:
            return self.user_modes[user_id]
        if datasource_id and datasource_id in self.datasource_modes:
            return self.datasource_modes[datasource_id]
        return self.default_mode
