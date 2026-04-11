"""VideoGenAgent - 视频生成专业Agent.

专门用于执行单次视频生成任务，使用 Seedance (火山引擎) 或其他视频生成模型。
一次调用生成一个视频，批量生成由主 Agent 调度。
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import logging
import json

from derisk.agent.core_v2.builtin_agents.base_builtin_agent import BaseBuiltinAgent
from derisk.agent.core_v2.agent_info import AgentInfo
from derisk.agent.core_v2.llm_adapter import LLMAdapter
from derisk.agent.core_v2.tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


VIDEO_GEN_SYSTEM_PROMPT = """你是一个专业的视频生成Agent，负责执行单次视频生成任务。

## 核心职责

你专注于基于首帧图片生成高质量视频。每次调用只生成一个视频片段。

## 可用工具

- `generate_video`: 视频生成工具，支持多种模型和参数

## 视频生成流程

1. **理解需求**
   - 分析首帧图片内容
   - 理解运动描述和风格要求
   - 确定视频时长和帧率

2. **选择模型**
   - doubao-seedance-1-5-pro-251215 (高质量，支持图片输入)
   - doubao-seedance-1-5-i2v (图片到视频专用)
   - 可选 Sora、其他视频模型

3. **生成视频**
   - 调用 generate_video 工具
   - 传递首帧图片 URL 和运动描述
   - 等待异步任务完成
   - 获取生成结果 URL

4. **验证结果**
   - 确认视频生成成功
   - 返回视频 URL 和元信息

## Seedance 视频生成参数

**基础参数:**
- prompt: 运动描述 (描述图片如何动起来)
- model: doubao-seedance-1-5-pro-251215 或 doubao-seedance-1-5-i2v
- first_frame_image_url: 首帧图片 URL (关键参数)

**高级参数:**
- duration: 视频时长 (默认5秒，范围3-10)
- camerafixed: 镜头固定模式
  - True: 固定镜头，仅画面内容动
  - False: 镜头可运动 (推拉摇移)
- watermark: 是否添加水印
- resolution: 视频分辨率 (720p, 1080p, 4K)

## 运动描述技巧

1. **明确运动类型**
   - 镜头运动: push_in, pull_out, pan_left, pan_right, tilt_up, tilt_down
   - 内容运动: flow, wave, grow, rotate, breathe

2. **描述运动幅度**
   - gentle: 轻柔运动
   - moderate: 中等运动
   - dynamic: 动态剧烈

3. **控制运动方向**
   - 明确运动起点和终点
   - 描述运动轨迹

4. **结合场景特点**
   - 自然场景: 水流、风吹、云动
   - 城市场景: 灯光变化、人流、车流
   - 人物场景: 表情变化、肢体动作

## 示例运动描述

```
- "缓慢推镜头，画面中的人物表情逐渐变得喜悦"
- "俯瞰视角，城市夜景中灯光闪烁，车流缓缓移动"
- "海浪轻轻拍打沙滩，镜头缓慢向右平移"
- "无人机视角，城市街道逐渐展现，建筑细节清晰"
```

## 输出格式

生成成功后，返回:
```
✅ 视频生成成功
- 视频URL: [生成的视频地址]
- 首帧图片: [首帧图片URL]
- 模型: [使用的模型]
- 时长: [视频时长]
- 描述: [运动描述]
```

## 注意事项

