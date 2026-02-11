import re
import string
from typing import Dict


class StringSizeConverter:
    @staticmethod
    def to_bytes(text, encoding='utf-8'):
        """获取字符串的字节大小"""
        return len(text.encode(encoding))

    @staticmethod
    def to_kb(text, decimal_places=2):
        """转换为KB"""
        bytes_size = StringSizeConverter.to_bytes(text)
        return round(bytes_size / 1024, decimal_places)

    @staticmethod
    def to_mb(text, decimal_places=2):
        """转换为MB"""
        bytes_size = StringSizeConverter.to_bytes(text)
        return round(bytes_size / (1024 * 1024), decimal_places)

    @staticmethod
    def auto_format(text, decimal_places=2):
        """自动格式化大小"""
        if not text:
            return "0 B"
        bytes_size = StringSizeConverter.to_bytes(text)

        if bytes_size < 1024:
            return f"{bytes_size} B"
        elif bytes_size < 1024 * 1024:
            kb = round(bytes_size / 1024, decimal_places)
            return f"{kb} KB"
        elif bytes_size < 1024 * 1024 * 1024:
            mb = round(bytes_size / (1024 * 1024), decimal_places)
            return f"{mb} MB"
        else:
            gb = round(bytes_size / (1024 * 1024 * 1024), decimal_places)
            return f"{gb} GB"

def is_all_chinese(text):
    ### Determine whether the string is pure Chinese
    pattern = re.compile(r"^[一-龥]+$")
    match = re.match(pattern, text)
    return match is not None


def contains_chinese(text):
    """Check if the text contains Chinese characters."""
    return re.search(r"[\u4e00-\u9fa5]", text) is not None


def is_number(s: str) -> bool:
    """
    判断字符串是否为数字
    :param s:
    :return:
    """
    # 找到第一个不是数字的字符
    return False if not s or next((c for c in s if c > "9" or c < "0"), None) else True


def is_number_chinese(text):
    ### Determine whether the string is numbers and Chinese
    pattern = re.compile(r"^[\d一-龥]+$")
    match = re.match(pattern, text)
    return match is not None


def is_chinese_include_number(text):
    ### Determine whether the string is pure Chinese or Chinese containing numbers
    pattern = re.compile(r"^[一-龥]+[\d一-龥]*$")
    match = re.match(pattern, text)
    return match is not None


def is_scientific_notation(string):
    # 科学计数法的正则表达式
    pattern = r"^[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?$"
    # 使用正则表达式匹配字符串
    match = re.match(pattern, str(string))
    # 判断是否匹配成功
    if match is not None:
        return True
    else:
        return False


def is_valid_ipv4(address):
    """Check if the address is a valid IPv4 address."""
    pattern = re.compile(
        r"^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\."
        r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\."
        r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\."
        r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    )
    return pattern.match(address) is not None


def extract_content(long_string, s1, s2, is_include: bool = False) -> Dict[int, str]:
    # extract text
    match_map = {}
    start_index = long_string.find(s1)
    while start_index != -1:
        if is_include:
            end_index = long_string.find(s2, start_index + len(s1) + 1)
            extracted_content = long_string[start_index : end_index + len(s2)]
        else:
            end_index = long_string.find(s2, start_index + len(s1))
            extracted_content = long_string[start_index + len(s1) : end_index]
        if extracted_content:
            match_map[start_index] = extracted_content
        start_index = long_string.find(s1, start_index + 1)
    return match_map


def extract_content_open_ending(long_string, s1, s2, is_include: bool = False):
    # extract text  open ending
    match_map = {}
    start_index = long_string.find(s1)
    while start_index != -1:
        if long_string.find(s2, start_index) <= 0:
            end_index = len(long_string)
        else:
            if is_include:
                end_index = long_string.find(s2, start_index + len(s1) + 1)
            else:
                end_index = long_string.find(s2, start_index + len(s1))
        if is_include:
            extracted_content = long_string[start_index : end_index + len(s2)]
        else:
            extracted_content = long_string[start_index + len(s1) : end_index]
        if extracted_content:
            match_map[start_index] = extracted_content
        start_index = long_string.find(s1, start_index + 1)
    return match_map


def str_to_bool(s):
    if s.lower() in ("true", "t", "1", "yes", "y"):
        return True
    elif s.lower().startswith("true"):
        return True
    elif s.lower() in ("false", "f", "0", "no", "n"):
        return False
    else:
        return False


def _to_str(x, charset="utf8", errors="strict"):
    if x is None or isinstance(x, str):
        return x

    if isinstance(x, bytes):
        return x.decode(charset, errors)

    return str(x)


def remove_trailing_punctuation(s):
    """Remove trailing punctuation from a string."""
    punctuation = set(string.punctuation)
    chinese_punctuation = {
        "。",
        "，",
        "！",
        "？",
        "；",
        "：",
        "“",
        "”",
        "‘",
        "’",
        "（",
        "）",
        "【",
        "】",
        "—",
        "…",
        "《",
        "》",
    }
    punctuation.update(chinese_punctuation)
    while s and s[-1] in punctuation:
        s = s[:-1]

    return s


