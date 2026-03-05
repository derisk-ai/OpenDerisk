"""
Risk Assessor - Unified Tool Authorization System

This module implements risk assessment for tool executions:
- RiskAssessor: Analyzes tool calls and provides risk scores/factors

Version: 2.0
"""

import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from ..tools.metadata import RiskLevel, RiskCategory


@dataclass
class RiskAssessment:
    """
    Risk assessment result for a tool execution.
    
    Attributes:
        score: Risk score from 0-100 (0 = safe, 100 = critical)
        level: Computed risk level
        factors: List of identified risk factors
        recommendations: List of recommendations
        details: Additional assessment details
    """
    score: int
    level: RiskLevel
    factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_high_risk(self) -> bool:
        """Check if this is a high risk operation."""
        return self.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    
    @property
    def requires_attention(self) -> bool:
        """Check if this requires user attention."""
        return self.level not in (RiskLevel.SAFE, RiskLevel.LOW)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": self.score,
            "level": self.level.value if isinstance(self.level, Enum) else self.level,
            "factors": self.factors,
            "recommendations": self.recommendations,
            "details": self.details,
        }


# Tool-specific risk patterns
SHELL_DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[rf]+\s+)*(/|~|\$HOME)", 100, "Recursive deletion of root or home directory"),
    (r"\brm\s+-[rf]*\s+\*", 80, "Recursive deletion with wildcard"),
    (r"\bmkfs\b", 100, "Filesystem format command"),
    (r"\bdd\s+.*of=/dev/", 100, "Direct disk write"),
    (r">\s*/dev/sd[a-z]", 100, "Write to disk device"),
    (r"\bchmod\s+777\b", 60, "Overly permissive file permissions"),
    (r"\bsudo\s+", 70, "Privileged command execution"),
    (r"\bsu\s+", 70, "User switching"),
    (r"\bcurl\s+.*\|\s*(ba)?sh", 90, "Piping remote content to shell"),
    (r"\bwget\s+.*\|\s*(ba)?sh", 90, "Piping remote content to shell"),
    (r"\bgit\s+push\s+.*--force", 60, "Force push to git repository"),
    (r"\bgit\s+reset\s+--hard", 50, "Hard reset git repository"),
    (r"\bDROP\s+DATABASE\b", 100, "Database drop command"),
    (r"\bDROP\s+TABLE\b", 80, "Table drop command"),
    (r"\bTRUNCATE\s+", 70, "Table truncate command"),
    (r":(){ :|:& };:", 100, "Fork bomb detected"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b", 100, "System shutdown/reboot"),
]

FILE_SENSITIVE_PATTERNS = [
    (r"^/etc/", 70, "System configuration directory"),
    (r"^/var/log/", 40, "System log directory"),
    (r"^/root/", 80, "Root user directory"),
    (r"\.env$", 60, "Environment file"),
    (r"\.pem$|\.key$|\.crt$", 80, "Certificate/key file"),
    (r"password|secret|credential|token|api_?key", 70, "Potential credential file"),
    (r"^/bin/|^/sbin/|^/usr/bin/|^/usr/sbin/", 90, "System binary directory"),
    (r"^~/.ssh/|\.ssh/", 90, "SSH directory"),
    (r"\.git/", 40, "Git repository internals"),
]

NETWORK_SENSITIVE_PATTERNS = [
    (r"localhost|127\.0\.0\.1|0\.0\.0\.0", 60, "Localhost access"),
    (r"192\.168\.|10\.\d+\.|172\.(1[6-9]|2[0-9]|3[01])\.", 50, "Internal network access"),
    (r"\.local$|\.internal$", 50, "Local/internal domain"),
    (r"metadata\.google|169\.254\.169\.254", 90, "Cloud metadata service"),
]


