"""
Core V2 VIS 适配器

将 Core V2 的 ProgressEvent 转换为 GptsMessage 格式，
复用现有的 vis_window3 转换器生成前端布局数据。
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from derisk.agent.core.memory.gpts.base import GptsMessage, ActionReportType
from derisk.agent.core.schema import Status

logger = logging.getLogger(__name__)


@dataclass
class VisStep:
    """可视化步骤"""
    step_id: str
    title: str
    status: str = "pending"
    result_summary: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    layer_count: int = 0


@dataclass
class VisArtifact:
    """可视化产物"""
    artifact_id: str
    artifact_type: str
    content: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class CoreV2VisAdapter:
    """
    Core V2 VIS 适配器
    
    将 Core V2 的运行数据适配为 vis_window3 格式
    
    示例:
        adapter = CoreV2VisAdapter(agent_name="production-agent")
        
        # 添加步骤
        adapter.add_step("1", "分析需求", "running")
        adapter.add_step("2", "执行查询", "pending")
        
        # 更新步骤状态
        adapter.update_step("1", status="completed", result_summary="完成需求分析")
        
        # 添加产物
        adapter.add_artifact("result", "tool", "查询结果...", "数据库查询")
        
        # 生成 VIS 输出
        vis_output = await adapter.generate_vis_output()
    """
    
    def __init__(
        self,
        agent_name: str = "production-agent",
        agent_role: str = "assistant",
        conv_id: Optional[str] = None,
        conv_session_id: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.conv_id = conv_id or f"conv_{uuid.uuid4().hex[:8]}"
        self.conv_session_id = conv_session_id or f"session_{uuid.uuid4().hex[:8]}"
        
        self.steps: Dict[str, VisStep] = {}
        self.step_order: List[str] = []
        self.current_step_id: Optional[str] = None
        
        self.artifacts: List[VisArtifact] = []
        
        self.thinking_content: Optional[str] = None
        self.content: Optional[str] = None
        
        self._message_counter = 0
    
    def _generate_message_id(self) -> str:
        """生成消息 ID"""
        self._message_counter += 1
        return f"{self.conv_session_id}_msg_{self._message_counter}"
    
    def add_step(
        self,
        step_id: str,
        title: str,
        status: str = "pending",
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        layer_count: int = 0,
    ) -> VisStep:
        """添加步骤"""
        step = VisStep(
            step_id=step_id,
            title=title,
            status=status,
            agent_name=agent_name or self.agent_name,
            agent_role=agent_role or self.agent_role,
            layer_count=layer_count,
            start_time=datetime.now() if status == "running" else None,
        )
        self.steps[step_id] = step
        if step_id not in self.step_order:
            self.step_order.append(step_id)
        return step
    
    def update_step(
        self,
        step_id: str,
        status: Optional[str] = None,
        result_summary: Optional[str] = None,
    ) -> Optional[VisStep]:
        """更新步骤状态"""
        if step_id not in self.steps:
            logger.warning(f"Step {step_id} not found")
            return None
        
        step = self.steps[step_id]
        
        if status:
            step.status = status
            if status in ("completed", "failed"):
                step.end_time = datetime.now()
            elif status == "running":
                if not step.start_time:
                    step.start_time = datetime.now()
        
        if result_summary:
            step.result_summary = result_summary
        
        return step
    
    def set_current_step(self, step_id: str):
        """设置当前执行步骤"""
        self.current_step_id = step_id
    
    def add_artifact(
        self,
        artifact_id: str,
        artifact_type: str,
        content: str,
        title: Optional[str] = None,
        **metadata,
    ):
        """添加产物"""
        artifact = VisArtifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content=content,
            title=title,
            metadata=metadata,
        )
        self.artifacts.append(artifact)
    
    def set_thinking(self, thinking: str):
        """设置思考内容"""
        self.thinking_content = thinking
    
    def set_content(self, content: str):
        """设置主要内容"""
        self.content = content
    
    def _steps_to_gpts_messages(self) -> List[GptsMessage]:
        """将步骤转换为 GptsMessage 列表"""
        messages = []
        
        for step_id in self.step_order:
            step = self.steps[step_id]
            message_id = self._generate_message_id()
            
            action_report: ActionReportType = [
                {
                    "action_id": f"{message_id}_action",
                    "action": step.title,
                    "action_name": step.title,
                    "action_input": {},
                    "thoughts": step.result_summary or "",
                    "view": step.result_summary or "",
                    "content": step.result_summary or "",
                    "state": self._map_status(step.status),
                    "start_time": step.start_time or datetime.now(),
                    "end_time": step.end_time,
                    "stream": False,
                }
            ]
            
            message = GptsMessage(
                conv_id=self.conv_id,
                conv_session_id=self.conv_session_id,
                message_id=message_id,
                sender=self.agent_role,
                sender_name=step.agent_name or self.agent_name,
                receiver="user",
                receiver_name="User",
                role="assistant",
                content=step.result_summary or "",
                thinking=None,
                action_report=action_report,
                created_at=step.start_time or datetime.now(),
                updated_at=step.end_time or datetime.now(),
            )
            messages.append(message)
        
        return messages
    
    def _map_status(self, status: str) -> str:
        """映射状态"""
        status_map = {
            "pending": Status.WAITING.value,
            "running": Status.RUNNING.value,
            "completed": Status.COMPLETE.value,
            "failed": Status.FAILED.value,
        }
        return status_map.get(status, Status.WAITING.value)
    
    def generate_planning_window(self) -> Dict[str, Any]:
        """生成规划窗口数据"""
        steps_data = []
        
        for step_id in self.step_order:
            step = self.steps[step_id]
            steps_data.append({
                "step_id": step.step_id,
                "title": step.title,
                "status": step.status,
                "result_summary": step.result_summary,
                "agent_name": step.agent_name,
                "agent_role": step.agent_role,
                "layer_count": step.layer_count,
                "start_time": step.start_time.isoformat() if step.start_time else None,
                "end_time": step.end_time.isoformat() if step.end_time else None,
            })
        
        return {
            "steps": steps_data,
            "current_step_id": self.current_step_id,
        }
    
    def generate_running_window(self) -> Dict[str, Any]:
        """生成运行窗口数据"""
        current_step = None
        if self.current_step_id and self.current_step_id in self.steps:
            current_step = self.steps[self.current_step_id]
        
        artifacts_data = []
        for artifact in self.artifacts:
            artifacts_data.append({
                "artifact_id": artifact.artifact_id,
                "type": artifact.artifact_type,
                "title": artifact.title,
                "content": artifact.content,
                "metadata": artifact.metadata,
            })
        
        return {
            "current_step": {
                "step_id": current_step.step_id if current_step else None,
                "title": current_step.title if current_step else None,
                "status": current_step.status if current_step else None,
            } if current_step else None,
            "thinking": self.thinking_content,
            "content": self.content,
            "artifacts": artifacts_data,
        }
    
    async def generate_vis_output(
        self,
        use_gpts_format: bool = True,
    ) -> Union[str, Dict[str, Any]]:
        """
        生成 VIS 输出
        
        Args:
            use_gpts_format: 是否使用 GptsMessage 格式（用于兼容 vis_window3 转换器）
        
        Returns:
            VIS 输出数据（JSON 字符串或字典）
        """
        if use_gpts_format:
            try:
                from derisk_ext.vis.derisk.derisk_vis_window3_converter import DeriskIncrVisWindow3Converter
                
                messages = self._steps_to_gpts_messages()
                
                if not messages:
                    return json.dumps({
                        "planning_window": self.generate_planning_window(),
                        "running_window": self.generate_running_window(),
                    }, ensure_ascii=False)
                
                converter = DeriskIncrVisWindow3Converter()
                
                vis_output = await converter.visualization(
                    messages=messages,
                    senders_map={},
                    main_agent_name=self.agent_name,
                    is_first_chunk=True,
                    is_first_push=True,
                )
                
                return vis_output
                
            except ImportError:
                logger.warning("DeriskIncrVisWindow3Converter not available, using simple format")
                return json.dumps({
                    "planning_window": self.generate_planning_window(),
                    "running_window": self.generate_running_window(),
                }, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to generate VIS output with GptsMessage format: {e}")
                return json.dumps({
                    "planning_window": self.generate_planning_window(),
                    "running_window": self.generate_running_window(),
                }, ensure_ascii=False)
        else:
            return {
                "planning_window": self.generate_planning_window(),
                "running_window": self.generate_running_window(),
            }
    
    async def generate_vis_manus_output(
        self,
    ) -> Optional[str]:
        """
        生成 Manus 布局 VIS 输出

        使用 DeriskIncrVisManusConverter 将步骤数据转换为 manus-left-panel + manus-right-panel

        Returns:
            VIS 输出 JSON 字符串
        """
        try:
            from derisk_ext.vis.derisk.derisk_vis_manus_converter import DeriskIncrVisManusConverter

            messages = self._steps_to_gpts_messages()

            if not messages:
                return None

            converter = DeriskIncrVisManusConverter()

            vis_output = await converter.visualization(
                messages=messages,
                senders_map={},
                main_agent_name=self.agent_name,
                is_first_chunk=True,
                is_first_push=True,
            )

            return vis_output

        except ImportError:
            logger.warning("DeriskIncrVisManusConverter not available")
            return None
        except Exception as e:
            logger.error(f"Failed to generate Manus VIS output: {e}")
            return None

    def clear(self):
        """清空数据"""
        self.steps.clear()
        self.step_order.clear()
        self.artifacts.clear()
        self.current_step_id = None
        self.thinking_content = None
        self.content = None