zh_punctuation = '，。！？；：“”‘’()[]{}《》【】〔〕〈〉〖〗「」『』﹁﹂﹃﹄《》「」『』〝〞…'
zh_punctuation_set = {c for c in zh_punctuation}
en_punctuation = string.punctuation
en_punctuation_set = {c for c in en_punctuation}


def determine(text):
    return "en"
    # zh_count = count_zh_punctuation(text)
    # en_count = count_en_punctuation(text)
    # if zh_count > en_count:
    #     return "zh"
    # elif en_count > zh_count:
    #     return "en"
    # else:
    #     return "en"


def count_zh_punctuation(text):
    count = 0
    for char in text:
        if char in zh_punctuation_set:
            count += 1
    return count


def count_en_punctuation(text):
    count = 0
    for char in text:
        if char in en_punctuation_set:
            count += 1
    return count

def is_markdown(text: str) -> bool:
    """
    判断给定的文本是否可能是Markdown格式。

    这个函数通过查找文本中是否存在多个Markdown特有语法元素来做判断。
    如果文本中包含以下任何一种或多种常见的Markdown元素，则认为其是Markdown。
    它使用启发式方法，不保证100%准确，但能覆盖大多数常见情况。

    Args:
        text (str): 要检查的文本字符串。

    Returns:
        bool: 如果文本包含明显的Markdown语法，则返回True；否则返回False。
    """
    if not isinstance(text, str) or not text.strip():
        # 空字符串或只包含空白字符的字符串不认为是Markdown
        return False

    # 定义常见的Markdown语法模式
    # 注意：这些模式是用来“检测”Markdown特征的，不是为了完整解析。
    # 它们被设计成足够独特，以减少误报。

    # 块级元素模式 (通常出现在行的开头，所以用re.match)
    block_patterns = {
        "heading_atx": r"^\s*#+\s.+",                  # ATX 风格标题: # Heading, ## Subheading
        "heading_setext_underline": r"^(?:-|=){2,}\s*$", # Setext 风格标题下划线: === 或 --- (需要前一行有文本)
        "unordered_list": r"^\s*[\*-+]\s.+",            # 无序列表: - item, * item, + item
        "ordered_list": r"^\s*\d+\.\s.+",               # 有序列表: 1. item, 2. item
        "blockquote": r"^\s*>\s.+",                     # 引用: > Quote
        "code_fence": r"^\s*(```|~~~)[a-zA-Z]*\s*$",    # 代码块: ```python, ~~~
        "horizontal_rule": r"^\s*(---|___|\*\*\*)\s*$", # 水平线: ---, ***, ___
    }

    # 行内元素模式 (可以出现在文本的任何位置，所以用re.search)
    inline_patterns = {
        "inline_code": r"`[^`]+`",                      # 行内代码: `code`
        "link": r"\[[^\]]+\]\([^\)]+\)",                # 链接: [text](url)
        "image": r"!\[[^\]]*\]\([^\)]+\)",              # 图片: ![alt](url)
        "bold_asterisk": r"\*\*[^*\s][^*]*[^*\s]\*\*",  # 加粗: **bold** (避免匹配** 或 ** **这种不规范的)
        "bold_underscore": r"__[^_\s][^_]*[^_\s]__",    # 加粗: __bold__
        "italic_asterisk": r"\*[^*\s][^*]*[^*\s]\*",    # 斜体: *italic*
        "italic_underscore": r"_[^_\s][^_]*[^_\s]_",    # 斜体: _italic_
    }

    matched_block_types = set()
    matched_inline_types = set()
    total_inline_matches = 0

    lines = text.splitlines()

    # 检查块级元素
    for i, line in enumerate(lines):
        for name, pattern in block_patterns.items():
            if re.match(pattern, line):
                # 对Setext标题进行额外检查，确保它前面有一行非空文本
                if name == "heading_setext_underline":
                    if i > 0 and lines[i-1].strip():
                        matched_block_types.add(name)
                else:
                    matched_block_types.add(name)

    # 检查行内元素
    for name, pattern in inline_patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            matched_inline_types.add(name)
            total_inline_matches += len(matches)

    # 启发式判断逻辑：
    # 1. 如果存在任何块级Markdown元素，则非常可能就是Markdown。
    if matched_block_types:
        return True

    # 2. 如果没有块级元素，但存在多种不同类型的行内Markdown元素，也很有可能。
    #    例如：同时有链接和加粗。
    if len(matched_inline_types) >= 2:
        return True

    # 3. 如果只有一种类型的行内元素，但数量较多，也可能意味着是Markdown。
    #    例如：文本中多处使用了 **加粗**。
    if len(matched_inline_types) == 1 and total_inline_matches >= 3:
        return True

    # 4. 如果匹配到的元素总数很少，或者没有明显特征，则认为不是Markdown。
    return False


def is_str_list(origin) -> bool:
    return isinstance(origin, list) and not any(item for item in origin if not isinstance(item, str))
