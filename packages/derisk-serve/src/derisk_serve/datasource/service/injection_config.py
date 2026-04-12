"""Configuration constants for database table injection optimization.

This module defines thresholds and strategies for tiered table injection
to optimize prompt size for databases with different table counts.
"""

import os
from typing import Dict, Any

# Table count thresholds for tiered injection strategy
TABLE_INJECTION_THRESHOLDS = {
    # Small DB: Full table list with summaries
    "SMALL_DB_THRESHOLD": int(os.getenv("INJECTION_SMALL_DB_THRESHOLD", 100)),
    # Medium DB: Compact table name list (truncated)
    "MEDIUM_DB_THRESHOLD": int(os.getenv("INJECTION_MEDIUM_DB_THRESHOLD", 500)),
}

# Injection modes
INJECTION_MODE_SMALL = "small"      # <100: full list with summaries
INJECTION_MODE_MEDIUM = "medium"    # 100-500: compact name-only list
INJECTION_MODE_LARGE = "large"      # >500: stats only + tool guidance

# Maximum tables to show in medium mode before truncation
MAX_MEDIUM_TABLE_DISPLAY = int(os.getenv("INJECTION_MAX_MEDIUM_DISPLAY", 200))

# Prompt template for large DB guidance
LARGE_DB_GUIDANCE_TEMPLATE = """
<workflow_for_large_db>
由于数据库表数量较多（{total_tables} 张表），表列表未注入到提示词中。
请按以下流程操作：

1. **使用 search_tables 工具** - 根据问题语义搜索相关表
   ```
   search_tables(db_name="{db_name}", question="你的问题")
   ```

2. **使用 list_tables 工具** - 查看完整表列表或按分组筛选
   ```
   list_tables(db_name="{db_name}", group="分组名", page=1)
   ```

3. **使用 get_table_spec 工具** - 获取表的详细结构（列、类型、注释、索引）
   ```
   get_table_spec(db_name="{db_name}", table_names="表名1,表名2")
   ```

推荐工作流：
```
search_tables -> get_table_spec -> execute_sql
```
</workflow_for_large_db>
"""


def get_injection_mode(table_count: int) -> str:
    """Determine injection mode based on table count.

    Args:
        table_count: Number of tables in the database

    Returns:
        Injection mode: "small", "medium", or "large"
    """
    small_threshold = TABLE_INJECTION_THRESHOLDS["SMALL_DB_THRESHOLD"]
    medium_threshold = TABLE_INJECTION_THRESHOLDS["MEDIUM_DB_THRESHOLD"]

    if table_count < small_threshold:
        return INJECTION_MODE_SMALL
    elif table_count < medium_threshold:
        return INJECTION_MODE_MEDIUM
    else:
        return INJECTION_MODE_LARGE


def format_group_stats(groups: Dict[str, int], max_display: int = 5) -> str:
    """Format group statistics for display.

    Args:
        groups: Dict of group_name -> table_count
        max_display: Maximum number of groups to display

    Returns:
        Formatted string like "sales(150), orders(120), ..."
    """
    if not groups:
        return "无分组"

    sorted_groups = sorted(groups.items(), key=lambda x: -x[1])
    displayed = sorted_groups[:max_display]

    result = ", ".join([f"{name}({count})" for name, count in displayed])

    if len(sorted_groups) > max_display:
        remaining = len(sorted_groups) - max_display
        result += f", ... ({remaining} 更多分组)"

    return result