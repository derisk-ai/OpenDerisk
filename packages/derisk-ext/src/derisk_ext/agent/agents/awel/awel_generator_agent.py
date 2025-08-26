import json
import logging
from typing import List

from derisk._private.config import Config
from derisk.agent import ConversableAgent, ProfileConfig, AgentMessage, ActionOutput, Resource
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.resource import get_resource_manager
from derisk.core import ModelMessageRoleType
from derisk.core.awel import DAG
from derisk.util.json_utils import find_json_objects
from derisk.util.template_utils import render
from derisk_ext.agent.agents.awel.generate import build_schema, build_ability, build_model_awel
from derisk_serve.agent.db import GptsConversationsDao
from derisk_serve.agent.db.gpts_app import GptsApp, GptsAppDao
from derisk_serve.flow.service.service import Service as FlowService

CFG = Config()

logger: logging.Logger = logging.getLogger("awel")


class AwelGeneratorAgent(ConversableAgent):
    profile: ProfileConfig = ProfileConfig(
        # Agent角色 需要全局唯一 建议跟类名保持一致
        role="AwelGeneratorAgent",

        # 这里是默认值 在Nex产品配置的Agent名会覆盖到这里
        name="生成Awel SOP的Agent",

        # Agent描述
        desc="系统内置Agent，用于根据用户输入生成Awel SOP。",

        # 系统提示词模板 这里是默认值 若在Nex产品配置了系统提示词，会覆盖到这里
        system_prompt_template="""
你是一个智能助手，请将用户问题拆解为可执行的流程图。

## 图元素Schema
{{schema}}


## 可用能力清单（只能选用下列工具）
{{ability}}
**注意：只能使用上述工具！若无匹配工具或参数不足需终止任务并说明原因**

## 输出格式约束
严格按以下JSON格式输出，确保可直接解析：
{
  "reason": "解释拆解/未拆解出流程图的原因",
  "items"?: [{
    "type": "图元素类型。只能从`图元素Schema`中选择"
    "data": "图元素需要的信息。必须严格满足`图元素Schema`中对应类型的property描述"
  }]
        """
    )

    async def generate_reply(self, received_message: AgentMessage, **kwargs) -> AgentMessage:
        logger.info(f"AwelGeneratorAgent:{self.agent_context.gpts_app_code}|{self.agent_context.gpts_app_name}: in")
        gpts_app: GptsApp = GptsAppDao().app_detail(received_message.context["agent_id"])
        resource: Resource = get_resource_manager().build_resource(gpts_app.team_context.resources)

        # system prompt
        system_prompt: str = render(self.profile.system_prompt_template.strip(), {
            "ability": await build_ability(resource=resource, **kwargs),
            "schema": await build_schema(),
            "example_query": received_message.context.get("example_query", None)
        })
        messages: list[AgentMessage] = [AgentMessage(content=system_prompt, role=ModelMessageRoleType.SYSTEM)]

        # history
        conversations = GptsConversationsDao().get_like_conv_id_asc(session_id_from_conv_id(self.agent_context.conv_id))
        for conversation in conversations:
            gpts_messages: List[GptsMessage] = await self.memory.gpts_memory.get_messages(conversation.conv_id)
            for gpts_message in gpts_messages:
                if not gpts_message.content:
                    continue
                messages.append(AgentMessage(content=gpts_message.content, role=ModelMessageRoleType.HUMAN
                if gpts_message.sender == "Human" else ModelMessageRoleType.AI))

        # 调用模型
        reply_message: AgentMessage = await self.init_reply_message(received_message=received_message)
        res_thinking, res_content, model_name = await self.thinking(messages=messages, reply_message_id=reply_message.message_id, recived_message=received_message)
        reply_message.content = res_content
        reply_message.thinking = res_thinking
        reply_message.model_name = model_name

        # 结果解析
        parsed_json = find_json_objects(res_content)

        # 生成dag
        dag: DAG = build_model_awel(
            parsed_json[-1], flow_service=get_flow_service(), app_code=gpts_app.app_code,
            user_name=self.agent_context.extra['user_code'] if self.agent_context.extra and "user_code" in self.agent_context.extra else "")
        reply_message.action_report = ActionOutput.from_dict({
            "content": json.dumps({
                "dag_id": dag.dag_id,
            }, ensure_ascii=False),
        })
        logger.info(f"AwelGeneratorAgent[{self.agent_context.gpts_app_code}|{self.agent_context.gpts_app_name}]: done,"
                    f" message_id[{reply_message.message_id}], dag_id[{dag.dag_id}], mermaid:[{dag.show(mermaid=True)}]")
        return reply_message


def session_id_from_conv_id(conv_id: str) -> str:
    idx = conv_id.rfind("_")
    return conv_id[:idx] if idx else conv_id


def get_flow_service() -> FlowService:
    return FlowService.get_instance(CFG.SYSTEM_APP)
