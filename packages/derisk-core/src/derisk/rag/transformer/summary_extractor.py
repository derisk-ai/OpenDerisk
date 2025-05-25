"""Tags Extractor class."""

import logging
from typing import List, Optional

from derisk.core import LLMClient
from derisk.rag.transformer.llm_extractor import LLMExtractor

SUMMARY_EXTRACT_PT = (
    "你是一个「总结专家」，请根据query对检索到的文档进行回答，要求回答的内容和query是相关的。\n"
    "注意："
    "1.尽可能的不要漏要点信息，不要加上你的评论和建议\n"
    "2.尽可能地保留知识的要点信息，不要遗漏\n"
    "3.如果问题和检索到的知识没有关系，请返回无相关知识\n"
    "检索到的知识: {text}\n"
)


logger = logging.getLogger(__name__)


class SummaryExtractor(LLMExtractor):
    """KeywordExtractor class."""

    def __init__(
        self, llm_client: LLMClient, model_name: str, prompt: Optional[str] = None
    ):
        """Initialize the SummaryExtractor."""
        self._prompt = prompt or SUMMARY_EXTRACT_PT
        super().__init__(llm_client, model_name, self._prompt)

    def _parse_response(self, text: str, limit: Optional[int] = None) -> List[str]:
        return text
