import asyncio
import logging
from typing import Optional, List

from derisk.agent import ConversableAgent, AgentMessage, Agent, AWELTeamContext, ProfileConfig, BlankAction, AgentGenerateContext
from derisk.agent.core.base_team import ManagerAgent
from derisk.core.awel import DAG, BaseOperator, DAGContext
from derisk.core.awel.dag.base import DAGVariables
from derisk.core.awel.flow.flow_factory import FlowPanel
from derisk.util.configure import DynConfig
from derisk.util.date_utils import current_ms
from derisk_ext.agent.agents.awel.awel_runner import AWELRunner
from derisk_serve.flow.service.service import Service as FlowService

logger: logging.Logger = logging.getLogger("awel")


class AwelRunnerAgent(ManagerAgent):
    flow_service: FlowService = None
    team_context: AWELTeamContext = None

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "AwelRunnerAgent",
            category="agent",
            key="derisk_agent_expand_plugin_assistant_agent_name",
        ),
        role=DynConfig(
            "AwelRunnerAgent",
            category="agent",
            key="derisk_agent_expand_plugin_assistant_agent_role",
        ),
    )

    def __init__(self, **kwargs):
        """Create a new instance of AwelRunnerAgent."""
        super().__init__(**kwargs)
        self.team_context: AWELTeamContext = kwargs.get("team_context")
        self.flow_service: FlowService = kwargs.get("flow_service")
        self._init_actions([BlankAction])

    async def generate_reply(
            self,
            received_message: AgentMessage,
            sender: ConversableAgent,
            reviewer: Optional[Agent] = None,
            rely_messages: Optional[List[AgentMessage]] = None,
            historical_dialogues: Optional[List[AgentMessage]] = None,
            is_retry_chat: bool = False,
            last_speaker_name: Optional[str] = None,
            **kwargs,
    ) -> Optional[AgentMessage]:
        st = current_ms()
        succ: bool = True
        try:
            logger.info(f"AwelRunnerAgent in: {received_message.message_id}, " + received_message.content)

            request: AgentGenerateContext = AgentGenerateContext(
                message=received_message,
                sender=sender,
                receiver=self,
                rely_messages=rely_messages,
                memory=sender.memory,
                agent_context=sender.agent_context,
                llm_client=self.llm_client,
                round_index=received_message.rounds,
            )
            flow: FlowPanel = self.flow_service.get({"uid": self.team_context.uid})
            dag: DAG = self.flow_service.dag_manager.dag_map.get(flow.dag_id)
            logger.info(f"AwelRunnerAgent dag_id[{flow.dag_id if flow else None}][{'' if not dag else '!'}=None]")

            trigger: BaseOperator = dag.root_nodes[0]
            trigger._runner = AWELRunner()

            logger.info(f"AwelRunnerAgent 开始执行: {trigger.node_name}/{trigger.node_id}")
            dag_variables = DAGVariables()
            dag_ctx = DAGContext(
                event_loop_task_id=id(asyncio.current_task()),
                node_to_outputs={},
                share_data={"query": received_message.content},
                streaming_call=False,
                dag_variables=dag_variables,
            )
            result: AgentGenerateContext = await trigger.call(request, dag_ctx=dag_ctx, dag_variables=dag_variables)
            # if result and result.message:
            #     await self.send(message=result.message, recipient=sender, request_reply=False)
            #
            # return None
            return result.message if result else None
        except BaseException as e:
            logger.exception("AwelRunnerAgent 捕获异常: " + repr(e))
            succ = False
            raise
        finally:
            logger.info(f"[DIGEST][AwelRunnerAgent],succ=[{succ}],cost_ms=[{current_ms() - st}],")
