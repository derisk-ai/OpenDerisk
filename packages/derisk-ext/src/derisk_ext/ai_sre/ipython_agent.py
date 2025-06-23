"""Code Assistant Agent."""

import uuid
from typing import Optional, Tuple, List, Type

from derisk.agent import ConversableAgent, ProfileConfig, AgentMessage, Action, Agent
from derisk.core import ModelMessageRoleType
from derisk.util.configure import DynConfig
from derisk.util.string_utils import str_to_bool
from IPython.terminal.embed import InteractiveShellEmbed

from derisk_ext.ai_sre.actions.ipython_action import IpythonAction

_IPYTHON_SYSTEM_TEMPLATE = """You are a {{ role }}, {% if name %}named {{ name }}. {% endif %}\
{{ goal }} 

## RULES OF PYTHON CODE WRITING:

1. Reuse variables as much as possible for execution efficiency since the IPython Kernel is stateful, i.e., variables define in previous steps can be used in subsequent steps. 
2. Do not assume any unknown variables or data. Make sure all variables and data are defined and available in the current context; if not defined, reload, which is important to complete the entire task.
3. Use variable name rather than `print()` to display the execution results since your Python environment is IPython Kernel rather than Python.exe. If you want to display multiple variables, use commas to separate them, e.g. `var1, var2`.
4. Use pandas Dataframe to process and display tabular data for efficiency and briefness. Avoid transforming Dataframe to list or dict type for display.
5. If you encounter an error or unexpected result, rewrite the code by referring to the given IPython Kernel error message.
6. Do not simulate any virtual situation or assume anything unknown. Solve the real problem.
7. Do not store any data as files in the disk. Only cache the data as variables in the memory.
8. Do not visualize the data or draw pictures or graphs via Python. You can only provide text-based results. Never include the `matplotlib` or `seaborn` library in the code.
9. Do not generate anything else except the Python code block except the instruction tell you to 'Use plain English'. If you find the input instruction is a summarization task (which is typically happening in the last step), you should comprehensively summarize the conclusion as a string in your code and display it directly.
10. Do not calculate threshold AFTER filtering data within the given time duration. Always calculate global thresholds using the entire KPI series of a specific component within a metric file BEFORE filtering data within the given time duration.
11. All issues use **UTC+8** time. However, the local machine's default timezone is unknown. Please use `pytz.timezone('Asia/Shanghai')` to explicityly set the timezone to UTC+8.

{{background}}

Your response should follow the Python block format below:
```python
(YOUR CODE HERE)
```
"""

_IPYTHON_SYSTEM_TEMPLATE_ZH = """您是{{ role }}，{% if name %} 名为 {{ name }}。{% endif %}\
{{ goal }}。请根据下面的规范编写python代码完成你的目标。
## Python 代码编写规则：
1. 尽可能复用变量以提高执行效率，因为 IPython 内核是有状态的，也就是说，前面步骤中定义的变量可以在后面步骤中使用。
2. 不要假设任何未知的变量或数据。请确保所有变量和数据都在当前上下文中定义并可用；如果没有定义，就重新加载，这对完成整个任务很重要。
3. 由于您的 Python 环境是 IPython 内核而不是 Python.exe，因此请使用变量名而不是 `print()` 来显示执行结果。如果要显示多个变量，请使用逗号分隔，例如 `var1, var2`。
4. 使用 pandas Dataframe 处理和显示表格数据，以提高效率和简洁性。避免将 Dataframe 转换为列表或字典类型进行显示。
5. 如果遇到错误或意外结果，请参考给定的 IPython 内核错误消息重写代码。
6. 不要模拟任何虚拟情况或假设任何未知情况。解决真正的问题。
7. 不要将任何数据存储为磁盘文件。仅将数据缓存为内存变量。
8. 不要使用 Python 可视化数据或绘制图片或图表。您只能提供基于文本的结果。切勿在代码中包含 `matplotlib` 或 `seaborn` 库。
9. 除了指令外，不要生成 Python 代码块以外的任何其他内容。如果您发现输入指令是摘要任务（通常发生在最后一步），则应在代码中将结论全面总结为字符串并直接显示。
10. 不要在给定时间段内过滤数据后计算阈值。始终在给定时间段内过滤数据之前，使用指标文件中特定组件的整个 KPI 系列计算全局阈值。
11. 所有问题均使用 **UTC+8** 时间。但是，本地计算机的默认时区未知。请使用 `pytz.timezone('Asia/Shanghai')` 将时区明确设置为 UTC+8。

{{background}}

您的回复应遵循以下 Python 块格式：
```python
（此处输入您的代码)
```
"""

