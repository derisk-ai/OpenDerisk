"""FrameGenAgent - 首帧图片生成专业Agent.

专门用于执行单次图片生成任务，使用 Wan (万相) 或其他图片生成模型。
一次调用生成一张图片，批量生成由主 Agent 调度。
"""

from typing import AsyncIterator, Dict, Any, Optional, List
import logging
import json

from derisk.agent.core_v2.builtin_agents.base_builtin_agent import BaseBuiltinAgent
from derisk.agent.core_v2.agent_info import AgentInfo
from derisk.agent.core_v2.llm_adapter import LLMAdapter
from derisk.agent.core_v2.tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


FRAME_GEN_SYSTEM_PROMPT = """你是一个专业的首帧图片生成Agent，负责执行单次图片生成任务。

## 核心职责

你专注于生成高质量的首帧图片，用于后续视频生成。每次调用只生成一张图片。

## 可用工具

- `generate_image`: 图片生成工具，支持多种模型和参数

## 图片生成流程

1. **理解需求**
   - 分析场景描述和视觉风格要求
   - 确定构图、光线、色调等关键元素
   - 优化提示词以获得最佳效果

2. **选择模型**
   - 默认使用 wan2.7-image-pro (高质量)
   - wan2.7-image (快速生成)
   - 可选 DALL-E、Stable Diffusion 等

3. **生成图片**
   - 调用 generate_image 工具
   - 传递优化后的提示词和参数
   - 获取生成结果 URL

4. **验证结果**
   - 确认图片生成成功
   - 返回图片 URL 和元信息

## Wan 图片生成参数

**基础参数:**
- prompt: 图片描述 (英文最佳)
- model: wan2.7-image-pro 或 wan2.7-image
- size: 图片尺寸 (1024x1024, 1920x1080 等)

**高级参数 (wan2.7-image-pro):**
- thinking_mode: 思考模式，提升复杂场景生成质量
- enable_sequential: 序列生成模式，用于连续场景
- bbox_list: 构图区域控制，精确指定元素位置
- color_palette: 色调控制，保持风格一致性
- negative_prompt: 负面提示词，排除不需要的元素

## 提示词优化技巧

1. **构图清晰**
   - 明确主体位置和背景层次
   - 添加镜头角度描述 (俯视、仰视、平视)

2. **光线明确**
   - 指定光源方向和强度
   - 描述光影效果 (柔和、硬光、逆光)

3. **色调统一**
   - 定义整体色彩风格
   - 使用 color_palette 保持一致性

4. **细节丰富**
   - 添加环境细节描述
   - 包含材质和纹理信息

## 输出格式

生成成功后，返回:
```
✅ 图片生成成功
- 图片URL: [生成的图片地址]
- 模型: [使用的模型]
- 描述: [图片描述]
- 尺寸: [图片尺寸]
```

## 注意事项

- 每次只生成一张图片
- 提示词必须是英文
- 遇到错误时分析原因并尝试调整参数
- 复杂场景启用 thinking_mode
"""


