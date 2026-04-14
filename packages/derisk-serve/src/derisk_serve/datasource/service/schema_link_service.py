"""Schema Linking service — dynamic table discovery based on Spec.

Provides intelligent table recommendation based on user questions,
using the stored Spec data (table names, column names, comments,
relationships) to match relevant tables.
"""

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from derisk_serve.datasource.manages.db_spec_db import DbSpecDao
from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

logger = logging.getLogger(__name__)


@dataclass
class TableRecommendation:
    """A recommended table with match details."""

    table_name: str
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    group: str = "default"
    row_count: Optional[int] = None  # 表行数，用于过滤空表


@dataclass
class TableRelation:
    """A relationship between two tables."""

    from_table: str
    to_table: str
    relation_type: str  # foreign_key / naming_convention
    column: str = ""


class SchemaLinkService:
    """Dynamic Schema Linking service based on Spec data.

    Provides table recommendation by matching user questions against
    stored Spec metadata. Designed to work as a helper for the Agent's
    table selection process, not as a mandatory preprocessing step.
    """

    def __init__(self):
        self._db_spec_dao = DbSpecDao()
        self._table_spec_dao = TableSpecDao()
        # In-memory cache: datasource_id → index
        self._index_cache: Dict[int, Dict] = {}

    def suggest_tables(
        self,
        datasource_id: int,
        question: str,
        max_results: int = 10,
    ) -> List[TableRecommendation]:
        """Recommend tables relevant to a user question.

        Matching strategy (by priority):
        1. Exact match: table names mentioned directly in the question
        2. Column match: keywords in question matching column names
        3. Comment match: keywords matching table/column comments
        4. Relation expansion: add related tables via foreign keys
        5. Group affinity: same-group tables get a small bonus

        Args:
            datasource_id: The datasource ID.
            question: The user's natural language question.
            max_results: Maximum number of tables to recommend.

        Returns:
            Sorted list of TableRecommendation, highest score first.
        """
        index = self._get_or_build_index(datasource_id)
        if not index:
            return []

        # Tokenize question into keywords
        keywords = self._extract_keywords(question)
        if not keywords:
            return []

        scores: Dict[str, float] = defaultdict(float)
        reasons: Dict[str, List[str]] = defaultdict(list)

        table_names = set(index.get("tables", {}).keys())

        # Strategy 1: Exact table name match
        for kw in keywords:
            kw_lower = kw.lower()
            for tname in table_names:
                if kw_lower == tname.lower():
                    scores[tname] += 10.0
                    reasons[tname].append(f"exact match: '{kw}'")
                elif kw_lower in tname.lower():
                    scores[tname] += 5.0
                    reasons[tname].append(f"partial match: '{kw}' in '{tname}'")

        # Strategy 2: Column name match
        col_index = index.get("column_to_tables", {})
        for kw in keywords:
            kw_lower = kw.lower()
            for col_name, col_tables in col_index.items():
                if kw_lower == col_name.lower() or kw_lower in col_name.lower():
                    for tname in col_tables:
                        scores[tname] += 3.0
                        reasons[tname].append(
                            f"column match: '{kw}' → {tname}.{col_name}"
                        )

        # Strategy 3: Comment match
        comment_index = index.get("keyword_to_tables", {})
        for kw in keywords:
            kw_lower = kw.lower()
            for comment_kw, ct_tables in comment_index.items():
                if kw_lower in comment_kw.lower():
                    for tname in ct_tables:
                        scores[tname] += 2.0
                        reasons[tname].append(
                            f"comment match: '{kw}' in '{comment_kw}'"
                        )

        # Strategy 4: Relation expansion
        relations = index.get("relations", [])
        matched_tables = {t for t, s in scores.items() if s >= 3.0}
        for rel in relations:
            if rel["from_table"] in matched_tables and rel["to_table"] not in scores:
                scores[rel["to_table"]] += 1.5
                reasons[rel["to_table"]].append(
                    f"related via {rel['type']}: {rel['from_table']}.{rel.get('column', '')}"
                )
            elif rel["to_table"] in matched_tables and rel["from_table"] not in scores:
                scores[rel["from_table"]] += 1.5
                reasons[rel["from_table"]].append(
                    f"related via {rel['type']}: ← {rel['to_table']}"
                )

        # Strategy 5: Group affinity
        table_groups = index.get("table_groups", {})
        matched_groups = {
            table_groups.get(t, "default") for t in matched_tables
        }
        for tname, group in table_groups.items():
            if group in matched_groups and tname in scores:
                scores[tname] += 0.5

        # Sort and return
        table_row_counts = index.get("table_row_counts", {})
        recommendations = []
        for tname, score in sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        )[:max_results]:
            recommendations.append(
                TableRecommendation(
                    table_name=tname,
                    score=score,
                    reasons=reasons.get(tname, []),
                    group=table_groups.get(tname, "default"),
                    row_count=table_row_counts.get(tname),  # 添加行数信息
                )
            )

        return recommendations

    def build_table_index(self, datasource_id: int) -> Dict:
        """Build a search index from Spec data.

        Returns:
            Index dict with keys:
            - tables: {table_name: {comment, columns, group, row_count}}
            - column_to_tables: {column_name: [table_name, ...]}
            - keyword_to_tables: {keyword: [table_name, ...]}
            - relations: [{from_table, to_table, type, column}]
            - table_groups: {table_name: group_name}
            - table_row_counts: {table_name: row_count} - 用于过滤空表
        """
        table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)
        db_spec = self._db_spec_dao.get_by_datasource_id(datasource_id)

        tables = {}
        column_to_tables: Dict[str, Set[str]] = defaultdict(set)
        keyword_to_tables: Dict[str, Set[str]] = defaultdict(set)
        table_groups: Dict[str, str] = {}
        table_row_counts: Dict[str, int] = {}  # 新增：记录表的行数

        # Parse db spec for group info
        if db_spec and db_spec.get("spec_content"):
            try:
                spec_entries = json.loads(db_spec["spec_content"])
                for entry in spec_entries:
                    tname = entry.get("table_name", "")
                    if tname:
                        table_groups[tname] = entry.get("group", "default")
            except (json.JSONDecodeError, TypeError):
                pass

        for spec in table_specs:
            tname = spec.get("table_name", "")
            if not tname:
                continue

            # 新增：过滤空表（row_count = 0 或 None）
            row_count = spec.get("row_count", 0)
            if row_count is None:
                row_count = 0
            if row_count == 0:
                logger.debug(f"[SchemaLink] Skipping empty table: {tname} (row_count=0)")
                continue

            # 记录行数
            table_row_counts[tname] = row_count

            comment = spec.get("table_comment", "") or ""
            columns = spec.get("columns", []) or []
            col_names = [c.get("name", "") for c in columns]

            tables[tname] = {
                "comment": comment,
                "columns": col_names,
                "group": table_groups.get(tname, "default"),
                "row_count": row_count,  # 新增：行数信息
            }

            # Column index
            for col_name in col_names:
                if col_name:
                    column_to_tables[col_name].add(tname)

            # Keyword index from comments
            if comment:
                for word in self._tokenize_comment(comment):
                    keyword_to_tables[word].add(tname)

            # Column comments
            for col in columns:
                col_comment = col.get("comment", "")
                if col_comment:
                    for word in self._tokenize_comment(col_comment):
                        keyword_to_tables[word].add(tname)

        # Detect relations
        relations = self._detect_relations_from_specs(table_specs, set(tables.keys()))

        # Convert sets to lists for JSON serialization
        index = {
            "tables": tables,
            "column_to_tables": {k: list(v) for k, v in column_to_tables.items()},
            "keyword_to_tables": {k: list(v) for k, v in keyword_to_tables.items()},
            "relations": relations,
            "table_groups": table_groups,
            "table_row_counts": table_row_counts,  # 新增：行数映射
        }

        logger.info(
            f"[SchemaLink] Built index for datasource {datasource_id}: "
            f"{len(tables)} tables (filtered empty tables)"
        )

        # Cache
        self._index_cache[datasource_id] = index
        return index

    def detect_relations(self, datasource_id: int) -> List[Dict]:
        """Detect table relations from Spec data."""
        table_specs = self._table_spec_dao.get_all_by_datasource(datasource_id)
        all_tables = set()
        for spec in table_specs:
            tname = spec.get("table_name", "")
            if tname:
                all_tables.add(tname)
        return self._detect_relations_from_specs(table_specs, all_tables)

    def invalidate_cache(self, datasource_id: int):
        """Invalidate the cached index for a datasource."""
        self._index_cache.pop(datasource_id, None)

    def _get_or_build_index(self, datasource_id: int) -> Dict:
        """Get cached index or build a new one."""
        if datasource_id in self._index_cache:
            return self._index_cache[datasource_id]
        return self.build_table_index(datasource_id)

    def _detect_relations_from_specs(
        self, table_specs: List[Dict], all_tables: Set[str]
    ) -> List[Dict]:
        """Detect relations from DDL foreign keys and naming conventions."""
        relations = []
        seen = set()

        for spec in table_specs:
            tname = spec.get("table_name", "")
            if not tname:
                continue

            # Method 1: Foreign keys from DDL
            ddl = spec.get("create_ddl", "") or ""
            fk_matches = re.findall(
                r"FOREIGN\s+KEY.*?REFERENCES\s+`?(\w+)`?", ddl, re.IGNORECASE
            )
            for ref_table in fk_matches:
                key = (tname, ref_table, "foreign_key")
                if key not in seen:
                    seen.add(key)
                    relations.append(
                        {
                            "from_table": tname,
                            "to_table": ref_table,
                            "type": "foreign_key",
                        }
                    )

            # Method 2: Naming convention (xxx_id → xxx / xxxs table)
            columns = spec.get("columns", []) or []
            for col in columns:
                col_name = col.get("name", "")
                if col_name.endswith("_id") and col_name != "id":
                    candidate = col_name[:-3]
                    for t in all_tables:
                        if t == tname:
                            continue
                        if t.lower() == candidate.lower() or t.lower() == (
                            candidate + "s"
                        ).lower():
                            key = (tname, t, "naming_convention")
                            if key not in seen:
                                seen.add(key)
                                relations.append(
                                    {
                                        "from_table": tname,
                                        "to_table": t,
                                        "type": "naming_convention",
                                        "column": col_name,
                                    }
                                )

        return relations

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract meaningful keywords from text.

        Removes common stop words and short tokens.
        """
        # Split on non-alphanumeric (supports CJK by keeping Unicode word chars)
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())

        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "of", "in", "to", "for", "with", "on", "at", "by", "from",
            "and", "or", "not", "but", "if", "then", "than", "so",
            "what", "which", "who", "whom", "this", "that", "these",
            "those", "it", "its", "my", "your", "our", "their",
            "all", "each", "every", "some", "any", "no", "how",
            "me", "i", "we", "you", "he", "she", "they",
            # Chinese stop words
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
            "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
            "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
            "吗", "把", "让", "给", "从", "帮", "帮我", "查", "查询",
            "分析", "统计", "计算", "显示", "列出", "找出", "请",
        }

        return [t for t in tokens if t not in stop_words and len(t) >= 2]

    @staticmethod
    def _tokenize_comment(comment: str) -> List[str]:
        """Tokenize a comment into keywords."""
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", comment.lower())
        return [t for t in tokens if len(t) >= 2]
