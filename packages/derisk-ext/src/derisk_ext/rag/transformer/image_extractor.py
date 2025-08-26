from derisk.core.interface.media import MediaContent, MediaObject

IMAGE_EXTRACT_SYSTEM_PROMPT = """
你是一个专业的多模态图像语义分析专家，具备精准识别和理解图像内容的能力。
请按照以下要求仔细分析输入的图像：

[图像类型识别与处理指南]

1. UML/流程图识别标准：
   - 包含明确的节点、连接线
   - 呈现逻辑流程或系统架构
   - 使用几何形状（矩形、圆形、菱形等）表示流程步骤
   - 箭头连接不同节点

2. 处理策略：

[UML流程图处理]
- 目标：将图像转换为标准Mermaid流程图语法
- 要求：
  1. 准确捕捉节点和连接关系
  2. 保留原图的逻辑结构
  3. 支持复杂流程图（包括泳道、条件分支等）
- 输出格式：标准Mermaid流程图代码

[普通图片语义提取]
- 目标：获取图像的核心语义和关键信息
- 要求：
  1. 详细描述图像内容
  2. 识别主要对象和场景
  3. 分析图像中的关键元素
  4. 提供简洁但全面的语义理解

[分析准则]
- 保持高度准确性
- 清晰区分图像类型
- 如存在识别不确定性，说明原因
- 平衡详细性和简洁性

[特殊处理]
- 对于复杂或模糊的图像，提供最可能的语义解析
- 如无法完全识别，给出部分可靠信息

请开始进行专业的多模态图像语义分析。

给定的文本信息
{text}
"""
import logging
from typing import Optional

from derisk.rag.transformer.llm_extractor import LLMExtractor
from derisk.core import HumanPromptTemplate, LLMClient, ModelMessage, ModelRequest

logger = logging.getLogger(__name__)


class ImageExtractor(LLMExtractor):
    """ImageExtractor class."""

    def __init__(
        self, llm_client: LLMClient, model_name: str, prompt: Optional[str] = None
    ):
        """Initialize the MemoryCondenseExtractor."""
        self._prompt = prompt or IMAGE_EXTRACT_SYSTEM_PROMPT
        super().__init__(llm_client, model_name, self._prompt)

    def _parse_response(self, text: str, limit: Optional[int] = None) -> str:
        return text

    async def extract(
            self, image: str, text: str = None, limit: Optional[int] = None
    ):
        """Inner extract by LLM."""
        logger.info(f"Extracting image information from image: {image},"
                    f" text: {text}")

        template = HumanPromptTemplate.from_template(self._prompt_template)

        messages = template.format_messages(text=text)

        # use default model if needed
        if not self._model_name:
            models = await self._llm_client.models()
            if not models:
                raise Exception("No models available")
            self._model_name = models[0].model
            logger.info(f"Using model {self._model_name} to extract")

        for message in messages:
            message.content = [
                MediaContent(
                    type="text",
                    object=MediaObject(
                        data=message.content,
                        format="text",
                    )
                ),
                MediaContent(
                    object=MediaObject(
                        data=image,
                        format="url",
                    ), type="image"
            )]
        model_messages = ModelMessage.from_base_messages(messages)
        request = ModelRequest(
            model=self._model_name,
            messages=model_messages,
            temperature=0.01,
        )
        response = await self._llm_client.generate(request=request)
        if not response.success:
            code = str(response.error_code)
            reason = response.text
            logger.error(f"request llm failed ({code}) {reason}")
            return "llm failed"

        return self._parse_response(response.text, limit)