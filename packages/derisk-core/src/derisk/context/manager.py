import json
import logging
from typing import Optional, Type, Any

from derisk import BaseComponent, SystemApp
from derisk.component import ComponentType, T
from derisk.context.base import ContextWindow
from derisk.context.event import Event, EventType
from derisk.context.operator import Operator
from derisk.util.date_utils import current_ms
from derisk.util.logger import digest
from derisk.util.module_utils import model_scan

logger = logging.getLogger("context")
_SYSTEM_APP: Optional[SystemApp] = None


class ChatContextKey:
    """Agent会话级别的上下文key"""
    GPTS_APP_CODE: str = "gpts_app_code"  # 当前对话的主Agent(应用)app_code
    AGENT_APP_CODE: str = "agent_app_code"  # 当前Agent的ID
    CONV_SESSION_ID: str = "conv_session_id"
    CONV_ID: str = "conv_id"

    # OUTPUT_SCHEMA: str = "output_schema"  # 输出格式约束
    QUERY: str = "query"  # 接收到的用户(或主Agent)消息
    SUB_AGENTS: str = "sub_agents"  # 子Agent 格式: [{app_code,name,description}]
    MCPS: str = "mcps"  # MCP工具 格式: [{mcp_name, tools:[{tool_name, tool_description, prompt}]}]
    TOOLS: str = "tools"  # 除mcp外的工具 格式: [{tool_name, tool_description, prompt}]
    KNOWLEDGE: str = "knowledge"  # 知识 格式: {id,description,parameters}


class StepContextKey:
    """Agent Step级别的上下文key"""
    MESSAGE_ID: str = "message_id"  # 当前轮次的message_id
    STEP_COUNTER: str = "step_counter"  # 当前Agent第几轮循环
    ACTION_REPORTS: str = "action_reports"  # 当前轮次的action_reports 格式: [ActionOutput.to_dict]

    REMINDER: str = "reminder"  # 当前轮次需要提醒的信息 格式: str


def keys(ks) -> list[str]:
    """取出上下文key"""
    return [value for name, value in ks.__dict__.items() if value and isinstance(value, str) and not name.startswith("__")]


async def push_context_event(event: Event, agent: "ConversableAgent" = None, **kwargs):
    """推送上下文事件"""
    manager: Manager = Manager.get_instance()
    operator_clss: list[Type[Operator]] = manager.operator_clss_by_type(event.event_type)
    start_ms = current_ms()
    for operator_cls in operator_clss:
        succeed = True
        round_ms = current_ms()
        try:
            await operator_cls().handle(event=event, agent=agent, **kwargs)
        except Exception as e:
            succeed = False
            logger.exception("push_context_event: " + repr(e))
        finally:
            digest(logger, "push_context_event.operate", cost_ms=current_ms() - round_ms, succeed=succeed,
                   event_type=event.event_type, operator_name=operator_cls.name)
    digest(logger, "push_context_event", cost_ms=current_ms() - start_ms,
           event_type=event.event_type, operator_size=len(operator_clss))


def filter_context(origin: dict) -> dict:
    """从origin中过滤出上下文字段"""

    def _unpack_value(v):
        """memory写入时可能对复杂类型的value做了json dump，这里统一解析回来"""
        if v and isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                pass
        return v

    return {k: _unpack_value(origin[k]) for k in keys(ChatContextKey) + keys(StepContextKey) if k in origin}


class Manager(BaseComponent):
    name = ComponentType.CONTEXT_MANAGER

    event_subscribe: dict[EventType, list[Type[Operator]]] = {}

    def init_app(self, system_app: SystemApp):
        global _SYSTEM_APP
        _SYSTEM_APP = system_app

    def after_init(self):
        for _, operator_cls in model_scan("derisk_ext.context.operator", Operator).items():
            for event_type in operator_cls.subscribed():
                operators = self.event_subscribe.get(event_type, [])
                operators.append(operator_cls)
                self.event_subscribe[event_type] = operators

    @classmethod
    def get_instance(cls: Type[T], **kwargs) -> T:
        if not _SYSTEM_APP:
            return Manager()
        return _SYSTEM_APP.get_component(cls.name, cls)

    @classmethod
    def new_window(cls, ctx: dict = None) -> ContextWindow:
        return ContextWindow(ctx)

    @classmethod
    def current_window(cls) -> dict[str, Any]:
        return ContextWindow.get_current()

    def operator_clss_by_type(self, event_type: EventType) -> list[Type[Operator]]:
        return self.event_subscribe.get(event_type, [])

    def operator_clss(self) -> dict[EventType, list[Type[Operator]]]:
        return self.event_subscribe