class RiskAssessor:
    """
    Risk Assessor - Analyzes tool executions for security risks.
    
    Provides static risk assessment based on tool metadata and arguments.
    """
    
    @staticmethod
    def assess(
        tool_name: str,
        tool_metadata: Any,
        arguments: Dict[str, Any],
    ) -> RiskAssessment:
        """
        Assess the risk of a tool execution.
        
        Args:
            tool_name: Name of the tool
            tool_metadata: Tool metadata object
            arguments: Tool arguments
            
        Returns:
            RiskAssessment with score, factors, and recommendations
        """
        factors: List[str] = []
        details: Dict[str, Any] = {}
        base_score = 0
        
        # Get base risk from tool metadata
        auth = getattr(tool_metadata, 'authorization', None)
        if auth:
            risk_level = getattr(auth, 'risk_level', RiskLevel.MEDIUM)
            risk_categories = getattr(auth, 'risk_categories', [])
            
            # Base score from risk level
            level_scores = {
                RiskLevel.SAFE: 0,
                RiskLevel.LOW: 20,
                RiskLevel.MEDIUM: 40,
                RiskLevel.HIGH: 70,
                RiskLevel.CRITICAL: 90,
            }
            base_score = level_scores.get(
                RiskLevel(risk_level) if isinstance(risk_level, str) else risk_level,
                40
            )
            
            # Add factors from risk categories
            for cat in risk_categories:
                cat_name = cat.value if isinstance(cat, Enum) else cat
                factors.append(f"Risk category: {cat_name}")
        
        # Tool-specific analysis
        category = getattr(tool_metadata, 'category', None)
        
        if category == "shell" or tool_name == "bash":
            score_adjustment, shell_factors = RiskAssessor._assess_shell(arguments)
            base_score = max(base_score, score_adjustment)
            factors.extend(shell_factors)
            
        elif category == "file_system" or tool_name in ("read", "write", "edit"):
            score_adjustment, file_factors = RiskAssessor._assess_file(tool_name, arguments)
            base_score = max(base_score, score_adjustment)
            factors.extend(file_factors)
            
        elif category == "network" or tool_name in ("webfetch", "websearch"):
            score_adjustment, network_factors = RiskAssessor._assess_network(arguments)
            base_score = max(base_score, score_adjustment)
            factors.extend(network_factors)
        
        # Cap score at 100
        final_score = min(100, base_score)
        
        # Determine level from score
        level = RiskAssessor._score_to_level(final_score)
        
        # Generate recommendations
        recommendations = RiskAssessor._get_recommendations(
            level, factors, tool_name, arguments
        )
        
        return RiskAssessment(
            score=final_score,
            level=level,
            factors=factors,
            recommendations=recommendations,
            details=details,
        )
    
    @staticmethod
    def _assess_shell(arguments: Dict[str, Any]) -> tuple:
        """Assess risk for shell commands."""
        command = arguments.get("command", "")
        factors = []
        max_score = 0
        
        for pattern, score, description in SHELL_DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                factors.append(description)
                max_score = max(max_score, score)
        
        # Check for pipe chains
        if command.count("|") > 2:
            factors.append("Complex command pipeline")
            max_score = max(max_score, 40)
        
        # Check for background execution
        if "&" in command and not "&&" in command:
            factors.append("Background process execution")
            max_score = max(max_score, 30)
        
        return max_score, factors
    
    @staticmethod
    def _assess_file(tool_name: str, arguments: Dict[str, Any]) -> tuple:
        """Assess risk for file operations."""
        file_path = arguments.get("file_path", arguments.get("path", ""))
        factors = []
        max_score = 0
        
        for pattern, score, description in FILE_SENSITIVE_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                factors.append(description)
                max_score = max(max_score, score)
        
        # Higher risk for write/edit operations
        if tool_name in ("write", "edit"):
            max_score = max(max_score, 30)
            if not factors:
                factors.append("File modification operation")
        
        return max_score, factors
    
    @staticmethod
    def _assess_network(arguments: Dict[str, Any]) -> tuple:
        """Assess risk for network operations."""
        url = arguments.get("url", "")
        factors = []
        max_score = 0
        
        for pattern, score, description in NETWORK_SENSITIVE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                factors.append(description)
                max_score = max(max_score, score)
        
        # Check for sensitive data in request
        body = arguments.get("body", "")
        if body:
            sensitive_patterns = ["password", "token", "secret", "api_key", "credential"]
            for pattern in sensitive_patterns:
                if pattern in body.lower():
                    factors.append(f"Sensitive data in request body: {pattern}")
                    max_score = max(max_score, 60)
        
        return max_score, factors
    
    @staticmethod
    def _score_to_level(score: int) -> RiskLevel:
        """Convert a risk score to a risk level."""
        if score <= 10:
            return RiskLevel.SAFE
        elif score <= 30:
            return RiskLevel.LOW
        elif score <= 50:
            return RiskLevel.MEDIUM
        elif score <= 80:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
    
    @staticmethod
    def _get_recommendations(
        level: RiskLevel,
        factors: List[str],
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> List[str]:
        """Generate recommendations based on risk assessment."""
        recommendations = []
        
        if level == RiskLevel.CRITICAL:
            recommendations.append("CRITICAL: This operation requires explicit user approval")
            recommendations.append("Consider alternative approaches if possible")
            
        elif level == RiskLevel.HIGH:
            recommendations.append("High-risk operation - review carefully before approving")
            
        elif level == RiskLevel.MEDIUM:
            recommendations.append("Moderate risk - verify the operation is intended")
        
        # Tool-specific recommendations
        if tool_name == "bash":
            command = arguments.get("command", "")
            if "rm" in command:
                recommendations.append("Verify file paths before deletion")
            if "sudo" in command:
                recommendations.append("Consider running without sudo if possible")
                
        elif tool_name in ("write", "edit"):
            recommendations.append("Ensure you have backups of important files")
            
        elif tool_name == "webfetch":
            recommendations.append("Verify the URL is from a trusted source")
        
        return recommendations


__all__ = [
    "RiskAssessor",
    "RiskAssessment",
    "SHELL_DANGEROUS_PATTERNS",
    "FILE_SENSITIVE_PATTERNS",
    "NETWORK_SENSITIVE_PATTERNS",
]
