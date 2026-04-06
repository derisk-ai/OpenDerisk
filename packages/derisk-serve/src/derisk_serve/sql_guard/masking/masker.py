"""Dynamic data masking engine.

Applies format-preserving masking or reversible tokenization to
sensitive column values in SQL query results, before they reach the LLM.

Two modes:
- Masking (default): 138****5678 — human-readable, irreversible
- Tokenization: [PHONE_001] — reversible via session-level mapping
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from derisk_serve.sql_guard.masking.detector import SensitiveType

logger = logging.getLogger(__name__)


class MaskingMode:
    """Masking mode constants."""

    MASK = "mask"  # Partial masking: 138****5678
    TOKEN = "token"  # Reversible token: [PHONE_001]
    NONE = "none"  # No masking (passthrough)


@dataclass
class ColumnMaskingConfig:
    """Masking configuration for a specific column."""

    table_name: str
    column_name: str
    sensitive_type: str
    mode: str = MaskingMode.MASK
    # Custom mask pattern (overrides default)
    custom_pattern: Optional[str] = None


@dataclass
class MaskingContext:
    """Per-session context for tokenization mode.

    Maintains the mapping between real values and tokens,
    enabling reverse-lookup for final delivery.
    """

    session_id: str = ""
    # token → real_value
    _token_map: Dict[str, str] = field(default_factory=dict)
    # real_value → token (for dedup within session)
    _reverse_map: Dict[str, str] = field(default_factory=dict)
    # counter per sensitive type
    _counters: Dict[str, int] = field(default_factory=dict)

    def get_or_create_token(
        self, value: str, sensitive_type: str
    ) -> str:
        """Get existing token or create a new one for the value."""
        if value in self._reverse_map:
            return self._reverse_map[value]

        counter = self._counters.get(sensitive_type, 0) + 1
        self._counters[sensitive_type] = counter

        type_label = sensitive_type.upper()
        token = f"[{type_label}_{counter:04d}]"

        self._token_map[token] = value
        self._reverse_map[value] = token
        return token

    def resolve_token(self, token: str) -> Optional[str]:
        """Resolve a token back to its real value."""
        return self._token_map.get(token)

    def resolve_all_tokens(self, text: str) -> str:
        """Replace all tokens in text with real values.

        Used for final delivery to user.
        """
        result = text
        for token, real_value in self._token_map.items():
            result = result.replace(token, real_value)
        return result

    @property
    def token_count(self) -> int:
        """Number of unique tokens in this session."""
        return len(self._token_map)

    def clear(self):
        """Clear all mappings."""
        self._token_map.clear()
        self._reverse_map.clear()
        self._counters.clear()


class DataMasker:
    """Applies masking to SQL query result rows.

    Sits between the SQL execution layer and the LLM context,
    intercepting result data to mask sensitive columns.
    """

    def __init__(self):
        # table_name.column_name → ColumnMaskingConfig
        self._configs: Dict[str, ColumnMaskingConfig] = {}
        # Session-level token contexts
        self._sessions: Dict[str, MaskingContext] = {}

    def configure_column(self, config: ColumnMaskingConfig):
        """Register masking config for a column."""
        key = f"{config.table_name}.{config.column_name}"
        self._configs[key] = config

    def configure_columns(self, configs: List[ColumnMaskingConfig]):
        """Register multiple column configs at once."""
        for cfg in configs:
            self.configure_column(cfg)

    def remove_column(self, table_name: str, column_name: str):
        """Remove masking config for a column."""
        key = f"{table_name}.{column_name}"
        self._configs.pop(key, None)

    def get_session_context(self, session_id: str) -> MaskingContext:
        """Get or create a masking context for a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = MaskingContext(session_id=session_id)
        return self._sessions[session_id]

    def clear_session(self, session_id: str):
        """Clear the masking context for a session."""
        self._sessions.pop(session_id, None)

    def mask_results(
        self,
        columns: Tuple,
        rows: List,
        *,
        table_name: Optional[str] = None,
        session_id: Optional[str] = None,
        mode_override: Optional[str] = None,
    ) -> Tuple[Tuple, List]:
        """Mask sensitive columns in SQL query results.

        Args:
            columns: Column name tuple from query result.
            rows: Data rows from query result.
            table_name: The table being queried (for config lookup).
                If None, tries to match column names across all configs.
            session_id: Session ID for tokenization mode.
            mode_override: Override masking mode for all columns.

        Returns:
            (columns, masked_rows) — same structure, masked values.
        """
        if not rows or not columns:
            return columns, rows

        # Find which column indices need masking
        col_names = [str(c) for c in columns] if columns else []
        mask_plan: Dict[int, ColumnMaskingConfig] = {}

        for idx, col_name in enumerate(col_names):
            config = self._find_config(table_name, col_name)
            if config:
                mask_plan[idx] = config

        if not mask_plan:
            return columns, rows

        # Get session context for token mode
        ctx = None
        if session_id:
            ctx = self.get_session_context(session_id)

        # Apply masking
        masked_rows = []
        for row in rows:
            if not isinstance(row, (list, tuple)):
                masked_rows.append(row)
                continue

            masked_row = list(row)
            for idx, config in mask_plan.items():
                if idx < len(masked_row):
                    mode = mode_override or config.mode
                    masked_row[idx] = self._mask_value(
                        masked_row[idx], config.sensitive_type, mode, ctx
                    )
            masked_rows.append(masked_row)

        return columns, masked_rows

    def resolve_tokens_in_text(
        self, text: str, session_id: str
    ) -> str:
        """Replace all tokens in text with real values.

        Call this on the Agent's final response before delivering to the user.
        """
        ctx = self._sessions.get(session_id)
        if not ctx:
            return text
        return ctx.resolve_all_tokens(text)

    def get_masked_columns(
        self, table_name: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Get list of currently configured masked columns."""
        results = []
        for key, config in self._configs.items():
            if table_name and config.table_name != table_name:
                continue
            results.append({
                "table_name": config.table_name,
                "column_name": config.column_name,
                "sensitive_type": config.sensitive_type,
                "mode": config.mode,
            })
        return results

    def _find_config(
        self, table_name: Optional[str], col_name: str
    ) -> Optional[ColumnMaskingConfig]:
        """Find masking config for a column."""
        if table_name:
            key = f"{table_name}.{col_name}"
            if key in self._configs:
                return self._configs[key]

        # Try matching by column name across all tables
        for key, config in self._configs.items():
            if config.column_name == col_name:
                return config

        return None

    def _mask_value(
        self,
        value: Any,
        sensitive_type: str,
        mode: str,
        ctx: Optional[MaskingContext],
    ) -> Any:
        """Mask a single value."""
        if value is None:
            return None

        str_val = str(value)
        if not str_val or str_val == "None":
            return value

        if mode == MaskingMode.TOKEN and ctx:
            return ctx.get_or_create_token(str_val, sensitive_type)

        if mode == MaskingMode.NONE:
            return value

        # Default: partial masking
        return self._partial_mask(str_val, sensitive_type)

    @staticmethod
    def _partial_mask(value: str, sensitive_type: str) -> str:
        """Apply format-preserving partial masking.

        Preserves a recognizable prefix/suffix while hiding the middle,
        so the model understands the data type without seeing the full value.
        """
        length = len(value)

        if sensitive_type == SensitiveType.PHONE.value:
            # 13812345678 → 138****5678
            if length >= 7:
                return value[:3] + "****" + value[-4:]
            return "****"

        if sensitive_type == SensitiveType.EMAIL.value:
            # user@example.com → u***@example.com
            at_idx = value.find("@")
            if at_idx > 1:
                return value[0] + "***" + value[at_idx:]
            return "***@***"

        if sensitive_type == SensitiveType.ID_CARD.value:
            # 310101199001011234 → 310101********1234
            if length >= 10:
                return value[:6] + "****" * 2 + value[-4:]
            return "****"

        if sensitive_type == SensitiveType.BANK_CARD.value:
            # 6222021234561234567 → 6222****4567
            if length >= 8:
                return value[:4] + "****" + value[-4:]
            return "****"

        if sensitive_type == SensitiveType.ADDRESS.value:
            # 上海市浦东新区张江路100号 → 上海市浦东新区****
            if length > 6:
                # Keep first ~40%, mask rest
                keep = max(3, length * 2 // 5)
                return value[:keep] + "****"
            return "****"

        if sensitive_type == SensitiveType.NAME.value:
            # 张三 → 张* , 张三丰 → 张*丰
            if length == 1:
                return "*"
            if length == 2:
                return value[0] + "*"
            return value[0] + "*" * (length - 2) + value[-1]

        if sensitive_type in (
            SensitiveType.PASSWORD.value, SensitiveType.TOKEN.value
        ):
            # Full mask — never show these
            return "******"

        if sensitive_type == SensitiveType.IP_ADDRESS.value:
            # 192.168.1.100 → 192.168.*.*
            parts = value.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.*.*"
            return "****"

        # Generic: keep first and last char
        if length <= 2:
            return "*" * length
        return value[0] + "*" * (length - 2) + value[-1]


# Module-level singleton
_masker_instance: Optional[DataMasker] = None


def get_data_masker() -> DataMasker:
    """Get the module-level DataMasker singleton."""
    global _masker_instance
    if _masker_instance is None:
        _masker_instance = DataMasker()
    return _masker_instance
