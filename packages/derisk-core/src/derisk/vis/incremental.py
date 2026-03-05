"""
增量协议增强

提供智能增量合并和差异检测功能
"""

from __future__ import annotations

import difflib
import logging
from typing import Any, Dict, List, Optional, Set

from derisk._private.pydantic import BaseModel

logger = logging.getLogger(__name__)


class IncrementalMerger:
    """
    增量合并器
    
    智能合并增量数据到基础数据
    
    示例:
        merger = IncrementalMerger()
        
        # 初始数据
        base = {"markdown": "Hello", "items": [1, 2]}
        
        # 增量数据
        delta = {"type": "incr", "markdown": " World", "items": [3]}
        
        # 合并
        result = merger.merge(base, delta)
        # {"markdown": "Hello World", "items": [1, 2, 3]}
    """
    
    def __init__(self):
        """初始化合并器"""
        self._list_fields: Set[str] = set()
        self._text_fields: Set[str] = set()
        self._replace_fields: Set[str] = set()
    
    def register_list_field(self, field_name: str):
        """
        注册列表字段(增量追加)
        
        Args:
            field_name: 字段名
        """
        self._list_fields.add(field_name)
    
    def register_text_field(self, field_name: str):
        """
        注册文本字段(增量追加)
        
        Args:
            field_name: 字段名
        """
        self._text_fields.add(field_name)
    
    def register_replace_field(self, field_name: str):
        """
        注册替换字段(完全替换)
        
        Args:
            field_name: 字段名
        """
        self._replace_fields.add(field_name)
    
    def merge(
        self,
        base: Dict[str, Any],
        delta: Dict[str, Any],
        strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        合并增量数据
        
        Args:
            base: 基础数据
            delta: 增量数据
            strategy: 合并策略(auto, append, replace)
            
        Returns:
            合并后的数据
        """
        # 判断类型
        data_type = delta.get("type", "all")
        
        if data_type == "incr":
            return self._merge_incremental(base, delta)
        else:
            return self._merge_full(base, delta)
    
    def _merge_incremental(
        self,
        base: Dict[str, Any],
        delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """增量合并"""
        result = base.copy()
        
        for key, value in delta.items():
            if key in ["type", "uid"]:
                continue
            
            # 列表字段 - 追加
            if key in self._list_fields or key == "items":
                if key not in result:
                    result[key] = []
                
                if isinstance(value, list):
                    result[key].extend(value)
                else:
                    result[key].append(value)
            
            # 文本字段 - 追加
            elif key in self._text_fields or key == "markdown":
                if key not in result:
                    result[key] = ""
                
                result[key] = str(result[key]) + str(value)
            
            # 替换字段 - 完全替换
            elif key in self._replace_fields:
                result[key] = value
            
            # 默认: 如果base有值则替换,否则设置
            else:
                if value is not None:
                    result[key] = value
        
        return result
    
    def _merge_full(
        self,
        base: Dict[str, Any],
        delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """全量合并(替换)"""
        result = base.copy()
        
        for key, value in delta.items():
            if key in ["type", "uid"]:
                continue
            
            result[key] = value
        
        return result


class DiffDetector:
    """
    差异检测器
    
    检测两个数据版本之间的差异
    
    示例:
        detector = DiffDetector()
        
        old_data = {"content": "Hello", "items": [1, 2]}
        new_data = {"content": "Hello World", "items": [1, 2, 3]}
        
        diff = detector.detect(old_data, new_data)
        # {"content": {"old": "Hello", "new": "Hello World"}, "items": {"added": [3]}}
    """
    
    def detect(
        self,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        检测差异
        
        Args:
            old_data: 旧数据
            new_data: 新数据
            
        Returns:
            差异描述
        """
        diff = {}
        
        # 检查所有键
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            if key in ["uid", "created_at", "updated_at"]:
                continue
            
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            # 值相同,跳过
            if old_value == new_value:
                continue
            
            # 键不存在于旧数据
            if key not in old_data:
                diff[key] = {"status": "added", "value": new_value}
                continue
            
            # 键不存在于新数据
            if key not in new_data:
                diff[key] = {"status": "removed", "value": old_value}
                continue
            
            # 值不同,检测具体差异
            key_diff = self._detect_value_diff(old_value, new_value)
            if key_diff:
                diff[key] = key_diff
        
        return diff
    
    def _detect_value_diff(
        self,
        old_value: Any,
        new_value: Any
    ) -> Optional[Dict[str, Any]]:
        """检测值的差异"""
        # 类型不同
        if type(old_value) != type(new_value):
            return {
                "status": "type_changed",
                "old": old_value,
                "new": new_value
            }
        
        # 列表差异
        if isinstance(old_value, list):
            return self._detect_list_diff(old_value, new_value)
        
        # 字典差异
        if isinstance(old_value, dict):
            return self._detect_dict_diff(old_value, new_value)
        
        # 字符串差异
        if isinstance(old_value, str):
            return self._detect_string_diff(old_value, new_value)
        
        # 其他类型
        return {
            "status": "changed",
            "old": old_value,
            "new": new_value
        }
    
    def _detect_list_diff(
        self,
        old_list: List[Any],
        new_list: List[Any]
    ) -> Dict[str, Any]:
        """检测列表差异"""
        old_set = set(str(x) for x in old_list)
        new_set = set(str(x) for x in new_list)
        
        added = [x for x in new_list if str(x) not in old_set]
        removed = [x for x in old_list if str(x) not in new_set]
        
        return {
            "status": "list_changed",
            "added": added,
            "removed": removed,
            "old_count": len(old_list),
            "new_count": len(new_list)
        }
    
    def _detect_dict_diff(
        self,
        old_dict: Dict[str, Any],
        new_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """检测字典差异"""
        old_keys = set(old_dict.keys())
        new_keys = set(new_dict.keys())
        
        added_keys = new_keys - old_keys
        removed_keys = old_keys - new_keys
        common_keys = old_keys & new_keys
        
        changed = {}
        for key in common_keys:
            if old_dict[key] != new_dict[key]:
                changed[key] = {
                    "old": old_dict[key],
                    "new": new_dict[key]
                }
        
        return {
            "status": "dict_changed",
            "added_keys": list(added_keys),
            "removed_keys": list(removed_keys),
            "changed": changed
        }
    
    def _detect_string_diff(
        self,
        old_str: str,
        new_str: str
    ) -> Dict[str, Any]:
        """检测字符串差异"""
        # 使用difflib计算差异
        matcher = difflib.SequenceMatcher(None, old_str, new_str)
        
        changes = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                changes.append({
                    "type": "replace",
                    "old": old_str[i1:i2],
                    "new": new_str[j1:j2]
                })
            elif tag == "delete":
                changes.append({
                    "type": "delete",
                    "old": old_str[i1:i2]
                })
            elif tag == "insert":
                changes.append({
                    "type": "insert",
                    "new": new_str[j1:j2]
                })
        
        return {
            "status": "string_changed",
            "changes": changes,
            "similarity": matcher.ratio()
        }


class IncrementalValidator:
    """
    增量数据验证器
    
    验证增量数据的有效性
    """
    
    @staticmethod
    def validate_uid(uid: Optional[str]) -> bool:
        """验证UID"""
        return uid is not None and len(uid) > 0
    
    @staticmethod
    def validate_type(data_type: str) -> bool:
        """验证类型"""
        return data_type in ["incr", "all"]
    
    @staticmethod
    def validate_incremental_data(data: Dict[str, Any]) -> List[str]:
        """
        验证增量数据
        
        Args:
            data: 增量数据
            
        Returns:
            错误列表
        """
        errors = []
        
        # 必需字段
        if "uid" not in data:
            errors.append("缺少必需字段: uid")
        
        if "type" not in data:
            errors.append("缺少必需字段: type")
        elif not IncrementalValidator.validate_type(data["type"]):
            errors.append(f"无效的type值: {data['type']}")
        
        # 增量数据应该有内容
        if data.get("type") == "incr":
            has_content = any(
                key in data
                for key in ["markdown", "items", "content", "metadata"]
            )
            if not has_content:
                errors.append("增量数据缺少内容字段")
        
        return errors