import dataclasses
from typing import Optional, Type, Tuple, Dict, List

from derisk.agent import Resource, ResourceType
from derisk.agent.resource import ResourceParameters
from derisk.core import Chunk
from derisk.util.i18n_utils import _
CODE_CONDENSE_PROMPT =  """你是一个专门压缩代码的系统。请仅针对Observation
后面的内容进行压缩，保留关键信息的同时减少冗余。其他部分保持不变。
特别注意，你需要识别是文本压缩还是代码压缩，当Observation包含代码时，请根据Question
中的问题来精简压缩代码，只保留与问题直接相关的部分。
示例（代码压缩）:
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

TEXT_CONDENSE_PROMPT = """
你是一个专门压缩AI代理执行历史中Observation部分的系统。请仅针对Observation
后面的内容进行文本压缩，保留关键信息的同时减少冗余。其他部分保持不变。
请根据Question中的问题来精简压缩文本，只保留与问题直接相关的部分。

示例1（文本压缩）: 输入: Question: What is the capital of France? Thoughts: I need to search 
for the capital city of France. Action: Search for "capital of France" Observation: 
The capital of France is Paris. Paris is located in northern France and is the 
country's largest city. It is a global center for art, fashion, gastronomy and 
culture. Its 19th-century cityscape is crisscrossed by wide boulevards and the River 
Seine.

输出: Observation: Paris is 
the capital of France. It's the largest city, located in northern France, known for 
art, fashion, and culture.
{text}
"""

@dataclasses.dataclass
class MemoryParameters(ResourceParameters):
    enable_global_session: bool = dataclasses.field(
        default=True, metadata={"help": _("多智能体协作记忆协作模式，适用于多Agent"
                                          "协作场景，多智能体协作模式下，打开可查看所有智能体对话记忆，关闭只能看到当前智能体对话记忆"),
                                "label": _("多智能体协作记忆")}
    )
    discard_strategy: str = dataclasses.field(
        default="fifo", metadata={"help": _("记忆淘汰策略:\n"
                                            "lru:最近最少使用策略, 优先淘汰最长时间未被访问的数据\n"
                                            "fifo: 先进先出策略, 按照数据进入的顺序进行淘汰\n"
                                            "similarity:相似度策略。基于新信息与现有记忆的相似程度来决定淘汰\n"
                                            "condense: 压缩策略。通过总结或合并多条相关信息来减少占用空间"
                                            "而不是直接删除。"),
                                  "label": _("记忆淘汰策略"),
                                  "options": [{"name":"fifo","desc":"先进先出"}, {"name":"lru", "desc":"最近最少使用"}, {"name":"similarity","desc": "语义相似度"}, {"name":"condense","desc":"记忆压缩"}]}
    )
    retrieve_strategy: str = dataclasses.field(
        default="sliding_window", metadata={"help": _(
            "记忆检索策略\n"
            "semantic:语义检索, 通过当前任务目标进行语义相关度匹配\n"
            "sliding_window:滑动窗口检索，将历史对话消息按照滑动窗口大小方式进行动态返回\n"
            "keyword:关键词检索, 通过当前任务目标对记忆按照关键词进行搜索\n"
        ), "options": [{"name":"semantic","desc":"语义检索"}, {"name":"sliding_window","desc":"滑动窗口检索"}, {"name":"keyword","desc":"关键词检索"}], "label": _("记忆检索策略")
        }
    )
    top_k: int = dataclasses.field(
        default=50, metadata={"help": _("返回记忆片段数量，如果只看最近历史记忆可以将值适当调小"), "label": _("返回记忆片段数量")}
    )
    score_threshold: Optional[float] = dataclasses.field(
        default=0.0, metadata={"help": _("相似度得分阈值"), "label": _("相似度得分阈值"), "max": _("1"), "min": _("0"), "step": _("0.1")}
    )

    enable_message_condense: bool = dataclasses.field(
        default=False, metadata={"help": _("是否开启消息压缩"), "label": _("消息压缩")}
    )
    message_condense_model: Optional[str] = dataclasses.field(
        default="deepseek-v3",
        metadata={"help": _("消息压缩模型"), "label": _("压缩模型")}
    )
    message_condense_strategy: Optional[str] = dataclasses.field(
        default="text", metadata={"help": _("压缩策略"), "label": _("压缩策略")
            , "options": [
                {"name":"text","desc":"文本压缩"}, {"name":"code", "desc":"代码压缩"}
            ]}
    )
    condense_max_token: Optional[int] = dataclasses.field(
        default=5000,
        metadata={"help": _("压缩模型最大输出token"), "label": _("压缩模型最大输出token")}
    )
    message_condense_prompt: Optional[str] = dataclasses.field(
        default="""你是一个专门压缩AI代理执行历史中Observation部分的系统。请仅针对Observation
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
""", metadata={"help": _("消息压缩提示词"), "label": _("消息压缩提示词")}
    )
    enable_user_memory: bool = dataclasses.field(
        default=False, metadata={"help": _("是否开启用户记忆"),
                                "label": _("用户记忆")}
    )
    name: Optional[str] = dataclasses.field(
        default="MemoryResource", metadata={"help": _(
            "MemoryResource"
        ),
        }
    )


class MemoryResource(Resource[ResourceParameters]):
    def __init__(
        self,
        name: Optional[str] = None,
        enable_global_session: bool = False,
        discard_strategy: str = "fifo",
        retrieve_strategy: str = "semantic",
        top_k: int = 50,
        score_threshold: Optional[float] = 0.0,
        enable_message_condense: bool = False,
        message_condense_model: Optional[str] = "deepseek-v3",
        message_condense_prompt: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize a MemoryResource instance.
        Args:
            name (Optional[str]): The name of the memory resource.
            memory_params (Optional[dict]): Parameters for the memory resource.
    """
        self._name = name or "MemoryResource"
        memory_params = {
            "enable_global_session": enable_global_session,
            "discard_strategy": discard_strategy,
            "retrieve_strategy": retrieve_strategy,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "enable_message_condense": enable_message_condense,
            "message_condense_model": message_condense_model,
            "message_condense_prompt": message_condense_prompt,
            "name": self._name,
        }
        self._memory_params = MemoryParameters(**(memory_params or {}))

    @classmethod
    def type(cls) -> ResourceType:
        return ResourceType.Memory

    @property
    def name(self) -> str:
        """Return the resource name."""
        return self._name

    @property
    def memory_params(self) -> MemoryParameters:
        return self._memory_params

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[ResourceParameters]:
        """Return the resource parameters class."""
        return MemoryParameters

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[Dict]]:
        return "", {}

    async def get_resources(
        self,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
    ) -> Tuple[Optional[List[Chunk]], str, Optional[Dict]]:
        pass

    @classmethod
    def default_parameters(
        cls,
    ) -> MemoryParameters:
        """Return default parameters for the memory resource."""
        return MemoryParameters(
            enable_global_session=True,
            discard_strategy="fifo",
            retrieve_strategy="sliding_window",
            top_k=50,
            score_threshold=0.0,
            enable_message_condense=False,
            message_condense_model="deepseek-v3",
            message_condense_prompt=None,
            name="MemoryResource",
            condense_max_token=5000,
        )