- 每次只生成一个视频片段
- 必须提供首帧图片 URL
- 运动描述要简洁明确
- 视频生成是异步任务，需要等待
- 遇到错误时分析原因并尝试调整参数
"""


class VideoGenAgent(BaseBuiltinAgent):
    """视频生成Agent - 单次视频生成执行器"""

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        default_model: str = "doubao-seedance-1-5-pro-251215",
        default_duration: int = 5,
        default_camerafixed: bool = False,
        **kwargs,
    ):
        super().__init__(info, llm_adapter, tool_registry, **kwargs)

        self.default_model = default_model
        self.default_duration = default_duration
        self.default_camerafixed = default_camerafixed

        logger.info(
            f"[VideoGenAgent] 初始化完成: "
            f"default_model={default_model}, "
            f"default_duration={default_duration}, "
            f"camerafixed={default_camerafixed}"
        )

    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表"""
        return ["generate_video"]

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return VIDEO_GEN_SYSTEM_PROMPT

    async def generate_video(
        self,
        first_frame_image_url: str,
        prompt: str,
        model: Optional[str] = None,
        duration: Optional[int] = None,
        camerafixed: Optional[bool] = None,
        watermark: bool = False,
        resolution: str = "1080p",
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行单次视频生成

        Args:
            first_frame_image_url: 首帧图片 URL (必须)
            prompt: 运动描述提示词
            model: 生成模型 (默认 doubao-seedance-1-5-pro-251215)
            duration: 视频时长秒数 (默认 5)
            camerafixed: 镜头固定模式
            watermark: 是否添加水印
            resolution: 视频分辨率
            context: 生成上下文信息

        Returns:
            Dict: 生成结果，包含 url, model, duration 等
        """
        if not first_frame_image_url:
            return {
                "success": False,
                "error": "首帧图片 URL 是必须参数",
            }

        model = model or self.default_model
        duration = duration or self.default_duration
        camerafixed = camerafixed if camerafixed is not None else self.default_camerafixed

        logger.info(
            f"[VideoGenAgent] 开始生成视频: "
            f"model={model}, duration={duration}s, "
            f"image={first_frame_image_url[:50]}..."
        )

        # 构建工具参数
        tool_args = {
            "prompt": prompt,
            "model": model,
            "first_frame_image_url": first_frame_image_url,
        }

        # Seedance 高级参数
        if model.startswith("doubao-seedance"):
            tool_args["duration"] = duration
            tool_args["camerafixed"] = camerafixed
            tool_args["watermark"] = watermark
            tool_args["resolution"] = resolution

        # 执行生成工具
        result = await self.execute_tool("generate_video", tool_args)

        if result.success:
            logger.info(f"[VideoGenAgent] 视频生成成功")

            # 提取视频 URL
            video_url = None
            if result.artifacts:
                for artifact in result.artifacts:
                    if artifact.type == "video":
                        video_url = artifact.url
                        break

            return {
                "success": True,
                "url": video_url,
                "first_frame_image_url": first_frame_image_url,
                "model": model,
                "prompt": prompt,
                "duration": duration,
                "output": result.output,
                "metadata": {
                    "camerafixed": camerafixed,
                    "watermark": watermark,
                    "resolution": resolution,
                },
            }
        else:
            logger.error(f"[VideoGenAgent] 视频生成失败: {result.error}")
            return {
                "success": False,
                "error": result.error,
                "model": model,
                "prompt": prompt,
                "first_frame_image_url": first_frame_image_url,
            }

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """
        主执行循环

        Args:
            message: 用户请求，包含视频生成需求
            stream: 是否流式输出

        Returns:
            AsyncIterator: 生成结果流
        """
        logger.info(f"[VideoGenAgent] 收到生成请求: {message[:100]}...")

        # 解析请求
        request = self._parse_request(message)

        # 验证必要参数
        first_frame_url = request.get("first_frame_image_url") or request.get("image_url")
        if not first_frame_url:
            yield "❌ 错误: 必须提供首帧图片 URL (first_frame_image_url 或 image_url)"
            return

        # 执行生成
        result = await self.generate_video(
            first_frame_image_url=first_frame_url,
            prompt=request.get("prompt", "自然运动"),
            model=request.get("model"),
            duration=request.get("duration"),
            camerafixed=request.get("camerafixed"),
            watermark=request.get("watermark", False),
            resolution=request.get("resolution", "1080p"),
            context=request.get("context"),
        )

        # 输出结果
        if result.get("success"):
            output = f"""
✅ 视频生成成功
- 视频URL: {result.get('url')}
- 首帧图片: {result.get('first_frame_image_url')}
- 模型: {result.get('model')}
- 时长: {result.get('duration')}s
- 描述: {result.get('prompt')}
"""
        else:
            output = f"""
❌ 视频生成失败
- 错误: {result.get('error')}
- 首帧图片: {result.get('first_frame_image_url')}
- 模型: {result.get('model')}
"""

        yield output

    def _parse_request(self, message: str) -> Dict[str, Any]:
        """
        解析请求参数

        支持两种格式:
        1. JSON 格式: {"prompt": "...", "image_url": "...", ...}
        2. 纯文本: 尝试提取 URL 和描述
        """
        try:
            # 尝试解析 JSON
            if message.strip().startswith("{"):
                return json.loads(message)
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取 URL 和描述
        # 格式: "image_url: xxx prompt: xxx" 或 "xxx [url] xxx"
        import re

        url_pattern = r'(https?://[^\s]+(?:\.jpg|\.png|\.jpeg|\.webp|\.gif))'
        urls = re.findall(url_pattern, message)

        result = {}
        if urls:
            result["first_frame_image_url"] = urls[0]

        # 描述为剩余文本
        prompt = message
        for url in urls:
            prompt = prompt.replace(url, "").strip()
        if prompt:
            result["prompt"] = prompt

        return result

    @classmethod
    def create(
        cls,
        name: str = "video-gen-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 5,
        default_video_model: str = "doubao-seedance-1-5-pro-251215",
        default_duration: int = 5,
        default_camerafixed: bool = False,
        **kwargs,
    ) -> "VideoGenAgent":
        """
        便捷创建方法

        Args:
            name: Agent名称
            model: LLM模型
            api_key: API密钥
            max_steps: 最大步数
            default_video_model: 默认视频生成模型
            default_duration: 默认视频时长
            default_camerafixed: 默认镜头固定模式
            **kwargs: 其他参数

        Returns:
            VideoGenAgent: Agent实例
        """
        import os
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache
        from derisk.agent.core_v2.llm_adapter import LLMConfig, LLMFactory

        if not api_key:
            if ModelConfigCache.has_model(model):
                model_config = ModelConfigCache.get_config(model)
                if model_config:
                    api_key = api_key or model_config.get("api_key")

        api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("需要提供 OpenAI API Key")

        info = AgentInfo(name=name, max_steps=max_steps, **kwargs)
        llm_config = LLMConfig(model=model, api_key=api_key)
        llm_adapter = LLMFactory.create(llm_config)

        return cls(
            info=info,
            llm_adapter=llm_adapter,
            default_model=default_video_model,
            default_duration=default_duration,
            default_camerafixed=default_camerafixed,
            **kwargs,
        )


__all__ = ["VideoGenAgent"]