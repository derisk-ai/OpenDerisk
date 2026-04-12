"""Analyze Image Tool.

Uses multimodal LLM to analyze image quality and provide optimization suggestions.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import Artifact, ToolResult

logger = logging.getLogger(__name__)

_ANALYZE_IMAGE_PROMPT = """分析图片质量并提供优化建议。

**使用场景：**
- 分析首帧图片质量，评估是否适合视频生成
- 提供图片优化建议和改进后的提示词
- 检查构图、光线、色调等维度

**推荐用法：**
```
# 分析图片质量
analyze_image(
    image_url="https://...",
    analysis_type="full",
    context="原始提示词：无人机俯瞰城市夜景"
)

# 仅检查视频适配性
analyze_image(
    image_url="https://...",
    analysis_type="video_suitability"
)
```

**分析维度：**
- composition: 构图质量 (主体位置、视觉平衡)
- lighting: 光线效果 (光源方向、阴影处理)
- color: 色调一致性 (颜色搭配、风格统一)
- video_suitability: 视频适配性 (是否适合作为视频首帧)

**输出：**
- 各维度评分 (1-10)
- 总体评分
- 优化建议
- 改进后的提示词建议
"""


class AnalyzeImageTool(ToolBase):
    """图片分析工具 - 使用多模态模型分析图片质量"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_image",
            display_name="Analyze Image",
            description=_ANALYZE_IMAGE_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=60,
            tags=["image", "analysis", "multimodal", "quality"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "图片 URL (公网可访问)",
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["composition", "lighting", "color", "video_suitability", "full"],
                    "description": "分析类型",
                    "default": "full",
                },
                "context": {
                    "type": "string",
                    "description": "分析上下文 (如原始提示词、场景描述)",
                },
                "model": {
                    "type": "string",
                    "description": "多模态模型 (如 claude-sonnet-4-6)",
                    "default": "claude-sonnet-4-6",
                },
            },
            "required": ["image_url"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        image_url = args.get("image_url", "").strip()
        if not image_url:
            return ToolResult.fail(error="image_url 不能为空", tool_name=self.name)

        analysis_type = args.get("analysis_type", "full")
        original_context = args.get("context", "")
        model = args.get("model", "claude-sonnet-4-6")

        # Build analysis prompt
        analysis_prompt = self._build_analysis_prompt(analysis_type, original_context)

        # Get LLM client from context
        llm_client = self._get_llm_client(context)
        if not llm_client:
            return ToolResult.fail(
                error="无法获取 LLM 客户端，请检查配置",
                tool_name=self.name,
            )

        try:
            # Call multimodal LLM with image
            result = await self._call_multimodal_llm(
                llm_client=llm_client,
                prompt=analysis_prompt,
                image_url=image_url,
                model=model,
            )

            # Parse and format result
            formatted_result = self._format_analysis_result(result, analysis_type)

            return ToolResult.ok(
                output=formatted_result,
                tool_name=self.name,
                artifacts=[Artifact(
                    name=f"image_analysis_{uuid.uuid4().hex[:8]}.json",
                    type="analysis",
                    url=image_url,
                    metadata={
                        "analysis_type": analysis_type,
                        "image_url": image_url,
                        "analysis_result": result,
                    },
                )],
            )

        except Exception as e:
            logger.error(f"[analyze_image] Analysis failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"图片分析失败: {e}",
                tool_name=self.name,
            )

    def _build_analysis_prompt(self, analysis_type: str, context: str) -> str:
        """Build analysis prompt based on type."""
        base_prompts = {
            "composition": """
分析这张图片的构图质量：

**评估维度：**
1. 主体位置 - 是否处于视觉焦点
2. 视觉平衡 - 各元素分布是否协调
3. 景深层次 - 前后景是否分明
4. 视线引导 - 是否有清晰的视觉路径

请给出评分 (1-10) 和具体评语。
""",
            "lighting": """
分析这张图片的光线效果：

**评估维度：**
1. 光源方向 - 主光源位置是否合理
2. 阴影处理 - 阴影是否自然
3. 整体亮度 - 是否适中
4. 光影层次 - 是否丰富

请给出评分 (1-10) 和具体评语。
""",
            "color": """
分析这张图片的色调：

**评估维度：**
1. 颜色搭配 - 是否和谐
2. 风格统一 - 色调是否一致
3. 情绪氛围 - 色彩传达的情绪
4. 色彩层次 - 是否丰富

请给出评分 (1-10) 和具体评语。
""",
            "video_suitability": """
分析这张图片是否适合作为视频生成的首帧：

**评估维度：**
1. 画面清晰度 - 是否足够清晰
2. 构图稳定性 - 是否适合动态效果
3. 细节丰富度 - 是否有足够细节供视频展开
4. 前景背景 - 是否有足够空间进行镜头运动
5. 视觉焦点 - 是否有明确的主体

请给出评分 (1-10) 和是否适合视频生成的判断。
""",
            "full": """
请全面分析这张图片的质量，评估以下维度：

**1. 构图质量 (composition)**
- 主体位置、视觉平衡、景深层次

**2. 光线效果 (lighting)**
- 光源方向、阴影处理、整体亮度

**3. 色调一致性 (color)**
- 颜色搭配、风格统一、情绪氛围

**4. 视频适配性 (video_suitability)**
- 是否适合作为视频首帧，考虑：
  - 清晰度、构图稳定性
  - 细节丰富度、镜头运动空间

**输出格式：**
```json
{
  "composition": {"score": 8, "comment": "..."},
  "lighting": {"score": 7, "comment": "..."},
  "color": {"score": 9, "comment": "..."},
  "video_suitability": {"score": 8, "comment": "..."},
  "overall_score": 8,
  "suggestions": ["优化建议1", "优化建议2"],
  "optimized_prompt": "改进后的英文提示词..."
}
```
""",
        }

        prompt = base_prompts.get(analysis_type, base_prompts["full"])

        if context:
            prompt += f"\n\n**上下文信息：**\n{context}"

        return prompt

    def _get_llm_client(self, context: Optional[ToolContext]) -> Any:
        """Get LLM client from context."""
        if context is None:
            return None

        # Try different ways to get LLM client
        if isinstance(context, dict):
            return context.get("llm_client")

        # From ToolContext
        if hasattr(context, "llm_client"):
            return context.llm_client

        # From resource
        return context.get_resource("llm_client")

    async def _call_multimodal_llm(
        self,
        llm_client: Any,
        prompt: str,
        image_url: str,
        model: str,
    ) -> str:
        """Call multimodal LLM with image."""
        # Build message with image
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]

        # Call LLM
        response = await llm_client.chat(
            messages=messages,
            model=model,
        )

        return response.content or response.output or str(response)

    def _format_analysis_result(self, result: str, analysis_type: str) -> str:
        """Format analysis result for output."""
        return f"""## 图片分析结果

**分析类型**: {analysis_type}

{result}
"""


__all__ = ["AnalyzeImageTool"]