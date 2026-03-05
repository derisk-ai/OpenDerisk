"""
Authorization Engine - Unified Tool Authorization System

This module implements the core authorization engine:
- AuthorizationDecision: Decision types
- AuthorizationContext: Context for authorization checks
- AuthorizationResult: Result of authorization check
- AuthorizationEngine: Main engine class

Version: 2.0
"""

import time
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from .model import (
    PermissionAction,
    AuthorizationMode,
    AuthorizationConfig,
    LLMJudgmentPolicy,
)
from .cache import AuthorizationCache, get_authorization_cache
from .risk_assessor import RiskAssessor, RiskAssessment
from ..tools.metadata import RiskLevel

logger = logging.getLogger(__name__)


class AuthorizationDecision(str, Enum):
    """Authorization decision types."""
    GRANTED = "granted"                     # Authorization granted
    DENIED = "denied"                       # Authorization denied
    NEED_CONFIRMATION = "need_confirmation" # Needs user confirmation
    NEED_LLM_JUDGMENT = "need_llm_judgment" # Needs LLM judgment
    CACHED = "cached"                       # Decision from cache


@dataclass
class AuthorizationContext:
    """
    Context for an authorization check.
    
    Contains all information needed to make an authorization decision.
    """
    session_id: str
    tool_name: str
    arguments: Dict[str, Any]
    tool_metadata: Any = None
    
    # Optional context
    user_id: Optional[str] = None
    agent_name: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    
    # Additional context
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "user_id": self.user_id,
            "agent_name": self.agent_name,
            "timestamp": self.timestamp,
            "extra": self.extra,
        }


@dataclass
class AuthorizationResult:
    """
    Result of an authorization check.
    
    Contains the decision and all supporting information.
    """
    decision: AuthorizationDecision
    action: PermissionAction
    reason: str
    
    # Cache information
    cached: bool = False
    cache_key: Optional[str] = None
    
    # User message (for confirmation requests)
    user_message: Optional[str] = None
    
    # Risk assessment
    risk_assessment: Optional[RiskAssessment] = None
    
    # LLM judgment result
    llm_judgment: Optional[Dict[str, Any]] = None
    
    # Timing
    duration_ms: float = 0.0
    
    @property
    def is_granted(self) -> bool:
        """Check if authorization was granted."""
        return self.decision in (
            AuthorizationDecision.GRANTED,
            AuthorizationDecision.CACHED,
        ) and self.action == PermissionAction.ALLOW
    
    @property
    def needs_user_input(self) -> bool:
        """Check if user input is needed."""
        return self.decision == AuthorizationDecision.NEED_CONFIRMATION
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "decision": self.decision.value,
            "action": self.action.value if isinstance(self.action, Enum) else self.action,
            "reason": self.reason,
            "cached": self.cached,
            "cache_key": self.cache_key,
            "user_message": self.user_message,
            "risk_assessment": self.risk_assessment.to_dict() if self.risk_assessment else None,
            "llm_judgment": self.llm_judgment,
            "duration_ms": self.duration_ms,
        }


# Type for user confirmation callback
UserConfirmationCallback = Callable[
    [AuthorizationContext, RiskAssessment],
    Awaitable[bool]
]

# Type for LLM judgment callback
LLMJudgmentCallback = Callable[
    [AuthorizationContext, RiskAssessment, str],
    Awaitable[Dict[str, Any]]
]


