"""SQL Guard API endpoints."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk_serve.core import Result

from .schemas import (
    AuditLogResponse,
    AuditStatsResponse,
    GuardConfigResponse,
    GuardConfigUpdateRequest,
    RuleInfo,
    RuleUpdateRequest,
    SensitiveColumnCreateRequest,
    SensitiveColumnDetectRequest,
    SensitiveColumnResponse,
    SensitiveColumnUpdateRequest,
    SQLCheckRequest,
    SQLCheckResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()
get_bearer_token = HTTPBearer(auto_error=False)


def _get_guard():
    """Get the SQLGuard singleton."""
    from derisk_serve.sql_guard.guard import get_sql_guard

    return get_sql_guard()


def _get_audit_dao():
    """Get the audit DAO."""
    from derisk_serve.sql_guard.audit.dao import SqlAuditLogDao

    return SqlAuditLogDao()


@router.get(
    "/sql-guard/config",
    response_model=Result[GuardConfigResponse],
)
async def get_config() -> Result[GuardConfigResponse]:
    """Get current SQL Guard configuration."""
    guard = _get_guard()
    cfg = guard.config
    return Result.succ(
        GuardConfigResponse(
            enabled=cfg.enabled,
            default_mode=cfg.default_mode,
            audit_enabled=cfg.audit_enabled,
            default_select_limit=cfg.default_select_limit,
            max_select_limit=cfg.max_select_limit,
            disabled_rules=cfg.disabled_rules,
        )
    )


@router.put(
    "/sql-guard/config",
    response_model=Result[GuardConfigResponse],
)
async def update_config(
    request: GuardConfigUpdateRequest,
) -> Result[GuardConfigResponse]:
    """Update SQL Guard configuration."""
    guard = _get_guard()
    cfg = guard.config

    if request.enabled is not None:
        cfg.enabled = request.enabled
    if request.default_mode is not None:
        cfg.default_mode = request.default_mode
    if request.audit_enabled is not None:
        cfg.audit_enabled = request.audit_enabled
    if request.default_select_limit is not None:
        cfg.default_select_limit = request.default_select_limit
    if request.max_select_limit is not None:
        cfg.max_select_limit = request.max_select_limit
    if request.disabled_rules is not None:
        cfg.disabled_rules = request.disabled_rules

    guard.update_config(cfg)

    return Result.succ(
        GuardConfigResponse(
            enabled=cfg.enabled,
            default_mode=cfg.default_mode,
            audit_enabled=cfg.audit_enabled,
            default_select_limit=cfg.default_select_limit,
            max_select_limit=cfg.max_select_limit,
            disabled_rules=cfg.disabled_rules,
        )
    )


@router.post(
    "/sql-guard/check",
    response_model=Result[SQLCheckResponse],
)
async def check_sql(request: SQLCheckRequest) -> Result[SQLCheckResponse]:
    """Manually check SQL against guard rules (for debugging/testing)."""
    guard = _get_guard()
    result = guard.check(
        request.sql,
        user_id=request.user_id,
        datasource_id=request.datasource_id,
        db_name=request.db_name,
        mode=request.mode,
    )
    return Result.succ(
        SQLCheckResponse(
            allowed=result.allowed,
            risk_level=result.risk_level,
            risk_score=result.risk_score,
            blocked_rules=result.blocked_rules,
            warnings=result.warnings,
            rewritten_sql=result.rewritten_sql,
            sql_type=result.sql_type,
        )
    )


@router.get(
    "/sql-guard/rules",
    response_model=Result[List[RuleInfo]],
)
async def get_rules() -> Result[List[RuleInfo]]:
    """Get all registered guard rules."""
    guard = _get_guard()
    rules = guard.get_rules()
    return Result.succ([RuleInfo(**r) for r in rules])


@router.put(
    "/sql-guard/rules/{rule_name}",
    response_model=Result[RuleInfo],
)
async def update_rule(
    rule_name: str,
    request: RuleUpdateRequest,
) -> Result[RuleInfo]:
    """Enable or disable a specific rule."""
    guard = _get_guard()
    cfg = guard.config

    if request.enabled:
        cfg.disabled_rules = [r for r in cfg.disabled_rules if r != rule_name]
    else:
        if rule_name not in cfg.disabled_rules:
            cfg.disabled_rules.append(rule_name)

    guard.update_config(cfg)

    # Find the rule info
    for r in guard.get_rules():
        if r["name"] == rule_name:
            return Result.succ(RuleInfo(**r))

    return Result.succ(
        RuleInfo(name=rule_name, description="", enabled=request.enabled)
    )


@router.get(
    "/sql-guard/audit",
    response_model=Result[List[AuditLogResponse]],
)
async def get_audit_logs(
    user_id: Optional[str] = Query(None),
    datasource_id: Optional[int] = Query(None),
    session_id: Optional[str] = Query(None),
    check_result: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Result[List[AuditLogResponse]]:
    """Query SQL audit logs with filters."""
    dao = _get_audit_dao()
    logs = dao.list(
        user_id=user_id,
        datasource_id=datasource_id,
        session_id=session_id,
        check_result=check_result,
        risk_level=risk_level,
        page=page,
        page_size=page_size,
    )
    return Result.succ([AuditLogResponse(**log) for log in logs])


@router.get(
    "/sql-guard/audit/stats",
    response_model=Result[AuditStatsResponse],
)
async def get_audit_stats(
    datasource_id: Optional[int] = Query(None),
) -> Result[AuditStatsResponse]:
    """Get audit statistics."""
    dao = _get_audit_dao()
    stats = dao.get_stats(datasource_id=datasource_id)
    return Result.succ(AuditStatsResponse(**stats))


# ============================================================
# Sensitive Column Masking Endpoints
# ============================================================


def _get_sensitive_dao():
    """Get the SensitiveColumnDao."""
    from derisk_serve.sql_guard.masking.config_db import SensitiveColumnDao

    return SensitiveColumnDao()


@router.get(
    "/sql-guard/masking/{datasource_id}/columns",
    response_model=Result[List[SensitiveColumnResponse]],
)
async def get_sensitive_columns(
    datasource_id: int,
) -> Result[List[SensitiveColumnResponse]]:
    """Get all sensitive column configs for a datasource."""
    dao = _get_sensitive_dao()
    configs = dao.get_by_datasource(datasource_id)
    return Result.succ([SensitiveColumnResponse(**c) for c in configs])


@router.post(
    "/sql-guard/masking/{datasource_id}/columns",
    response_model=Result[SensitiveColumnResponse],
)
async def add_sensitive_column(
    datasource_id: int,
    request: SensitiveColumnCreateRequest,
) -> Result[SensitiveColumnResponse]:
    """Manually add a sensitive column config."""
    dao = _get_sensitive_dao()
    result = dao.upsert(
        datasource_id=datasource_id,
        table_name=request.table_name,
        column_name=request.column_name,
        data={
            "sensitive_type": request.sensitive_type,
            "masking_mode": request.masking_mode,
            "confidence": None,
            "source": "manual",
            "enabled": 1,
        },
    )

    # Reload masker config
    _reload_masker_config(datasource_id)

    return Result.succ(SensitiveColumnResponse(**result))


@router.put(
    "/sql-guard/masking/{datasource_id}/columns/{table_name}/{column_name}",
    response_model=Result[SensitiveColumnResponse],
)
async def update_sensitive_column(
    datasource_id: int,
    table_name: str,
    column_name: str,
    request: SensitiveColumnUpdateRequest,
) -> Result[SensitiveColumnResponse]:
    """Update a sensitive column config."""
    dao = _get_sensitive_dao()
    data = {}
    if request.sensitive_type is not None:
        data["sensitive_type"] = request.sensitive_type
    if request.masking_mode is not None:
        data["masking_mode"] = request.masking_mode
    if request.enabled is not None:
        data["enabled"] = 1 if request.enabled else 0

    if not data:
        # Nothing to update, return current
        configs = dao.get_by_datasource(datasource_id)
        for c in configs:
            if c["table_name"] == table_name and c["column_name"] == column_name:
                return Result.succ(SensitiveColumnResponse(**c))
        return Result.failed(msg="Column config not found")

    result = dao.upsert(
        datasource_id=datasource_id,
        table_name=table_name,
        column_name=column_name,
        data=data,
    )

    _reload_masker_config(datasource_id)
    return Result.succ(SensitiveColumnResponse(**result))


@router.put(
    "/sql-guard/masking/{datasource_id}/columns/{table_name}/{column_name}/toggle",
    response_model=Result[str],
)
async def toggle_sensitive_column(
    datasource_id: int,
    table_name: str,
    column_name: str,
    enabled: bool = Query(...),
) -> Result[str]:
    """Enable or disable masking for a specific column."""
    dao = _get_sensitive_dao()
    dao.set_enabled(datasource_id, table_name, column_name, enabled)
    _reload_masker_config(datasource_id)
    return Result.succ("OK")


@router.post(
    "/sql-guard/masking/{datasource_id}/detect",
    response_model=Result[List[SensitiveColumnResponse]],
)
async def detect_sensitive_columns(
    datasource_id: int,
    request: Optional[SensitiveColumnDetectRequest] = None,
) -> Result[List[SensitiveColumnResponse]]:
    """Trigger auto-detection of sensitive columns for a datasource."""
    from derisk_serve.sql_guard.masking.config_db import SensitiveColumnDao
    from derisk_serve.sql_guard.masking.detector import SensitiveColumnDetector

    from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

    detector = SensitiveColumnDetector()
    dao = SensitiveColumnDao()
    table_spec_dao = TableSpecDao()

    table_specs = table_spec_dao.get_all_by_datasource(datasource_id)

    # Filter to requested tables if specified
    if request and request.table_names:
        table_specs = [
            s for s in table_specs
            if s.get("table_name") in request.table_names
        ]

    detections = detector.detect_batch(table_specs)
    results = []

    for table_name, columns in detections.items():
        for col_info in columns:
            saved = dao.upsert(
                datasource_id=datasource_id,
                table_name=col_info.table_name,
                column_name=col_info.column_name,
                data={
                    "sensitive_type": col_info.sensitive_type,
                    "masking_mode": (
                        "mask" if col_info.masking_strategy == "full"
                        else col_info.masking_strategy
                    ),
                    "confidence": col_info.confidence,
                    "source": "auto",
                    "enabled": 1,
                },
            )
            results.append(SensitiveColumnResponse(**saved))

    _reload_masker_config(datasource_id)
    return Result.succ(results)


def _reload_masker_config(datasource_id: int) -> None:
    """Reload masking configs into the DataMasker singleton."""
    try:
        from derisk_serve.sql_guard.masking.config_db import SensitiveColumnDao
        from derisk_serve.sql_guard.masking.masker import (
            ColumnMaskingConfig,
            get_data_masker,
        )

        dao = SensitiveColumnDao()
        masker = get_data_masker()
        configs = dao.get_enabled_by_datasource(datasource_id)

        for cfg in configs:
            masker.configure_column(ColumnMaskingConfig(
                table_name=cfg["table_name"],
                column_name=cfg["column_name"],
                sensitive_type=cfg["sensitive_type"],
                mode=cfg.get("masking_mode", "mask"),
            ))
    except Exception as e:
        logger.warning(f"Failed to reload masker config: {e}")
