"""
Authorization Module - Unified Tool Authorization System

This module provides the complete authorization system:
- Model: Permission rules, rulesets, and configurations
- Cache: Authorization caching with TTL
- RiskAssessor: Runtime risk assessment
- Engine: Authorization decision engine

Version: 2.0
"""

from .model import (
    PermissionAction,
    AuthorizationMode,
    LLMJudgmentPolicy,
    PermissionRule,
    PermissionRuleset,
    AuthorizationConfig,
    # Predefined configs
    STRICT_CONFIG,
    MODERATE_CONFIG,
    PERMISSIVE_CONFIG,
    AUTONOMOUS_CONFIG,
)

from .cache import (
    AuthorizationCache,
    get_authorization_cache,
)

from .risk_assessor import (
    RiskAssessor,
    RiskAssessment,
)

from .engine import (
    AuthorizationDecision,
    AuthorizationContext,
    AuthorizationResult,
    AuthorizationEngine,
    get_authorization_engine,
)

__all__ = [
    # Model
    "PermissionAction",
    "AuthorizationMode",
    "LLMJudgmentPolicy",
    "PermissionRule",
    "PermissionRuleset",
    "AuthorizationConfig",
    "STRICT_CONFIG",
    "MODERATE_CONFIG",
    "PERMISSIVE_CONFIG",
    "AUTONOMOUS_CONFIG",
    # Cache
    "AuthorizationCache",
    "get_authorization_cache",
    # Risk Assessor
    "RiskAssessor",
    "RiskAssessment",
    # Engine
    "AuthorizationDecision",
    "AuthorizationContext",
    "AuthorizationResult",
    "AuthorizationEngine",
    "get_authorization_engine",
]
