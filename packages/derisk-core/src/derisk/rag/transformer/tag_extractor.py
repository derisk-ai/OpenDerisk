import json
import logging
from typing import Optional, List

from derisk.agent.core.action.base import JsonMessageType
from derisk.core import LLMClient, ModelMessage, ModelRequest, HumanPromptTemplate
from derisk.rag.transformer.llm_extractor import LLMExtractor
from derisk._private.pydantic import BaseModel
from derisk.util import json_utils

TAGS_EXTRACT_PT = (
    "你是一个元数据提取专家，我会给你一个问题以及一个tags列表，列表里面是各种tag标签，[{{'tag':'year', 'description': '年份, eg: CY25,CY24'}}]，你需要选出和问题相关的tag标签，"
    "示例1 : "
    "问题：CY25封网计划是什么？ tags:[{{'tag': 'year', 'tag_description': '年份, eg: CY25,CY24'}}]\n"
    "输出：[{{\"year\": \"CY25\"}}]\n"
     "示例1 : "
    "问题：封网计划是什么？ tags:[{{'tag': \"year\", 'tag_description': '年份, eg: CY25,CY24'}}]\n"
    "输出：[{{\"year\": ""}}]\n"
    "示例2 : "
    "问题：CY24封网计划是什么？ tags:[{{'tag': \"year\", 'tag_description': '年份, eg: CY25,CY24'}}]\n"
    "输出：[{{\"year\": \"CY24\"}}]\n"
    "示例3 : "
    "问题：OB4.x版本有什么新特性？ tags:[{{'tag': \"version\", 'tag_description': '版本, eg: 4.x, 3.x'}}]\n"
    "输出：[{{\"version\": \"4.x\"}}]\n"
    "输入：\n 问题: {text}， tags:{tags}\n"
    "输出:\n"
)

logger = logging.getLogger(__name__)


class MetadataTag(BaseModel):
    tag: str
    description: Optional[str] = None


class TagsExtractor(LLMExtractor):
    """TagsExtractor class."""

    def __init__(self, llm_client: LLMClient, model_name: str, tags: List[MetadataTag]):
        """Initialize the KeywordExtractor."""
        self._tags = tags
        super().__init__(llm_client, model_name, TAGS_EXTRACT_PT)


    async def _extract(
        self, text: str, history: str = None, limit: Optional[int] = None
    ) -> List:
        """Inner extract by LLM."""
        template = HumanPromptTemplate.from_template(self._prompt_template)

        messages = (
            template.format_messages(text=text, history=history)
            if history is not None
            else template.format_messages(text=text, tags="\n".join([
              json.dumps(tag.dict(), ensure_ascii=False) for tag in self._tags
            ]))
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

    def _parse_response(self, text: str, limit: Optional[int] = None) -> List[dict]:
        logger.info(f"_parse_response text is {text}")

        try:
            tags = json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse JSON response: {e}")
            # Attempt to find JSON objects in the text
            try:
                tags = self._ai_message_2_json(text)
            except Exception as e:
                logger.error(f"Failed to parse _ai_message_2_json response: {e}")
                tags = []
        logger.info(f"_parse_response tags is {tags}")
        return tags

    def _ai_message_2_json(self, ai_message: str) -> JsonMessageType:
        json_objects = json_utils.find_json_objects(ai_message)
        json_count = len(json_objects)
        if json_count != 1:
            raise ValueError("Unable to obtain valid output.")
        return json_objects[0]