"""Tags Extractor class."""

import logging
from typing import List, Optional

from derisk.core import LLMClient, HumanPromptTemplate, ModelMessage, ModelRequest
from derisk.rag.transformer.llm_extractor import LLMExtractor

TAGS_EXTRACT_PT = (
    "你是一个元数据提取专家，我会给你一个问题以及一个tags列表，列表存储的是各种tag标签，你需要从tags列表中选出和问题相关的tag标签，"
    "如果tag和问题都不相关，就返回空字符串。如果有多个tag与问题相关，那么返回多个tag标签，以英文逗号分隔。\n"
    "注意："
    "1.保证输出的tag标签必须在tags列表里面"
    "2.如果输出多个tag标签，那么必须以英文逗号分隔，并且严格检查每个tag标签没有多余的单引号或者双引号或者空格"
    ""
    "输入：\n 问题: {text}， tags:{tags}\n"
    "输出:\n"
)


logger = logging.getLogger(__name__)


class TagsExtractor(LLMExtractor):
    """KeywordExtractor class."""

    def __init__(self, llm_client: LLMClient, model_name: str, tags: List[str]):
        """Initialize the KeywordExtractor."""
        self._tags = tags
        super().__init__(llm_client, model_name, TAGS_EXTRACT_PT)

    def _parse_response(self, text: str, limit: Optional[int] = None) -> List[str]:
        logger.info(f"_parse_response text is {text}")

        texts = text.split(",")
        tags = set()
        for text in texts:
            text = text.strip().strip("'\"")
            tags.add(text)

        return list(tags)

    async def _extract(
        self, text: str, history: str = None, limit: Optional[int] = None
    ) -> List:
        """Inner extract by LLM."""
        template = HumanPromptTemplate.from_template(self._prompt_template)

        messages = (
            template.format_messages(text=text, history=history)
            if history is not None
            else template.format_messages(text=text, tags=self._tags)
        )

        # use default model if needed
        if not self._model_name:
            models = await self._llm_client.models()
            if not models:
                raise Exception("No models available")
            self._model_name = models[0].model

            logger.info(f"Using model {self._model_name} to extract")

        model_messages = ModelMessage.from_base_messages(messages)
        request = ModelRequest(model=self._model_name, messages=model_messages)
        response = await self._llm_client.generate(request=request)

        if not response.success:
            code = str(response.error_code)
            reason = response.text
            logger.error(f"request llm failed ({code}) {reason}")
            return []

        if limit and limit < 1:
            ValueError("optional argument limit >= 1")
        return self._parse_response(response.text, limit)
