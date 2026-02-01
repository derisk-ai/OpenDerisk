"""Utilities for the json_fixes package."""

import json
import logging
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from json_repair import json_repair

logger = logging.getLogger(__name__)

LLM_DEFAULT_RESPONSE_FORMAT = "llm_response_format_1"


def serialize(obj):
    if isinstance(obj, datetime):
        return obj.replace(microsecond=0).isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return str(obj)


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def extract_char_position(error_message: str) -> int:
    """Extract the character position from the JSONDecodeError message.

    Args:
        error_message (str): The error message from the JSONDecodeError
          exception.

    Returns:
        int: The character position.
    """

    char_pattern = re.compile(r"\(char (\d+)\)")
    if match := char_pattern.search(error_message):
        return int(match[1])
    else:
        raise ValueError("Character position not found in the error message.")


def find_json_objects(text: str):
    json_objects = []
    inside_string = False
    escape_character = False
    stack = []
    start_index = -1
    modified_text = list(text)  # Convert text to a list for easy modification

    for i, char in enumerate(text):
        # Handle escape characters
        if char == "\\" and not escape_character:
            escape_character = True
            continue

        # Toggle inside_string flag
        if char == '"' and not escape_character:
            inside_string = not inside_string

        # Replace newline and tab characters inside strings
        if inside_string:
            if char == "\n":
                modified_text[i] = "\\n"
            elif char == "\t":
                modified_text[i] = "\\t"

        # Handle opening brackets
        if char in "{[" and not inside_string:
            stack.append(char)
            if len(stack) == 1:
                start_index = i
        # Handle closing brackets
        if char in "}]" and not inside_string and stack:
            if (char == "}" and stack[-1] == "{") or (char == "]" and stack[-1] == "["):
                stack.pop()
                if not stack:
                    end_index = i + 1
                    try:
                        json_str = "".join(modified_text[start_index:end_index])
                        json_obj = json.loads(json_str)
                        json_objects.append(json_obj)
                    except json.JSONDecodeError:
                        pass
        # Reset escape_character flag
        escape_character = False if escape_character else escape_character

    return json_objects


def parse_or_raise_error(text: str, is_array: bool = False):
    if not text:
        return None
    parsed_objs = find_json_objects(text)
    if not parsed_objs:
        # Use json.loads to raise raw error
        return json.loads(text)
    return parsed_objs if is_array else parsed_objs[0]


def _format_json_str(jstr):
    """Remove newlines outside of quotes, and handle JSON escape sequences.

    1. this function removes the newline in the query outside of quotes otherwise json.loads(s) will fail.
        Ex 1:
        "{\n"tool": "python",\n"query": "print('hello')\nprint('world')"\n}" -> "{"tool": "python","query": "print('hello')\nprint('world')"}"
        Ex 2:
        "{\n  \"location\": \"Boston, MA\"\n}" -> "{"location": "Boston, MA"}"

    2. this function also handles JSON escape sequences inside quotes,
        Ex 1:
        '{"args": "a\na\na\ta"}' -> '{"args": "a\\na\\na\\ta"}'
    """  # noqa
    result = []
    inside_quotes = False
    last_char = " "
    for char in jstr:
        if last_char != "\\" and char == '"':
            inside_quotes = not inside_quotes
        last_char = char
        if not inside_quotes and char == "\n":
            continue
        if inside_quotes and char == "\n":
            char = "\\n"
        if inside_quotes and char == "\t":
            char = "\\t"
        result.append(char)
    return "".join(result)


def compare_json_properties(json1, json2):
    """
    Check whether the attributes of two json are consistent
    """
    obj1 = json.loads(json1)
    obj2 = json.loads(json2)

    # 检查两个对象的键集合是否相同
    if set(obj1.keys()) == set(obj2.keys()):
        return True

    return False


def compare_json_properties_ex(json1, json2):
    """
    Check whether the attributes of two json are consistent
    """
    # 检查两个对象的键集合是否相同
    if set(json1.keys()) == set(json2.keys()):
        return True

    return False


def _fix_newlines(text: str) -> str:
    """修复换行符问题"""
    return text.replace('\\n', '\n')


def _fix_escapes(text: str) -> str:
    """修复转义字符问题"""
    return text.replace('\\\\', '')


def _fix_trailing_commas(text: str) -> str:
    """修复尾随逗号问题"""
    # 移除对象或数组末尾的逗号
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def _fix_quotes(text: str) -> str:
    """修复引号问题"""
    # 尝试修复常见的引号问题
    text = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', text)
    return text


def get_fix_strategies() -> list:
    """
    获取JSON修复策略列表。

    Returns:
        list: 修复函数列表
    """
    return [
        _fix_newlines,
        _fix_escapes,
        _fix_trailing_commas,
        _fix_quotes
    ]


def extract_tool_calls(text: str) -> list:
    """
    从文本中提取工具调用列表。

    该方法会尝试多种修复策略来解析可能格式不正确的JSON。

    Args:
        text: 包含工具调用的文本

    Returns:
        list: 工具调用列表，每个元素是一个字典
    """

    try:
        tool_calls = json_repair.loads(text)
        if _is_valid_tool_calls(tool_calls):
            return _normalize_tool_calls(tool_calls)
    except Exception as e:
        logger.warning(f"第一次解析失败: {e}")

    # 尝试修复常见的格式问题
    for fix_strategy in get_fix_strategies():
        try:
            fixed_text = fix_strategy(text)
            tool_calls = json_repair.loads(fixed_text)
            if _is_valid_tool_calls(tool_calls):
                logger.info(f"使用修复策略成功解析: {fix_strategy.__name__}")
                return _normalize_tool_calls(tool_calls)
        except Exception as e:
            logger.debug(f"修复策略 {fix_strategy.__name__} 失败: {e}")
            continue

    logger.error(f"[extract_tool_calls] 所有解析策略都失败: {text}")
    return []


def _is_valid_tool_calls(tool_calls: Any) -> bool:
    """
    验证工具调用格式是否正确。

    Args:
        tool_calls: 待验证的工具调用数据

    Returns:
        bool: 格式是否正确
    """
    return (isinstance(tool_calls, list) and
            all(isinstance(item, dict) for item in tool_calls))


def _normalize_tool_calls(tool_calls: list) -> list:
    """过滤并返回有效的工具调用列表。"""
    return [dict(entry) for entry in tool_calls if isinstance(entry, dict)]