class AuthorizationEngine:
    """
    Authorization Engine - Core authorization decision maker.
    
    Handles the complete authorization flow:
    1. Check cache for existing decision
    2. Get effective permission action from config
    3. Perform risk assessment
    4. Apply LLM judgment (if enabled)
    5. Request user confirmation (if needed)
    6. Cache the decision
    7. Log audit trail
    """
    
    def __init__(
        self,
        config: Optional[AuthorizationConfig] = None,
        cache: Optional[AuthorizationCache] = None,
        llm_callback: Optional[LLMJudgmentCallback] = None,
        user_callback: Optional[UserConfirmationCallback] = None,
        audit_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize the authorization engine.
        
        Args:
            config: Authorization configuration (uses default if not provided)
            cache: Authorization cache (uses global cache if not provided)
            llm_callback: Callback for LLM judgment
            user_callback: Callback for user confirmation
            audit_callback: Callback for audit logging
        """
        self._config = config or AuthorizationConfig()
        self._cache = cache or get_authorization_cache()
        self._llm_callback = llm_callback
        self._user_callback = user_callback
        self._audit_callback = audit_callback
        self._stats = {
            "total_checks": 0,
            "cache_hits": 0,
            "grants": 0,
            "denials": 0,
            "confirmations_requested": 0,
            "llm_judgments": 0,
        }
    
    @property
    def config(self) -> AuthorizationConfig:
        """Get the authorization config."""
        return self._config
    
    @config.setter
    def config(self, value: AuthorizationConfig):
        """Set the authorization config."""
        self._config = value
    
    @property
    def cache(self) -> AuthorizationCache:
        """Get the authorization cache."""
        return self._cache
    
    @property
    def stats(self) -> Dict[str, int]:
        """Get engine statistics."""
        return dict(self._stats)
    
    async def check_authorization(
        self,
        ctx: AuthorizationContext,
    ) -> AuthorizationResult:
        """
        Check authorization for a tool execution.
        
        This is the main entry point for authorization checks.
        
        Args:
            ctx: Authorization context
            
        Returns:
            AuthorizationResult with the decision
        """
        start_time = time.time()
        self._stats["total_checks"] += 1
        
        try:
            # Step 1: Check cache
            if self._config.session_cache_enabled:
                cache_result = self._check_cache(ctx)
                if cache_result:
                    self._stats["cache_hits"] += 1
                    cache_result.duration_ms = (time.time() - start_time) * 1000
                    return cache_result
            
            # Step 2: Get effective permission action
            action = self._config.get_effective_action(
                ctx.tool_name,
                ctx.tool_metadata,
                ctx.arguments,
            )
            
            # Step 3: Perform risk assessment
            risk_assessment = RiskAssessor.assess(
                ctx.tool_name,
                ctx.tool_metadata,
                ctx.arguments,
            )
            
            # Step 4: Handle based on action
            if action == PermissionAction.ALLOW:
                result = await self._handle_allow(ctx, risk_assessment)
                
            elif action == PermissionAction.DENY:
                result = await self._handle_deny(ctx, risk_assessment)
                
            elif action == PermissionAction.ASK:
                # Check if LLM judgment should be used
                if self._should_use_llm_judgment(risk_assessment):
                    result = await self._handle_llm_judgment(ctx, risk_assessment)
                else:
                    result = await self._handle_user_confirmation(ctx, risk_assessment)
            
            else:
                # Unknown action - default to ask
                result = await self._handle_user_confirmation(ctx, risk_assessment)
            
            # Step 5: Cache the decision (if applicable)
            if result.is_granted and self._config.session_cache_enabled:
                self._cache_decision(ctx, result)
            
            # Step 6: Log audit trail
            await self._log_authorization(ctx, result)
            
            # Calculate duration
            result.duration_ms = (time.time() - start_time) * 1000
            
            return result
            
        except Exception as e:
            logger.exception("Authorization check failed")
            return AuthorizationResult(
                decision=AuthorizationDecision.DENIED,
                action=PermissionAction.DENY,
                reason=f"Authorization error: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    def _check_cache(self, ctx: AuthorizationContext) -> Optional[AuthorizationResult]:
        """Check the cache for an existing decision."""
        cache_key = AuthorizationCache.build_cache_key(
            ctx.session_id,
            ctx.tool_name,
            ctx.arguments,
        )
        
        cached = self._cache.get(cache_key)
        if cached:
            granted, reason = cached
            return AuthorizationResult(
                decision=AuthorizationDecision.CACHED,
                action=PermissionAction.ALLOW if granted else PermissionAction.DENY,
                reason=reason or "Cached authorization",
                cached=True,
                cache_key=cache_key,
            )
        
        return None
    
    def _cache_decision(self, ctx: AuthorizationContext, result: AuthorizationResult) -> None:
        """Cache an authorization decision."""
        cache_key = AuthorizationCache.build_cache_key(
            ctx.session_id,
            ctx.tool_name,
            ctx.arguments,
        )
        
        self._cache.set(
            cache_key,
            result.is_granted,
            result.reason,
            metadata={
                "tool_name": ctx.tool_name,
                "agent_name": ctx.agent_name,
                "timestamp": time.time(),
            }
        )
        result.cache_key = cache_key
    
    async def _handle_allow(
        self,
        ctx: AuthorizationContext,
        risk_assessment: RiskAssessment,
    ) -> AuthorizationResult:
        """Handle an ALLOW action."""
        self._stats["grants"] += 1
        
        return AuthorizationResult(
            decision=AuthorizationDecision.GRANTED,
            action=PermissionAction.ALLOW,
            reason="Authorization granted by policy",
            risk_assessment=risk_assessment,
        )
    
    async def _handle_deny(
        self,
        ctx: AuthorizationContext,
        risk_assessment: RiskAssessment,
    ) -> AuthorizationResult:
        """Handle a DENY action."""
        self._stats["denials"] += 1
        
        return AuthorizationResult(
            decision=AuthorizationDecision.DENIED,
            action=PermissionAction.DENY,
            reason="Authorization denied by policy",
            risk_assessment=risk_assessment,
        )
    
    async def _handle_user_confirmation(
        self,
        ctx: AuthorizationContext,
        risk_assessment: RiskAssessment,
    ) -> AuthorizationResult:
        """Handle user confirmation request."""
        self._stats["confirmations_requested"] += 1
        
        # Build user message
        user_message = self._build_confirmation_message(ctx, risk_assessment)
        
        # If we have a callback, use it
        if self._user_callback:
            try:
                granted = await self._user_callback(ctx, risk_assessment)
                
                if granted:
                    self._stats["grants"] += 1
                    return AuthorizationResult(
                        decision=AuthorizationDecision.GRANTED,
                        action=PermissionAction.ALLOW,
                        reason="User approved the operation",
                        user_message=user_message,
                        risk_assessment=risk_assessment,
                    )
                else:
                    self._stats["denials"] += 1
                    return AuthorizationResult(
                        decision=AuthorizationDecision.DENIED,
                        action=PermissionAction.DENY,
                        reason="User denied the operation",
                        user_message=user_message,
                        risk_assessment=risk_assessment,
                    )
                    
            except Exception as e:
                logger.error(f"User confirmation callback failed: {e}")
        
        # Return need_confirmation if no callback or callback failed
        return AuthorizationResult(
            decision=AuthorizationDecision.NEED_CONFIRMATION,
            action=PermissionAction.ASK,
            reason="Waiting for user confirmation",
            user_message=user_message,
            risk_assessment=risk_assessment,
        )
    
    def _should_use_llm_judgment(self, risk_assessment: RiskAssessment) -> bool:
        """Check if LLM judgment should be used."""
        if self._config.llm_policy == LLMJudgmentPolicy.DISABLED:
            return False
        
        if not self._llm_callback:
            return False
        
        # Use LLM for medium risk operations in balanced/aggressive mode
        if self._config.llm_policy == LLMJudgmentPolicy.BALANCED:
            return risk_assessment.level in (RiskLevel.MEDIUM, RiskLevel.LOW)
        
        elif self._config.llm_policy == LLMJudgmentPolicy.AGGRESSIVE:
            return risk_assessment.level in (
                RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.HIGH
            )
        
        elif self._config.llm_policy == LLMJudgmentPolicy.CONSERVATIVE:
            return risk_assessment.level == RiskLevel.LOW
        
        return False
    
    async def _handle_llm_judgment(
        self,
        ctx: AuthorizationContext,
        risk_assessment: RiskAssessment,
    ) -> AuthorizationResult:
        """Handle LLM judgment."""
        self._stats["llm_judgments"] += 1
        
        if not self._llm_callback:
            # Fall back to user confirmation
            return await self._handle_user_confirmation(ctx, risk_assessment)
        
        # Build prompt for LLM
        prompt = self._build_llm_prompt(ctx, risk_assessment)
        
        try:
            judgment = await self._llm_callback(ctx, risk_assessment, prompt)
            
            # Parse LLM response
            should_allow = judgment.get("allow", False)
            confidence = judgment.get("confidence", 0.0)
            reasoning = judgment.get("reasoning", "")
            
            # If confidence is low, defer to user
            if confidence < 0.7:
                result = await self._handle_user_confirmation(ctx, risk_assessment)
                result.llm_judgment = judgment
                return result
            
            if should_allow:
                self._stats["grants"] += 1
                return AuthorizationResult(
                    decision=AuthorizationDecision.GRANTED,
                    action=PermissionAction.ALLOW,
                    reason=f"LLM approved: {reasoning}",
                    risk_assessment=risk_assessment,
                    llm_judgment=judgment,
                )
            else:
                self._stats["denials"] += 1
                return AuthorizationResult(
                    decision=AuthorizationDecision.DENIED,
                    action=PermissionAction.DENY,
                    reason=f"LLM denied: {reasoning}",
                    risk_assessment=risk_assessment,
                    llm_judgment=judgment,
                )
                
        except Exception as e:
            logger.error(f"LLM judgment failed: {e}")
            # Fall back to user confirmation
            return await self._handle_user_confirmation(ctx, risk_assessment)
    
    def _build_confirmation_message(
        self,
        ctx: AuthorizationContext,
        risk_assessment: RiskAssessment,
    ) -> str:
        """Build a user confirmation message."""
        lines = [
            f"🔐 **Authorization Required**",
            f"",
            f"Tool: `{ctx.tool_name}`",
            f"Risk Level: {risk_assessment.level.value}",
            f"Risk Score: {risk_assessment.score}/100",
        ]
        
        if risk_assessment.factors:
            lines.append(f"")
            lines.append("Risk Factors:")
            for factor in risk_assessment.factors[:5]:
                lines.append(f"  • {factor}")
        
        if ctx.arguments:
            lines.append(f"")
            lines.append("Arguments:")
            for key, value in list(ctx.arguments.items())[:5]:
                # Truncate long values
                str_value = str(value)
                if len(str_value) > 100:
                    str_value = str_value[:100] + "..."
                lines.append(f"  • {key}: {str_value}")
        
        if risk_assessment.recommendations:
            lines.append(f"")
            lines.append("Recommendations:")
            for rec in risk_assessment.recommendations[:3]:
                lines.append(f"  ⚠️ {rec}")
        
        lines.append(f"")
        lines.append("Do you want to allow this operation?")
        
        return "\n".join(lines)
    
    def _build_llm_prompt(
        self,
        ctx: AuthorizationContext,
        risk_assessment: RiskAssessment,
    ) -> str:
        """Build a prompt for LLM judgment."""
        # Use custom prompt if provided
        if self._config.llm_prompt:
            return self._config.llm_prompt.format(
                tool_name=ctx.tool_name,
                arguments=ctx.arguments,
                risk_level=risk_assessment.level.value,
                risk_score=risk_assessment.score,
                risk_factors=risk_assessment.factors,
            )
        
        # Default prompt
        return f"""Analyze this tool execution request and determine if it should be allowed.

Tool: {ctx.tool_name}
Arguments: {ctx.arguments}
Risk Level: {risk_assessment.level.value}
Risk Score: {risk_assessment.score}/100
Risk Factors: {', '.join(risk_assessment.factors) if risk_assessment.factors else 'None'}
Agent: {ctx.agent_name or 'Unknown'}

Consider:
1. Is this operation reasonable given the context?
2. Are there any security concerns?
3. Does it follow safe practices?

Respond with JSON:
{{"allow": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
    
    async def _log_authorization(
        self,
        ctx: AuthorizationContext,
        result: AuthorizationResult,
    ) -> None:
        """Log the authorization decision for audit."""
        if not self._audit_callback:
            return
        
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": ctx.session_id,
            "user_id": ctx.user_id,
            "agent_name": ctx.agent_name,
            "tool_name": ctx.tool_name,
            "arguments": ctx.arguments,
            "decision": result.decision.value,
            "action": result.action.value if isinstance(result.action, Enum) else result.action,
            "reason": result.reason,
            "cached": result.cached,
            "risk_level": result.risk_assessment.level.value if result.risk_assessment else None,
            "risk_score": result.risk_assessment.score if result.risk_assessment else None,
            "duration_ms": result.duration_ms,
        }
        
        try:
            self._audit_callback(audit_entry)
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")
    
    def grant_session_permission(
        self,
        session_id: str,
        tool_name: str,
        reason: str = "Session permission granted",
    ) -> None:
        """
        Grant permission for a tool for the entire session.
        
        Args:
            session_id: Session identifier
            tool_name: Tool name to grant
            reason: Reason for the grant
        """
        # Use tool-level cache key (without arguments)
        cache_key = AuthorizationCache.build_cache_key(
            session_id,
            tool_name,
            {},
            include_args=False,
        )
        
        self._cache.set(cache_key, True, reason)
    
    def revoke_session_permission(
        self,
        session_id: str,
        tool_name: Optional[str] = None,
    ) -> int:
        """
        Revoke permissions for a session.
        
        Args:
            session_id: Session identifier
            tool_name: Specific tool to revoke (None = all tools)
            
        Returns:
            Number of permissions revoked
        """
        return self._cache.clear(session_id)


# Global engine instance
_authorization_engine: Optional[AuthorizationEngine] = None


def get_authorization_engine() -> AuthorizationEngine:
    """Get the global authorization engine instance."""
    global _authorization_engine
    if _authorization_engine is None:
        _authorization_engine = AuthorizationEngine()
    return _authorization_engine


def set_authorization_engine(engine: AuthorizationEngine) -> None:
    """Set the global authorization engine instance."""
    global _authorization_engine
    _authorization_engine = engine


async def check_authorization(
    session_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    tool_metadata: Any = None,
    **kwargs,
) -> AuthorizationResult:
    """
    Convenience function to check authorization.
    
    Args:
        session_id: Session identifier
        tool_name: Name of the tool
        arguments: Tool arguments
        tool_metadata: Tool metadata object
        **kwargs: Additional context
        
    Returns:
        AuthorizationResult
    """
    engine = get_authorization_engine()
    ctx = AuthorizationContext(
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
        tool_metadata=tool_metadata,
        **kwargs,
    )
    return await engine.check_authorization(ctx)


__all__ = [
    "AuthorizationDecision",
    "AuthorizationContext",
    "AuthorizationResult",
    "AuthorizationEngine",
    "UserConfirmationCallback",
    "LLMJudgmentCallback",
    "get_authorization_engine",
    "set_authorization_engine",
    "check_authorization",
]