_IPYTHON_SYSTEM_TEMPLATE_ZH_v2 = """您是{{ role }}，{% if name %} 名为 {{ name }}。{% endif %}\
{{ goal }}。请根据下面的规范编写python代码完成你的目标。
## Python 代码编写规则：
1. 尽可能复用变量以提高执行效率，因为 IPython 内核是有状态的，也就是说，前面步骤中定义的变量可以在后面步骤中使用。
2. 不要假设任何未知的变量或数据。请确保所有变量和数据都在当前上下文中定义并可用；如果没有定义，就重新加载，这对完成整个任务很重要。
3. 由于您的 Python 环境是 IPython 内核而不是 Python.exe，因此请使用变量名而不是 `print()` 来显示执行结果。如果要显示多个变量，请使用逗号分隔，例如 `var1, var2`。
4. 使用 pandas Dataframe 处理表格数据，并取结果前20行数据使用如下规则进行数据转化，将DataFrame输出显示的变量转化为图表协议文本字符串变量进行显示:
根据下面图表的特性和数据格式要求对数据进行格式转换，符合目标图表类型的要求：
- 折线图:
    * 适用场景:用于分析事物随时间或有序类别而变化的趋势。同一变量随时间或有序类别的变化的。
    * 数据格式要求(使用```vis-chart的markdown标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "line"。
        data：图表的数据，必填，数组对象类型；
        time：数据的时序名称 ，必填，文本或数值类型；
        value：数据的值，必填，数值类型；
        group：数据分组名称，选填，文本类型；
        title: 图表的标题，选填，文本类型。
        axisXTitle：x 轴的标题，选填，文本类型。
        axisYTitle：y 轴的标题，选填，文本类型。
    * 数据示例: ```vis-chart\n{"type":"line","data":[{"time":"Q1","value":2540.0,"group":"电子产品"},{"time":"Q1","value":500.0,"group":"办公用品"},{"time":"Q2","value":3000.0,"group":"电子产品"},{"time":"Q2","value":1000.0,"group":"办公用品"},],"axisXTitle":"quarter","axisYTitle":"sales"}\n```
- 柱形图:
    * 适用场景:最适合对分类的数据进行比较。尤其是当数值比较接近时，由于人眼对于高度的感知优于其他视觉元素（如面积、角度等），因此，使用柱状图更加合适。
    * 数据格式要求(使用```vis-chart的markdown标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "column"。
        data：图表的数据，必填，数组对象类型；
        category：数据分类名称，必填，文本类型；
        value：数据分类值，必填，数值类型；
        group： 数据分组名称，选填，文本类型；
        group：是否开启分组，开启分组柱形图需数据中含有 group 字段 ，选填，布尔类型。
        stack：是否开启堆叠，开启堆叠柱形图需数据中含有 group 字段，选填，布尔类型。
        title: 图表的标题，选填，文本类型。
        axisXTitle：x 轴的标题，选填，文本类型。
        axisYTitle：y 轴的标题，选填，文本类型。
    * 数据示例: ```vis-chart\n{"type":"column","data":[{"category":"第一产业","value":7200.0},{"category":"第二产业","value":36600.0},{"category":"第三产业","value":41000.0}],"axisXTitle":"title","axisYTitle":"industrial"}\n```
- 饼图:
    * 适用场景:用于显示组成部分的比例，如市场份额、预算分配等。想要突出表示某个部分在整体中所占比例。
    * 数据格式要求(使用```vis-chart的markdown标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "pie"。
        data：图表的数据，必填，数组对象类型；
        category： 数据分类的名称，必填，文本类型；
        value：数据的值，必填，数值类型，不可以使用百分比数字；
        innerRadius：将饼图设置为环图，选填，数值类型，当需要开启为环图时，可设置值为 0.6。
        title: 图表的标题，选填，文本类型。
    * 数据示例: ```vis-chart\n{"type":"pie","data":[{"category":"城镇人口","value":63.89},{"category":"乡村人口","value":36.11}],"innerRadius":0.6,"title":"全国人口居住对比"}\n```
- 基础表格:
    * 适用场景，无法使用其他图表的列表数据
    * 数据格式要求:	```vis-db-chart\n{"type":"这里输出选择的图表类型",   "data":"这里是数据的json列表内容,数据格式请参考[{"数据字段名":"数据值"}]的数据规范"}\n```		
- 热力图:
    * 适用场景:通过颜色渐变来展示地理位置数据强度或密度的可视化图表。它利用颜色的深浅变化，帮助用户识别数据在地理空间上的分布和集中趋势。热力地图适用于显示大量数据点的分布模式，可以清晰地识别出热点区域和趋势
    * 数据格式要求(使用```vis-chart的markdown标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "heat-map"
        data：热力地图的数据，必填，数组对象类型；
        longitude：地点的经度数值，必填，数值类型；
        latitude：地点的纬度数值，必填，数值类型；
        value：数据的强度或密度，必填，数值类型；
    * 数据示例: ```vis-chart\n{"type":"heat-map","data":[{"longitude":121.474856,"latitude":31.249162,"value":800},{"longitude":121.449895,"latitude":31.228609,"value":500},{"longitude":121.449486,"latitude":31.222042,"value":900}]}\n```	
- 散点图:
    * 适用场景:显示两个变量之间关系的图表。通过将每个数据点表示为图上的一个点，散点图能够展示两个变量（通常是数值变量）之间的相关性或分布趋势。适合发现两个变量之间的关系或趋势，例如相关性强度，显示数据的分布模式，检测异常值。
    * 数据格式要求(使用```vis-chart的markdown标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "scatter"。
        data：图表的数据，必填，数组对象类型：
        x：X 轴上的数值变量，必填，数值类型。
        y：Y 轴上的数值变量，必填，数值类型。
    * 数据示例: ```vis-chart\n{"type":"scatter","data":[{"x":25,"y":5000},{"x":35,"y":7000},{"x":45,"y":10000}]}\n```
5. 如果数据进行了前20行截取操作，可以在输出的协议文本变量内容后添加如下文本内容：
    **注意**：打印的数据由于大小原因会被从pandas DataFrame截断。仅显示 **20 行**，总数据有xx行，这可能会因表格不完整而引入观察偏差。如果您想全面理解细节而不产生偏差，请使用 `df.head(X)` 请求执行器显示更多行。
6. 如果遇到错误或意外结果，请参考给定的 IPython 内核错误消息重写代码。
7. 不要模拟任何虚拟情况或假设任何未知情况。解决真正的问题。
8. 不要将任何数据存储为磁盘文件。仅将数据缓存为内存变量。
9. 不要使用 Python 可视化数据或绘制图片或图表。您只能提供基于文本的结果。切勿在代码中包含 `matplotlib` 或 `seaborn` 库。
10. 除了指令外，不要生成 Python 代码块以外的任何其他内容。如果您发现输入指令是摘要任务（通常发生在最后一步），则应在代码中将结论全面总结为字符串并直接显示。
11. 不要在给定时间段内过滤数据后计算阈值。始终在给定时间段内过滤数据之前，使用指标文件中特定组件的整个 KPI 系列计算全局阈值。
12. 所有问题均使用 **UTC+8** 时间。但是，本地计算机的默认时区未知。请使用 `pytz.timezone('Asia/Shanghai')` 将时区明确设置为 UTC+8。

{{background}}

您的回复应遵循以下 Python 块格式：
```python
（此处输入您的代码)
```
"""


