import logging
import re
from typing import Any
import json

from pympler import asizeof

from derisk.util.string_utils import determine

MODEL_CONTEXT_LENGTH = {
    "aistudio/DeepSeek-V3": 64000,
    "aistudio/DeepSeek-R1": 64000,
    "aistudio/QwQ-32B": 64000,
}
COMP_RATE = {
    "math": 1.2,
    "code": 3.67,
    "zh": 1.86,
    "en": 2
}


logger = logging.getLogger(__name__)

def _get_object_bytes(obj: Any) -> int:
    """Get the bytes of a object in memory

    Args:
        obj (Any): The object to return the bytes
    """
    return asizeof.asizeof(obj)

def calculate_total_tokens(retrieved_memories):
    """Calculate the total number of tokens in the retrieved memories."""
    try:
        memory_texts = "".join(
            [retrieved_memory.raw_observation for retrieved_memory in retrieved_memories]
        )
        return calculate_tokens(memory_texts)
    except Exception as e:
        memories = [retrieved_memory.raw_observation for retrieved_memory in
         retrieved_memories]
        logger.error(f"Calculate total tokens failed current memories:{memories}, {e}")
        return 0

def calculate_tokens(text: str):
    """Calculate the number of tokens in the texts."""
    lang = determine(text)
    logger.info(
        f"Language detected: {lang}, "
        f"Compression rate: {COMP_RATE[lang]}"
    )
    return len(text) / COMP_RATE[lang]

def calculate_tokens_by_tiktoken(text: str):
    """Calculate the number of tokens in the texts."""
    try:
        import tiktoken
        ENCODING = tiktoken.get_encoding("cl100k_base")
        logger.info(
            "tiktoken installed, using it to count tokens, tiktoken will download "
            "tokenizer from network, also you can download it and put it in the "
            "directory of environment variable TIKTOKEN_CACHE_DIR"
        )
        return len(ENCODING.encode(text))
    except ImportError:
        logger.warn("tiktoken not installed, cannot count tokens")
        return None



def get_agent_llm_context_length(model_list: str) -> int:
    default_length = 32000
    if not model_list:
        return default_length
    if isinstance(model_list, str):
        try:
            model_list = json.loads(model_list)
        except Exception:
            return default_length
    return MODEL_CONTEXT_LENGTH.get(model_list[0], default_length)


def detect_text_type(text: str) -> str:
    """
    检测给定文本的类型：'code'（代码）、'data'（数据，包括监控数据）或 'plain_text'（纯文本）。

    Args:
        text: 要检测的字符串。

    Returns:
        字符串，表示文本的类型 ('code', 'data', 'plain_text')。
    """
    if not text or not text.strip():
        return "plain_text"  # 空白或只含空白的文本视为纯文本

    lines = text.splitlines()
    num_lines = len(lines)
    total_chars = len(text)

    # --- 1. 尝试检测“数据”类型 ---

    # 1.1 尝试解析为 JSON
    try:
        json.loads(text)
        return "data"
    except json.JSONDecodeError:
        pass

    # 1.3 检查是否为 CSV 格式
    # 简单的启发式：多行，且每行都有相似数量的逗号
    if num_lines > 1:
        first_line_commas = lines[0].count(',')
        if first_line_commas > 0:
            similar_comma_lines = sum(
                1 for line in lines if line.count(',') == first_line_commas)
            # 如果超过70%的行有相同数量的逗号，可能是CSV
            if similar_comma_lines / num_lines > 0.7:
                return "data"

    # 1.4 检查监控数据/日志模式
    # 常见的时间戳模式
    timestamp_pattern = r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?(?:Z|[+-]\d{2}:\d{2})?'
    # 常见日志/监控关键字和键值对模式
    monitoring_keywords = ['timestamp', 'level', 'metric', 'value', 'error', 'latency',
                           'CPU', 'memory', 'disk', 'status', 'response_time',
                           'service', 'host']
    key_value_pattern = r'\b\w+[:=][\'"]?\S+[\'"]?'  # 简单键值对，如 'key:value' 或 'key="value"'

    timestamp_lines = sum(1 for line in lines if re.search(timestamp_pattern, line))
    key_value_matches = sum(
        1 for line in lines for kw in monitoring_keywords if kw in line) + \
                        sum(1 for line in lines if re.search(key_value_pattern, line))

    # 如果有大量的行包含时间戳或监控关键字/键值对
    if (num_lines > 3 and timestamp_lines / num_lines > 0.3) or \
            (num_lines > 3 and key_value_matches / num_lines > 0.4) or \
            (key_value_matches > 5 and total_chars > 50):  # 至少5个键值对且文本较长
        return "data"

    # --- 2. 尝试检测“代码”类型 ---

    # 2.1 常见编程语言关键字
    code_keywords = [
        'def ', 'class ', 'import ', 'from ', 'return ', 'if ', 'else ', 'elif ',
        'for ', 'while ', 'try ', 'except ', 'finally ',  # Python
        'function ', 'var ', 'const ', 'let ', 'async ', 'await ', 'new ', 'this ',
        'console.log',  # JavaScript
        'public ', 'private ', 'protected ', 'static ', 'void ', 'int ', 'String ',
        'System.out.println',  # Java/C#
        'include ', '#define ', 'struct ', 'union ', 'typedef ', 'cout <<', 'cin >>',
        # C/C++
        'package ', 'func ', 'go '  # Go
    ]

    # 2.2 常见代码结构符号
    code_punctuation = ['{', '}', '(', ')', '[', ']', ';', ':', '=', '->', '=>', '//',
                        '#', '/*', '*/']

    keyword_count = sum(text.lower().count(kw.lower()) for kw in code_keywords)
    punctuation_count = sum(text.count(p) for p in code_punctuation)

    # 2.3 检查代码特有特征
    has_indentation = any(
        line.startswith('    ') or line.startswith('\t') for line in lines if
        line.strip())
    has_comments = any(line.strip().startswith('//') or line.strip().startswith(
        '#') or '/*' in line or '*/' in line for line in lines)

    # 启发式：如果关键字和标点符号数量都较高，且有缩进或注释，则倾向于代码
    if keyword_count > total_chars * 0.005 and punctuation_count > total_chars * 0.01:  # 关键字和标点符号密度
        if has_indentation or has_comments or num_lines > 5:  # 代码通常有多行且有结构
            return "code"

    # 另一种代码判断：如果包含一些非常强的代码特征，即使密度不高
    strong_code_indicators = ['lambda ', ' await ', 'yield ', 'class ', 'def ',
                              'import ', 'function ', '=>']
    if any(ind in text for ind in strong_code_indicators):
        return "code"

    return "plain_text"


