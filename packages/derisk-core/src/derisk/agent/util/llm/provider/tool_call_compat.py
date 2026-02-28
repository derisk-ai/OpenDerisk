import re
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MODELS_WITHOUT_NATIVE_FUNCTION_CALL = frozenset([
    "QwQ-32B",
    "QwQ-32B-Preview",
    "deepseek-r1",
])

_TOOL_CALL_COMPAT_PROMPT = """
You have access to the following tools. When you need to use a tool, you MUST output the tool call in the following format:

<__function_calls__>
[
  {{"name": "name_of_tool", "args": {{"arg1": "value1", "arg2": "value2"}}}}
]
</__function_calls__>

## Available Tools:
{tools_description}

## Important Rules:
1. You MUST wrap the JSON array inside <__function_calls__>...</__function_calls__> tags
2. Each tool call is a JSON object with "name" and "args" keys
3. You can call multiple tools in one response by adding more objects to the array
4. The JSON must be valid - escape special characters properly
5. Only output tool calls when you actually need to use a tool
"""


def is_model_without_native_fc(model_name: str) -> bool:
    base_name = model_name.split("/")[-1] if "/" in model_name else model_name
    return base_name.lower() in {m.lower() for m in _MODELS_WITHOUT_NATIVE_FUNCTION_CALL}


def convert_tools_to_prompt(tools: List[Dict]) -> str:
    tools_desc = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "")
            params = func.get("parameters", {})
            tools_desc.append(f"### {name}\n{desc}\nParameters: {json.dumps(params, ensure_ascii=False)}")
    return "\n\n".join(tools_desc)


def inject_tool_prompt_to_messages(messages: List[Dict], tools: List[Dict]) -> List[Dict]:
    tools_description = convert_tools_to_prompt(tools)
    tool_prompt = _TOOL_CALL_COMPAT_PROMPT.format(tools_description=tools_description)
    
    result_messages = []
    has_system = False
    for msg in messages:
        if msg.get("role") == "system":
            has_system = True
            result_messages.append({
                "role": "system",
                "content": msg.get("content", "") + "\n\n" + tool_prompt
            })
        else:
            result_messages.append(msg)
    
    if not has_system:
        result_messages.insert(0, {"role": "system", "content": tool_prompt})
    
    return result_messages


def extract_tool_calls_from_content(content: str) -> tuple[Optional[List[Dict]], str]:
    if not content or "<__function_calls__>" not in content:
        return None, content
    
    match = re.search(r"<__function_calls__>(.*?)(?:</__function_calls__>|\Z)", content, re.DOTALL)
    if not match:
        return None, content
    
    tool_calls_str = match.group(1).strip()
    cleaned_content = re.sub(r"<__function_calls__>.*?(?:</__function_calls__>|\Z)", "", content, flags=re.DOTALL).strip()
    
    if not tool_calls_str:
        return None, cleaned_content
    
    try:
        from derisk.util.json_utils import extract_tool_calls
        raw_calls = extract_tool_calls(tool_calls_str)
        if not raw_calls:
            return None, cleaned_content
        
        result = []
        for i, call in enumerate(raw_calls):
            if not isinstance(call, dict):
                continue
            
            name = call.get("name") or call.get("tool_name") or call.get("action")
            args = call.get("args", {})
            if args is None:
                args = {}
            
            if not name:
                for key, value in call.items():
                    if key in ("thought", "name", "tool_name", "action", "args"):
                        continue
                    name = key
                    if isinstance(value, dict):
                        args = value
                    elif value is None:
                        args = {}
                    break
            
            if name:
                result.append({
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                })
        
        return (result if result else None), cleaned_content
    except Exception as e:
        logger.warning(f"Failed to extract tool calls from content: {e}")
        return None, cleaned_content