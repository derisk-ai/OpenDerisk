"""Enhanced Async Scheduler Module with Flexible Parameter Handling"""
import asyncio
import datetime
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from derisk.agent import Action, ActionOutput, GptsMemory, AgentContext, AgentResource, AgentMessage
from derisk.agent.core.action.base import T
from derisk.agent.core.schema import Status
from derisk.vis.vis_converter import SystemVisTag

logger = logging.getLogger(__name__)


class BaseScheduledAction(Action[T]):
    """Abstract base class with improved parameter handling"""

    def __init__(self, language: str = "en", name: Optional[str] = None, **kwargs):

        super().__init__(language=language, name=name, **kwargs)

        self.scheduler = AsyncIOScheduler()
        self.active_tasks: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.action_view_tag: str = SystemVisTag.VisTool.value

        # 增加任务历史存储
        self.task_history: Dict[str, Dict[str, Any]] =  defaultdict(dict)


    async def terminate(self, message_id:str):
        final_data = self.active_tasks[message_id]

        parameters = final_data['parameters']
        await self.finalize_task(message_id, **parameters)
    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Main entry point with dynamic parameter support"""
        try:
            interval = kwargs.get("interval", 60)
            start_time = datetime.datetime.now().timestamp()
            kwargs['start_time'] = start_time
            self_message: AgentMessage = kwargs['self_message']
            task_id = self_message.message_id

            # 初始化任务时添加轮次计数和执行时间记录
            self.active_tasks[task_id] = {
                "start_time": start_time,
                "retries": 0,
                "poll_count": 0,  # 新增轮次计数器
                "run_time": None,
                "result": None,
                "status": Status.TODO,
                "ai_message": ai_message,
                "parameters": kwargs,
            }

            # Pass both task_id and original kwargs to wrapper
            self.scheduler.add_job(
                self._task_wrapper,
                'interval',
                seconds=interval,
                args=(task_id,),
                kwargs=kwargs,  # Pass kwargs as keyword arguments
                id=task_id,
                max_instances=1,
                next_run_time=datetime.datetime.now()
            )
            self.scheduler.start()

            task_data = self.active_tasks[task_id]

            return self.result_to_act_out(task_id=task_id,
                                          task_data=task_data, **kwargs)
        except Exception as e:
            logger.exception("Task initialization failed")
            return ActionOutput(
                name=self.name,
                is_success=False,
                content=str(e),
                terminate=True
            )

    async def _task_wrapper(self, task_id: str, **kwargs):
        """改进的错误处理逻辑"""
        if task_id not in self.active_tasks:
            return
        max_retries = kwargs.get("max_retries", 3)
        duration = kwargs.get("duration", 900)
        task_data = self.active_tasks[task_id]
        result = None
        try:
            # 更新轮次计数和执行时间
            task_data["poll_count"] += 1
            current_time = datetime.datetime.now()
            task_data["run_time"] = current_time
            task_data["status"] = Status.RUNNING

            excute_task = asyncio.create_task(self.execute_task(task_id, **kwargs))
            task_data['excute_task'] = excute_task
            try:
                send_message, result_message = await excute_task
                result = result_message
                task_data["result"] = result

                # 尝试把答案更新到调度的发送消息中
                kwargs['bind_message_id'] = send_message.message_id
                self.task_history[task_id][task_data['poll_count']] = task_data.copy()
                await self.handle_poll(
                    task_id,
                    task_data,
                    **kwargs
                )

                if await self.check_completion(task_id, **kwargs):
                    await self.finalize_task(task_id, **kwargs)
            except asyncio.CancelledError:
                logger.warning(f"Task cancelled: {excute_task.cancelled()}")

        except Exception as e:
            task_data["error"] = str(e)
            task_data["retries"] += 1
            task_data["status"] = Status.FAILED
            logger.error(f"Task error ({task_id}): {str(e)}")

            self.task_history[task_id][task_data['poll_count']] = task_data.copy()
            await self.handle_poll(
                task_id,
                task_data,
                **kwargs
            )

            if task_data["retries"] >= max_retries:
                await self.finalize_task(task_id, **kwargs)

    async def finalize_task(self, task_id: str, **kwargs):
        """任务终止处理"""
        logger.info(f"schedule action _finalize_task{task_id}!")
        self_message: AgentMessage = kwargs.get("self_message")
        sender: AgentMessage = kwargs.get("sender")
        message_id = kwargs.get("message_id")
        agent_context: AgentContext = kwargs.get("agent_context")
        self_agent = kwargs.get("self_agent")
        gpts_memory: GptsMemory = kwargs.get("gpts_memory")

        self_message.action_report = self.final_result(task_id=task_id, **kwargs)
        from derisk.agent.core.memory.gpts import GptsMessage
        gpts_message: GptsMessage = GptsMessage.from_agent_message(message=self_message,
            sender=self_agent,  receiver=sender
        )
        await gpts_memory.append_message(conv_id=agent_context.conv_id,   message=gpts_message)

        if task_id in self.active_tasks:
            # 存储轮次和时间到历史记录
            self._cleanup_task(task_id)

    def _is_timed_out(self, task_data: Dict, expire_time: int) -> bool:
        """改进的超时检测"""
        elapsed = datetime.datetime.now().timestamp() - task_data["start_time"]
        return elapsed > expire_time

    def _cleanup_task(self, task_id: str):
        """Comprehensive task cleanup"""
        if task_id in self.active_tasks:
            task_data = self.active_tasks[task_id]
            excute_task = task_data.get('excute_task')
            if excute_task:
                excute_task.cancel()

            del self.active_tasks[task_id]
        if self.scheduler.get_job(task_id):
            self.scheduler.remove_job(task_id)

    @abstractmethod
    async def execute_task(self, task_id: str, **kwargs) -> Tuple[AgentMessage, Optional[AgentMessage]]:
        """IMPLEMENTATION GUIDE:
        Access parameters directly from kwargs without context unpacking
        Example:
            async def execute_task(self, user_query: str, agent_context: AgentContext, **kwargs):
                # Implementation using named parameters
        """

    async def check_completion(self, task_id: str, **kwargs) -> bool:
        """IMPLEMENTATION GUIDE:
        Evaluate result object from execute_task()
        Return True if task should terminate
        """
        return False

    async def handle_poll(self, task_id: str, task_data: Dict, **kwargs):
        """Override for custom polling updates"""
        bind_message_id = kwargs.get("bind_message_id")
        message_id = kwargs.get("message_id")
        agent_context: AgentContext = kwargs.get("agent_context")
        gpts_memory: GptsMemory = kwargs.get("gpts_memory")
        self_agent = kwargs.get("self_agent")

        start_time = task_data.get("start_time")
        if agent_context and gpts_memory:
            await gpts_memory.push_message(
                agent_context.conv_id,
                stream_msg={
                    "uid": bind_message_id,
                    "type": "all",
                    "sender": self_agent.name or self_agent.role,
                    "sender_role": self_agent.role,
                    "message_id": bind_message_id,
                    "conv_id": agent_context.conv_id,
                    "conv_session_uid": agent_context.conv_session_id,
                    "app_code": agent_context.gpts_app_code,
                    "start_time": start_time,
                    "action_report": self.result_to_act_out(task_id=task_id, task_data=task_data,
                                                            **kwargs)
                },
                is_first_chunk=False,
                incremental=agent_context.incremental,
                sender=self_agent
            )

    def final_result(self, task_id: str, **kwargs):
        action_input = kwargs.get("action_input")
        start_time = kwargs.get("start_time")

        result_round_map =  self.task_history[task_id]
        all_view = ""
        content_map = {}
        for k,v in result_round_map.items():
            content, view = self.view_result(task_id=task_id, task_data=v, **kwargs)
            all_view = all_view + "\n" + view
            content_map[k]=content
        # 给调度消息添加所有调度记录

        return ActionOutput(
                name=self.name,
                action_input=json.dumps(action_input.to_dict(), ensure_ascii=False),
                content=json.dumps(content_map, ensure_ascii=False),
                view=all_view,
                cost_ms=int((datetime.datetime.now().timestamp() - start_time) * 1000)
            )

    def view_result(self, task_id: str, task_data: Dict, **kwargs) -> Tuple[str, str]:
        """Action 结果转可视化执行记录
        Args:
            result: Dict action的执行结果
        """
        return task_data.get("result"), self.render_protocol.sync_display(content=task_data.get("result"))

    def result_to_act_out(self, task_id: str, task_data: Dict, **kwargs) -> ActionOutput:
        action_input = kwargs.get("action_input")
        start_time = kwargs.get("start_time")
        if not task_data or task_data.get("status") == Status.TODO:
            return ActionOutput(
                name=self.name,
                action_input=json.dumps(action_input.to_dict(), ensure_ascii=False),
                content="跟踪调度开始, 请等待结果更新！",
            )
        else:
            status = task_data.get("status", Status.COMPLETE)
            """Override for custom progress formatting"""
            content, view = self.view_result(task_id=task_id, task_data=task_data, **kwargs)
            is_exe_success = True
            if status.FAILED == status:
                is_exe_success = False
            return ActionOutput(
                is_exe_success=is_exe_success,
                name=self.name,
                action_input=json.dumps(action_input.to_dict(), ensure_ascii=False),
                content=content,
                view=view,
                cost_ms=int((datetime.datetime.now().timestamp() - start_time) * 1000)
            )