if __name__ == "__main__":
    print("--- 代码示例 ---")
    python_code = """
    def factorial(n):
        if n == 0:
            return 1
        else:
            return n * factorial(n-1)

    class MyClass:
        def __init__(self, value):
            self.value = value

    # Example usage
    result = factorial(5)
    print(f"The factorial is: {result}")
    """
    print(f"Python Code:\n{detect_text_type(python_code)}\n")  # 预期: code

    # js_code = """
    # const express = require('express');
    # const app = express();
    # const port = 3000;
    #
    # app.get('/', (req, res) => {
    #   res.send('Hello World!');
    # });
    #
    # app.listen(port, () => {
    #   console.log(`App listening at http://localhost:${port}`);
    # });
    # """
    # print(f"JavaScript Code:\n{detect_text_type(js_code)}\n")  # 预期: code
    #
    # print("--- 数据示例 ---")
    # json_data = """
    # {
    #   "timestamp": "2023-10-27T10:30:00Z",
    #   "level": "INFO",
    #   "metric": "cpu_usage",
    #   "value": 0.85,
    #   "service": "backend-api",
    #   "metadata": {
    #     "host": "server-01",
    #     "region": "us-east-1"
    #   }
    # }
    # """
    # print(f"JSON Data:\n{detect_text_type(json_data)}\n")  # 预期: data
    #
    # yaml_data = """
    # database:
    #   host: localhost
    #   port: 5432
    #   user: admin
    #   password: secure_password
    # services:
    #   api:
    #     enabled: true
    #     version: v1.2.0
    # """
    # print(f"YAML Data:\n{detect_text_type(yaml_data)}\n")  # 预期: data
    #
    csv_data = """
    name,age,city
    Alice,30,New York
    Bob,24,London
    Charlie,35,Paris
    """
    print(f"CSV Data:\n{detect_text_type(csv_data)}\n")  # 预期: data

    log_data = """
    2023-10-27 10:30:01 INFO  [main] com.example.App - Starting application...
    2023-10-27 10:30:02 DEBUG [http-nio-8080] com.example.Api - Request received from 192.168.1.100 for /users
    2023-10-27 10:30:03 WARN  [db-pool] com.example.Db - Database connection pool running low. Connections: 5/20
    2023-10-27 10:30:04 ERROR [scheduler] com.example.Service - Failed to process job_id=123. Error: Timeout
    """
    print(f"Log Data:\n{detect_text_type(log_data)}\n")  # 预期: data

    monitoring_output = """
    # HELP node_cpu_seconds_total Total user and system CPU seconds spent.
    # TYPE node_cpu_seconds_total counter
    node_cpu_seconds_total{cpu="0",mode="idle"} 12345.67
    node_cpu_seconds_total{cpu="0",mode="system"} 890.12
    node_cpu_seconds_total{cpu="1",mode="user"} 5432.10
    """
    print(
        f"Monitoring Data (Prometheus style):\n{detect_text_type(monitoring_output)}\n")  # 预期: data

    print("--- 纯文本示例 ---")
    plain_text = """
    这是一段普通的中文文本，描述了关于人工智能和自然语言处理的发展趋势。
    它不包含任何代码结构，也没有像监控数据那样的格式化内容。
    仅仅是一些日常的描述性文字。
    """
    print(f"Plain Text (Chinese):\n{detect_text_type(plain_text)}\n")  # 预期: plain_text

    short_text = "Hello, world!"
    print(f"Short Plain Text:\n{detect_text_type(short_text)}\n")  # 预期: plain_text

    simple_list = "Item 1\nItem 2\nItem 3"
    print(f"Simple List:\n{detect_text_type(simple_list)}\n")  # 预期: plain_text

    ambiguous_text = "This is a simple text with a 'key: value' pattern inside. But it's not structured data."
    print(f"Ambiguous Text:\n{detect_text_type(ambiguous_text)}\n")  # 预期: plain_text

    yaml_like_but_plain = """
    hello: world
    This is a sentence.
    """
    print(
        f"YAML-like but plain:\n{detect_text_type(yaml_like_but_plain)}\n")  # 预期: plain_text or data (depending on strictness)
    # 调整后，对于这种多行但只有第一行像YAML的，会倾向于plain_text，除非yaml_data解析成功。

    code_like_but_plain = """
    I am talking about a 'class' of problems,
    and how we 'import' ideas from other fields.
    This is not programming.
    """
    print(
        f"Code-like words, but plain:\n{detect_text_type(code_like_but_plain)}\n")  # 预期: plain_text

    empty_text = ""
    print(f"Empty Text:\n{detect_text_type(empty_text)}\n")  # 预期: plain_text

    whitespace_text = "   \n  \t "
    print(
        f"Whitespace Only Text:\n{detect_text_type(whitespace_text)}\n")  # 预期: plain_text