class FrameGenAgent(BaseBuiltinAgent):
    """首帧图片生成Agent - 单次图片生成执行器"""

    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        default_model: str = "wan2.7-image-pro",
        default_size: str = "1920x1080",
        enable_thinking_mode: bool = True,
        **kwargs,
    ):
        super().__init__(info, llm_adapter, tool_registry, **kwargs)

        self.default_model = default_model
        self.default_size = default_size
        self.enable_thinking_mode = enable_thinking_mode

        logger.info(
            f"[FrameGenAgent] 初始化完成: "
            f"default_model={default_model}, "
            f"default_size={default_size}, "
            f"thinking_mode={enable_thinking_mode}"
        )

    def _get_default_tools(self) -> List[str]:
        """获取默认工具列表"""
        return ["generate_image"]

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return FRAME_GEN_SYSTEM_PROMPT

    async def generate_frame(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: Optional[str] = None,
        thinking_mode: Optional[bool] = None,
        bbox_list: Optional[List[Dict]] = None,
        color_palette: Optional[List[str]] = None,
        negative_prompt: Optional[str] = None,
        enable_sequential: bool = False,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行单次图片生成

        Args:
            prompt: 图片描述提示词
            model: 生成模型 (默认 wan2.7-image-pro)
            size: 图片尺寸 (默认 1920x1080)
            thinking_mode: 是否启用思考模式
            bbox_list: 构图区域控制
            color_palette: 色调控制
            negative_prompt: 负面提示词
            enable_sequential: 序列生成模式
            context: 生成上下文信息

        Returns:
            Dict: 生成结果，包含 url, model, prompt 等
        """
        model = model or self.default_model
        size = size or self.default_size
        thinking_mode = thinking_mode if thinking_mode is not None else self.enable_thinking_mode

        logger.info(f"[FrameGenAgent] 开始生成图片: model={model}, prompt={prompt[:50]}...")

        # 构建工具参数
        tool_args = {
            "prompt": prompt,
            "model": model,
            "size": size,
        }

        # Wan 高级参数
        if model.startswith("wan"):
            if thinking_mode:
                tool_args["thinking_mode"] = True
            if bbox_list:
                tool_args["bbox_list"] = bbox_list
            if color_palette:
                tool_args["color_palette"] = color_palette
            if negative_prompt:
                tool_args["negative_prompt"] = negative_prompt
            if enable_sequential:
                tool_args["enable_sequential"] = True

        # 执行生成工具
        result = await self.execute_tool("generate_image", tool_args)

        if result.success:
            logger.info(f"[FrameGenAgent] 图片生成成功")

            # 提取图片 URL
            image_url = None
            if result.artifacts:
                for artifact in result.artifacts:
                    if artifact.type == "image":
                        image_url = artifact.url
                        break

            return {
                "success": True,
                "url": image_url,
                "model": model,
                "prompt": prompt,
                "size": size,
                "output": result.output,
                "metadata": {
                    "thinking_mode": thinking_mode,
                    "bbox_list": bbox_list,
                    "color_palette": color_palette,
                },
            }
        else:
            logger.error(f"[FrameGenAgent] 图片生成失败: {result.error}")
            return {
                "success": False,
                "error": result.error,
                "model": model,
                "prompt": prompt,
            }

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """
        主执行循环

        Args:
            message: 用户请求，包含图片生成需求
            stream: 是否流式输出

        Returns:
            AsyncIterator: 生成结果流
        """
        logger.info(f"[FrameGenAgent] 收到生成请求: {message[:100]}...")

        # 解析请求
        request = self._parse_request(message)

        # 执行生成
        result = await self.generate_frame(
            prompt=request.get("prompt", message),
            model=request.get("model"),
            size=request.get("size"),
            thinking_mode=request.get("thinking_mode"),
            bbox_list=request.get("bbox_list"),
            color_palette=request.get("color_palette"),
            negative_prompt=request.get("negative_prompt"),
            context=request.get("context"),
        )

        # 输出结果
        if result.get("success"):
            output = f"""
✅ 图片生成成功
- 图片URL: {result.get('url')}
- 模型: {result.get('model')}
- 描述: {result.get('prompt')[:100]}
- 尺寸: {result.get('size')}
"""
        else:
            output = f"""
❌ 图片生成失败
- 错误: {result.get('error')}
- 模型: {result.get('model')}
- 描述: {result.get('prompt')[:100]}
"""

        yield output

    def _parse_request(self, message: str) -> Dict[str, Any]:
        """
        解析请求参数

        支持两种格式:
        1. JSON 格式: {"prompt": "...", "model": "...", ...}
        2. 纯文本: 直接作为 prompt 使用
        """
        try:
            # 尝试解析 JSON
            if message.strip().startswith("{"):
                return json.loads(message)
        except json.JSONDecodeError:
            pass

        # 作为纯文本 prompt
        return {"prompt": message}

    @classmethod
    def create(
        cls,
        name: str = "frame-gen-agent",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        max_steps: int = 5,
        default_image_model: str = "wan2.7-image-pro",
        default_size: str = "1920x1080",
        enable_thinking_mode: bool = True,
        **kwargs,
    ) -> "FrameGenAgent":
        """
        便捷创建方法

        Args:
            name: Agent名称
            model: LLM模型
            api_key: API密钥
            max_steps: 最大步数
            default_image_model: 默认图片生成模型
            default_size: 默认图片尺寸
            enable_thinking_mode: 默认启用思考模式
            **kwargs: 其他参数

        Returns:
            FrameGenAgent: Agent实例
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
            default_model=default_image_model,
            default_size=default_size,
            enable_thinking_mode=enable_thinking_mode,
            **kwargs,
        )


__all__ = ["FrameGenAgent"]