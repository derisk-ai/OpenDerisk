"""Code Assistant Agent."""

import uuid
from typing import Optional, Tuple, List, Type

from derisk.agent import ConversableAgent, ProfileConfig, AgentMessage, Action, BlankAction
from derisk.agent.core.plan.report_agent import ReportAssistantAgent
from derisk.core import ModelMessageRoleType
from derisk.util.configure import DynConfig
from derisk.util.string_utils import str_to_bool
from IPython.terminal.embed import InteractiveShellEmbed

_SYSTEM_TEMPLATE_ZH = """您是 {{ role }}，{% if name %} 名为 {{ name }}。{% endif %}\
现在，您已决定完成推理过程。现在您应该提供问题的最终分析报告。系统会向您提供可能的根本原因组件和原因的候选。您必须从提供的候选组件和原因中选择根本原因组件和原因。

## 可能的根本原因:
- CPU 使用率高
- 内存使用率高
- 网络延迟
- 网络丢包
- 磁盘 I/O 读取使用率高
- 磁盘空间使用率高
- JVM CPU 负载高
- JVM 内存溢出 (OOM)

## 可能的根本原因组件：

- apache01
- apache02
- Tomcat01
- Tomcat02
- Tomcat04
- Tomcat03
- MG01
- MG02
- IG01
- IG02
- Mysql01
- Mysql02
- Redis01
- Redis02

回想一下，问题是：{{question}}

请首先回顾你之前的推理过程，推断出该问题的确切答案。然后生成你的分析报告，确保你的分析报告包含如下三部分内容(不要使用```markdown这样的标签包裹报告内容)，同时请确保语言专业简洁，格式有条理，方便人类用户阅读：
1.根因定位信息，包含发生时间、发生的根因组件、根本原因
2.分析思路，把你的分析推理过程整理成如下格式的数据进行输出(注意确保下面数据格式中'edges'中的'source'和'target'必须是'nodes'中'name'的值,不能截取和编造)：
```vis-chart
{
  "type": "flow-diagram",
  "data": {
    "nodes": [
      { "name": "诊断步骤1" },
      { "name": "诊断步骤2" },

    ],
    "edges": [
      { "source": "诊断步骤1", "target": "诊断步骤1" },
      { "source": "诊断步骤x", "target": "诊断步骤y" },
      { "source": "诊断步骤x", "target": "诊断步骤y", "name": "诊断步骤链接逻辑原因"}
    ]
  }
}
```
3.根因推断证据链，包含推导出根因的关键证据和数据信息，确保数据来源于提供的数据.不要自行构造和篡改，但是可以对数据进行合并和精简。同时对于时序、比例等结构化的可以图表展示的数据可以考虑使用如下格式的图表进行展示,不适合如下图表类型展示的数据直接使用文本展示:
根据下面图表的特性和数据格式要求对数据进行格式转换，符合目标图表类型的要求：
- 折线图:
    * 适用场景:用于分析事物随时间或有序类别而变化的趋势。同一变量随时间或有序类别的变化的。
    * 数据格式要求(使用```vis-chart标签包裹如下内容的json数据，标签和数据之间需要换行):
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
    * 数据格式要求(使用```vis-chart标签包裹如下内容的json数据，标签和数据之间需要换行):
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
    * 数据格式要求(使用```vis-chart标签包裹如下内容的json数据，标签和数据之间需要换行):
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
    * 数据格式要求(使用```vis-chart标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "heat-map"
        data：热力地图的数据，必填，数组对象类型；
        longitude：地点的经度数值，必填，数值类型；
        latitude：地点的纬度数值，必填，数值类型；
        value：数据的强度或密度，必填，数值类型；
    * 数据示例: ```vis-chart\n{"type":"heat-map","data":[{"longitude":121.474856,"latitude":31.249162,"value":800},{"longitude":121.449895,"latitude":31.228609,"value":500},{"longitude":121.449486,"latitude":31.222042,"value":900}]}\n```	
- 散点图:
    * 适用场景:显示两个变量之间关系的图表。通过将每个数据点表示为图上的一个点，散点图能够展示两个变量（通常是数值变量）之间的相关性或分布趋势。适合发现两个变量之间的关系或趋势，例如相关性强度，显示数据的分布模式，检测异常值。
    * 数据格式要求(使用```vis-chart标签包裹如下内容的json数据，标签和数据之间需要换行):
        type：值必须为 "scatter"。
        data：图表的数据，必填，数组对象类型：
        x：X 轴上的数值变量，必填，数值类型。
        y：Y 轴上的数值变量，必填，数值类型。
    * 数据示例: ```vis-chart\n{"type":"scatter","data":[{"x":25,"y":5000},{"x":35,"y":7000},{"x":45,"y":10000}]}\n```
"""


# Not needed additional user prompt template
_USER_TEMPLATE = """"""

_WRITE_MEMORY_TEMPLATE = """\
{% if question %}Question: {{ question }} {% endif %}
{% if thought %}Thought: {{ thought }} {% endif %}
{% if action %}Action: {{ action }} {% endif %}
{% if action_input %}Action Input: {{ action_input }} {% endif %}
{% if observation %}Observation: {{ observation }} {% endif %}
"""


class DiagRportAssistantAgent(ReportAssistantAgent):
    """Ipython Code Assistant Agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "Reporter(Kevin)",
            category="agent",
            key="derisk_agent_expand_diag_reporter_agent_profile_name",
        ),
        role=DynConfig(
            "Reporter(Kevin)",
            category="agent",
            key="derisk_agent_expand_diag_reporter_agent_profile_role",
        ),
        desc=DynConfig(
            "Now, you have decided to finish your reasoning process. You should now provide the final answer to the issue. The candidates of possible root cause components and reasons are provided to you. The root cause components and reasons must be selected from the provided candidates."
            " problems",
            category="agent",
            key="derisk_agent_expand_code_assistant_agent_profile_desc",
        ),
        system_prompt_template=_SYSTEM_TEMPLATE_ZH,
        # user_prompt_template=_USER_TEMPLATE,
        write_memory_template=_WRITE_MEMORY_TEMPLATE,
        avatar="kevin.jpg",
    )
    current_goal: str = "诊断报告"

    def __init__(self, **kwargs):
        """Create a new CodeAssistantAgent instance."""
        super().__init__(**kwargs)


        self._init_actions([BlankAction])

