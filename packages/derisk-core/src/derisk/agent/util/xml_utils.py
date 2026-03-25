import re
from typing import List, Tuple, Optional

import xmltodict


def extract_valid_xmls(text) -> List[str]:
    # 正则匹配形如 <tag>...</tag> 的候选 XML 片段（支持属性、嵌套）
    # 改进版正则：允许标签名包含冒号（如 <ns:tag>），并处理自闭合标签
    pattern = r'(<([\w:]+)[^>]*>(?:.*?</\2>)|<[\w:]+[^>]*/>)'
    candidates = re.findall(pattern, text, re.DOTALL)

    valid_xmls = []
    for candidate in candidates:
        xml_str = candidate[0]
        try:
            # 尝试解析 XML
            xmltodict.parse(xml_str)
            valid_xmls.append(xml_str)
        except Exception:
            # 解析失败则跳过
            continue
    return valid_xmls


def extract_specific_tag(text, tag_name) -> Tuple[Optional[bool], Optional[str]]:
    """
    提取指定标签的内容

    Args:
        text (str): 输入文本
        tag_name (str): 要提取的标签名
    Returns:
        (
        bool: 标签内容是否已经完结
        str: 具体匹配到的内容
        )
        dict: 包含标签信息和内容的字典
    """
    # 构建匹配模式
    pattern = f'<{tag_name}>(.*?)</{tag_name}>'

    match = re.search(pattern, text, re.DOTALL)

    if match:
        return True, match.group(1).strip()
    else:
        # 检查是否有未闭合的标签
        start_match = re.search(f'<{tag_name}>', text)
        if start_match:
            start_pos = start_match.end()
            # 查找下一个标签开始位置或文本结束
            next_tag_match = re.search(r'<', text[start_pos:])

            if next_tag_match:
                end_pos = start_pos + next_tag_match.start()
                content = text[start_pos:end_pos]
            else:
                content = text[start_pos:]

            return False, content
        else:
            return None, None
