"""Sensitive column auto-detection.

Identifies potentially sensitive columns by analyzing column names,
types, comments, and sample data. Uses pattern matching — not ML —
for predictability and auditability.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SensitiveType(str, Enum):
    """Classification of sensitive data types."""

    PHONE = "phone"
    EMAIL = "email"
    ID_CARD = "id_card"
    BANK_CARD = "bank_card"
    ADDRESS = "address"
    NAME = "name"
    PASSWORD = "password"
    TOKEN = "token"
    IP_ADDRESS = "ip_address"
    CUSTOM = "custom"


@dataclass
class SensitiveColumnInfo:
    """Detected sensitive column metadata."""

    table_name: str
    column_name: str
    sensitive_type: str  # SensitiveType value
    confidence: float = 0.0  # 0.0 ~ 1.0
    detection_reason: str = ""
    masking_strategy: str = "partial"  # partial / full / token


# Name patterns → (SensitiveType, confidence, masking_strategy)
_NAME_PATTERNS: List[tuple] = [
    # Phone - 扩展常见变体
    (re.compile(r"(phone|mobile|tel|cellphone|cell|联系电话|联系电话|手机号|手机号码|电话号码|联系方式|contact_phone|phone_number)", re.I),
     SensitiveType.PHONE, 0.85, "partial"),
    # Email - 扩展常见变体
    (re.compile(r"(email|e_mail|mail|邮箱|邮件|电子邮箱|email_address)", re.I),
     SensitiveType.EMAIL, 0.9, "partial"),
    # ID card - 扩展常见变体（身份证）
    (re.compile(r"(id_card|idcard|identity|身份证|证件号|id_number|id_no|card_id|sfz|sfzh|idcard_no|identity_card|身份证号|证件号码|idcode)", re.I),
     SensitiveType.ID_CARD, 0.95, "partial"),
    # Bank card - 扩展常见变体
    (re.compile(r"(bank_card|bankcard|card_no|card_number|银行卡|卡号|bankcard_no|bank_card_no|credit_card|debit_card)", re.I),
     SensitiveType.BANK_CARD, 0.9, "partial"),
    # Address - 扩展常见变体
    (re.compile(r"(address|addr|地址|住址|居住地|详细地址|location|street|home_address|work_address)", re.I),
     SensitiveType.ADDRESS, 0.7, "partial"),
    # Name - 扩展常见变体（人名）
    (re.compile(r"(real_name|true_name|full_name|姓名|真实姓名|姓名|cn_name|customer_name|user_name|person_name|contact_name|member_name|employee_name|staff_name|patient_name|client_name|subscriber_name)", re.I),
     SensitiveType.NAME, 0.85, "partial"),
    # Name - 更通用的模式（置信度略低）
    (re.compile(r"^(name|cn|nick_name|nickname|nick|first_name|last_name|given_name|family_name|surname)$", re.I),
     SensitiveType.NAME, 0.65, "partial"),
    # Password / secret - 扩展常见变体
    (re.compile(r"(password|passwd|pwd|secret|密码|口令|登录密码|pass|user_password)", re.I),
     SensitiveType.PASSWORD, 0.95, "full"),
    # Token / key - 扩展常见变体
    (re.compile(r"(token|api_key|access_key|secret_key|密钥|auth_token|refresh_token|session_token|private_key|api_token)", re.I),
     SensitiveType.TOKEN, 0.95, "full"),
    # IP address - 扩展常见变体
    (re.compile(r"(ip_addr|ip_address|client_ip|remote_ip|ip|user_ip|source_ip|dest_ip|host_ip|server_ip)", re.I),
     SensitiveType.IP_ADDRESS, 0.7, "partial"),
]

# Comment patterns (Chinese + English) - 扩展常见注释
_COMMENT_PATTERNS: List[tuple] = [
    (re.compile(r"(手机|电话|phone|mobile|联系方式|联系电话|手机号)", re.I), SensitiveType.PHONE, 0.8),
    (re.compile(r"(邮箱|email|邮件地址|电子邮箱)", re.I), SensitiveType.EMAIL, 0.8),
    (re.compile(r"(身份证|证件|identity|id.?card|身份证号|证件号|证件号码|身份证号码)", re.I), SensitiveType.ID_CARD, 0.85),
    (re.compile(r"(银行卡|card.?no|银行卡号|卡号|信用卡|借记卡)", re.I), SensitiveType.BANK_CARD, 0.85),
    (re.compile(r"(地址|address|详细地址|居住地址|联系地址)", re.I), SensitiveType.ADDRESS, 0.6),
    (re.compile(r"(姓名|名字|真实姓名|用户名|联系人|姓名)", re.I), SensitiveType.NAME, 0.75),
    (re.compile(r"(密码|password|secret|登录密码|用户密码)", re.I), SensitiveType.PASSWORD, 0.9),
]

# Sample value patterns (for validating detections)
_VALUE_PATTERNS: Dict[str, re.Pattern] = {
    SensitiveType.PHONE.value: re.compile(
        r"^1[3-9]\d{9}$|^\+?\d{1,3}[\s-]?\d{6,14}$"
    ),
    SensitiveType.EMAIL.value: re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    ),
    SensitiveType.ID_CARD.value: re.compile(
        r"^\d{15}$|^\d{17}[\dXx]$"
    ),
    SensitiveType.BANK_CARD.value: re.compile(
        r"^\d{13,19}$"
    ),
    SensitiveType.IP_ADDRESS.value: re.compile(
        r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    ),
}


class SensitiveColumnDetector:
    """Detects sensitive columns from table spec metadata.

    Detection signals (combined for higher accuracy):
    1. Column name pattern matching
    2. Column comment pattern matching
    3. Sample data value pattern matching
    4. Column type heuristics (VARCHAR of certain lengths)
    """

    def __init__(self, confidence_threshold: float = 0.6):
        """Initialize detector.

        Args:
            confidence_threshold: Minimum confidence to flag a column.
                Lower = more sensitive columns detected (more false positives).
                Higher = fewer detections (may miss some).
        """
        self._threshold = confidence_threshold

    def detect_from_spec(
        self, table_spec: Dict[str, Any]
    ) -> List[SensitiveColumnInfo]:
        """Detect sensitive columns from a table spec dict.

        Args:
            table_spec: Table spec from TableSpecDao, with keys:
                table_name, columns, sample_data, create_ddl, etc.

        Returns:
            List of detected sensitive columns above the confidence threshold.
        """
        table_name = table_spec.get("table_name", "")
        columns = table_spec.get("columns", []) or []
        sample_data = table_spec.get("sample_data") or {}
        sample_cols = sample_data.get("columns", [])
        sample_rows = sample_data.get("rows", [])

        results = []

        for col in columns:
            col_name = col.get("name", "")
            col_type = str(col.get("type", "")).lower()
            col_comment = col.get("comment", "") or ""

            if not col_name:
                continue

            # Only check text-type columns
            if not self._is_text_type(col_type):
                continue

            best_match = self._detect_column(
                col_name, col_type, col_comment,
                table_name, sample_cols, sample_rows,
            )
            if best_match and best_match.confidence >= self._threshold:
                results.append(best_match)

        return results

    def detect_batch(
        self, table_specs: List[Dict[str, Any]]
    ) -> Dict[str, List[SensitiveColumnInfo]]:
        """Detect sensitive columns across multiple tables.

        Returns:
            Dict mapping table_name → list of sensitive columns.
        """
        result = {}
        for spec in table_specs:
            table_name = spec.get("table_name", "")
            detections = self.detect_from_spec(spec)
            if detections:
                result[table_name] = detections
        return result

    def _detect_column(
        self,
        col_name: str,
        col_type: str,
        col_comment: str,
        table_name: str,
        sample_cols: List[str],
        sample_rows: List[List],
    ) -> Optional[SensitiveColumnInfo]:
        """Run all detection strategies on a single column."""
        candidates: List[SensitiveColumnInfo] = []

        # Strategy 1: Name pattern
        for pattern, stype, conf, strategy in _NAME_PATTERNS:
            if pattern.search(col_name):
                candidates.append(SensitiveColumnInfo(
                    table_name=table_name,
                    column_name=col_name,
                    sensitive_type=stype.value,
                    confidence=conf,
                    detection_reason=f"name matches '{pattern.pattern}'",
                    masking_strategy=strategy,
                ))
                break

        # Strategy 2: Comment pattern
        if col_comment:
            for pattern, stype, conf in _COMMENT_PATTERNS:
                if pattern.search(col_comment):
                    # If we already have a name match, boost confidence
                    existing = next(
                        (c for c in candidates if c.sensitive_type == stype.value),
                        None,
                    )
                    if existing:
                        existing.confidence = min(
                            existing.confidence + 0.1, 1.0
                        )
                        existing.detection_reason += (
                            f"; comment matches '{pattern.pattern}'"
                        )
                    else:
                        candidates.append(SensitiveColumnInfo(
                            table_name=table_name,
                            column_name=col_name,
                            sensitive_type=stype.value,
                            confidence=conf,
                            detection_reason=(
                                f"comment '{col_comment}' matches "
                                f"'{pattern.pattern}'"
                            ),
                            masking_strategy="partial",
                        ))
                    break

        # Strategy 3: Validate with sample data
        if sample_cols and sample_rows and candidates:
            col_idx = None
            for i, sc in enumerate(sample_cols):
                if sc == col_name:
                    col_idx = i
                    break

            if col_idx is not None:
                sample_values = [
                    str(row[col_idx])
                    for row in sample_rows
                    if row and col_idx < len(row) and row[col_idx] is not None
                ]

                for candidate in candidates:
                    vp = _VALUE_PATTERNS.get(candidate.sensitive_type)
                    if vp and sample_values:
                        match_count = sum(
                            1 for v in sample_values if vp.match(v)
                        )
                        if match_count > 0:
                            ratio = match_count / len(sample_values)
                            candidate.confidence = min(
                                candidate.confidence + ratio * 0.1, 1.0
                            )
                            candidate.detection_reason += (
                                f"; {match_count}/{len(sample_values)} "
                                f"samples match value pattern"
                            )

        # Strategy 4: Heuristic detection from sample data (when name/comment don't match)
        # Detect sensitive data by analyzing sample value patterns
        if not candidates and sample_cols and sample_rows:
            col_idx = None
            for i, sc in enumerate(sample_cols):
                if sc == col_name:
                    col_idx = i
                    break

            if col_idx is not None:
                sample_values = [
                    str(row[col_idx])
                    for row in sample_rows
                    if row and col_idx < len(row) and row[col_idx] is not None
                    and str(row[col_idx]) != "NULL" and str(row[col_idx]).strip()
                ]

                if sample_values:
                    # Check each value pattern type
                    for stype, vp in _VALUE_PATTERNS.items():
                        if stype == SensitiveType.BANK_CARD.value:
                            continue  # Bank card is too generic (13-19 digits)

                        match_count = sum(
                            1 for v in sample_values if vp.match(v)
                        )
                        if match_count > 0:
                            ratio = match_count / len(sample_values)
                            # Require at least half of samples to match for heuristics
                            if ratio >= 0.5:
                                candidates.append(SensitiveColumnInfo(
                                    table_name=table_name,
                                    column_name=col_name,
                                    sensitive_type=stype,
                                    confidence=0.5 + ratio * 0.3,  # 0.5 ~ 0.8
                                    detection_reason=(
                                        f"sample data heuristic: {match_count}/{len(sample_values)} "
                                        f"values match {stype} pattern"
                                    ),
                                    masking_strategy="partial",
                                ))
                                break

                    # Heuristic for Chinese names (2-4 Chinese characters)
                    chinese_name_pattern = re.compile(r"^[\\u4e00-\\u9fa5]{2,4}$")
                    name_match_count = sum(
                        1 for v in sample_values if chinese_name_pattern.match(v)
                    )
                    if name_match_count > 0:
                        ratio = name_match_count / len(sample_values)
                        if ratio >= 0.5:
                            # Only add if not already detected
                            existing_name = next(
                                (c for c in candidates if c.sensitive_type == SensitiveType.NAME.value),
                                None,
                            )
                            if not existing_name:
                                candidates.append(SensitiveColumnInfo(
                                    table_name=table_name,
                                    column_name=col_name,
                                    sensitive_type=SensitiveType.NAME.value,
                                    confidence=0.5 + ratio * 0.25,  # 0.5 ~ 0.75
                                    detection_reason=(
                                        f"sample data heuristic: {name_match_count}/{len(sample_values)} "
                                        f"values look like Chinese names"
                                    ),
                                    masking_strategy="partial",
                                ))

        # Return highest confidence candidate
        if candidates:
            return max(candidates, key=lambda c: c.confidence)
        return None

    @staticmethod
    def _is_text_type(col_type: str) -> bool:
        """Check if column type is text-based."""
        text_indicators = (
            "varchar", "char", "text", "string", "nvarchar", "nchar",
            "clob", "nclob", "longtext", "mediumtext", "tinytext",
        )
        return any(t in col_type for t in text_indicators)
