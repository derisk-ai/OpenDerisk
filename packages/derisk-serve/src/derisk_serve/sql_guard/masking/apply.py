"""Unified masking entry point for SQL execution sites.

Every place that runs SQL and hands the result to the LLM or the user
should route the result through :func:`mask_run_result` instead of calling
the masker directly. This guarantees consistent, datasource-scoped,
restart-safe masking across all data exits (agent ``execute_sql``, table
preview, chart rendering, sample-data collection, ...).
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def mask_run_result(
    datasource_id: Optional[int],
    columns,
    rows: List,
    *,
    table_name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Tuple[list, List, List[str]]:
    """Apply privacy masking to a ``connector.run()`` style result set.

    Args:
        datasource_id: Datasource the rows came from. Used to scope which
            masking rules apply (lazily loaded — restart-safe). May be None,
            in which case only globally-registered rules apply.
        columns: Column names (list/tuple).
        rows: Data rows (list of lists/tuples).
        table_name: Table name, when known, for precise table.column lookup.
        session_id: Conversation/session id for tokenization mode.

    Returns:
        (columns, masked_rows, masked_column_names). On any failure the
        original columns/rows are returned unchanged with an empty masked
        list, so masking can never break a query path.
    """
    if not rows or not columns:
        return columns, rows, []
    try:
        from derisk_serve.sql_guard.masking.masker import get_data_masker

        masker = get_data_masker()
        return masker.mask_results_ex(
            columns,
            rows,
            datasource_id=datasource_id,
            table_name=table_name,
            session_id=session_id,
        )
    except ImportError:
        return columns, rows, []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Data masking failed, returning unmasked result: {e}")
        return columns, rows, []
