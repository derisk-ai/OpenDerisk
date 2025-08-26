"""MemoryCondenseExtractor class."""

import logging
from typing import List, Optional

from derisk.core import LLMClient
from derisk.rag.transformer.llm_extractor import LLMExtractor
MEMORY_CONDENSE_SYSTEM_PROMPT = """你是一个专门压缩AI代理执行历史中Observation部分的系统。请仅针对Observation
后面的内容进行压缩，保留关键信息的同时减少冗余。其他部分保持不变。
特别注意，你需要识别是文本压缩还是代码压缩，当Observation包含代码时，请根据Question
中的问题来精简压缩代码，只保留与问题直接相关的部分。

示例1（文本压缩）: 输入: Question: What is the capital of France? Thoughts: I need to search 
for the capital city of France. Action: Search for "capital of France" Observation: 
The capital of France is Paris. Paris is located in northern France and is the 
country's largest city. It is a global center for art, fashion, gastronomy and 
culture. Its 19th-century cityscape is crisscrossed by wide boulevards and the River 
Seine.

输出: Observation: Paris is 
the capital of France. It's the largest city, located in northern France, known for 
art, fashion, and culture.

示例2（代码压缩）:
输入:
Question: How do I calculate the factorial of a number in Java?
Thoughts: I need to find a Java function for calculating factorial.
Action: Search for "Java factorial function"
Observation:
Here's a Java function to calculate the factorial of a number:
public class MathUtils {{
    public static long factorial(int n) {{
        if (n == 0 || n == 1) {{
            return 1;
        }} else {{
            return n * factorial(n - 1);
        }}
    }}

    public static void main(String[] args) {{
        int num = 5;
        long result = factorial(num);
        System.out.println("The factorial of " + num + " is " + result);
    }}

    // Additional helper method
    public static boolean isPrime(int n) {{
        if (n < 2) {{
            return false;
        }}
        for (int i = 2; i <= Math.sqrt(n); i++) {{
            if (n % i == 0) {{
                return false;
            }}
        }}
        return true;
    }}
}}
输出:
Observation:
public class MathUtils {{
    public static long factorial(int n) {{
        if (n == 0 || n == 1) {{
            return 1;
        }} else {{
            return n * factorial(n - 1);
        }}
    }}

    public static void main(String[] args) {{
        int num = 5;
        long result = factorial(num);
        System.out.println("The factorial of " + num + " is " + result);
    }}
}}

{text}
"""


logger = logging.getLogger(__name__)


class MemoryCondenseExtractor(LLMExtractor):
    """MemoryCondenseExtractor class."""

    def __init__(
        self, llm_client: LLMClient, model_name: str, prompt: Optional[str] = None
    ):
        """Initialize the MemoryCondenseExtractor."""
        self._prompt = prompt or MEMORY_CONDENSE_SYSTEM_PROMPT
        super().__init__(llm_client, model_name, self._prompt)

    def _parse_response(self, text: str, limit: Optional[int] = None) -> str:
        return text