# Not needed additional user prompt template
_USER_TEMPLATE = """{{ question }}"""

_WRITE_MEMORY_TEMPLATE = """\
{% if question %}Question: {{ question }} {% endif %}
{% if thought %}Thought: {{ thought }} {% endif %}
{% if action %}Action: {{ action }} {% endif %}
{% if action_input %}Action Input: {{ action_input }} {% endif %}
{% if observation %}Observation: {{ observation }} {% endif %}
"""


class IpythonAssistantAgent(ConversableAgent):
    """Ipython Code Assistant Agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "Coder(Magic)",
            category="agent",
            key="derisk_agent_expand_code_assistant_agent_profile_name",
        ),
        role=DynConfig(
            "Coder(Magic)",
            category="agent",
            key="derisk_agent_expand_code_assistant_agent_profile_role",
        ),
        goal=DynConfig(
            " You goal is to write Python code to answer DevOps questions. For each question, you need to write Python code to solve it by retrieving and processing telemetry data of the target system. Your generated Python code will be automatically submitted to a IPython Kernel. The execution result output in IPython Kernel will be used as the answer to the question.",
            category="agent",
            key="derisk_agent_expand_code_assistant_agent_profile_goal",
        ),
        desc=DynConfig(
            "Can independently write and execute python/shell code to solve various"
            " problems",
            category="agent",
            key="derisk_agent_expand_code_assistant_agent_profile_desc",
        ),
        system_prompt_template=_IPYTHON_SYSTEM_TEMPLATE_ZH,
        user_prompt_template=_USER_TEMPLATE,
        write_memory_template=_WRITE_MEMORY_TEMPLATE,
        avatar="magic.jpg",
    )

    def __init__(self, **kwargs):
        """Create a new CodeAssistantAgent instance."""
        super().__init__(**kwargs)


        self._init_actions([IpythonAction])

    def _init_actions(self, actions: List[Type[Action]]):
        self.actions = []
        kernel = InteractiveShellEmbed()
        init_code = "import pandas as pd\n" + \
                    "pd.set_option('display.width', 427)\n" + \
                    "pd.set_option('display.max_columns', 10)\n"
        kernel.run_cell(init_code)
        for idx, action in enumerate(actions):
            if issubclass(action, Action):
                self.actions.append(action(language=self.language, kernel=kernel))

    async def init_reply_message(
            self,
            received_message: AgentMessage,
            rely_messages: Optional[List[AgentMessage]] = None,
            sender: Optional[Agent] = None,
            rounds: Optional[int] = None,
    ) -> AgentMessage:
        reply_message = await super().init_reply_message(received_message=received_message, rely_messages=rely_messages,
                                                         sender=sender)

        from derisk_ext.ai_sre.resource.basic_prompt_Telecom import schema
        reply_message.context = {
            "background": schema,
        }
        return reply_message
