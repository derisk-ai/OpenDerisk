import json
from typing import Optional

from derisk.component import logger
from derisk.core import LLMClient, ModelMessage, ModelRequest, HumanPromptTemplate
from derisk.core.awel import MapOperator
from derisk.core.awel.task.base import IN, OUT


class SplitQueryOperator(MapOperator[IN, OUT]):
    """The Base Assembler Operator."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model_name: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ):
        """Initialize the SummaryOperator.

        Args:
            llm_client (LLMClient): The LLM client.
            model_name (str): The model name.
            prompt (Optional[str]): The prompt template. Defaults to None.
        """
        self._llm_client = llm_client
        self._model_name = model_name or "deepseek-v3"
        self._prompt = prompt
        super().__init__(**kwargs)

    async def map(self, input_value: IN) -> OUT:
        """Map input value to output value.

        Args:
            input_value (IN): The input value.

        Returns:
            OUT: The output value.
        """
        query = input_value.get("query")
        spilt_queries = [query]
        try:
            spilt_queries = await self._split_v2(query)
        except Exception as e:
            logger.error(f"Split query error: {e}")
        result = {
            "query": query,
            "sub_queries": spilt_queries,
        }
        return result


    async def _split_v2(self, query: str) -> list[str]:
        messages = HumanPromptTemplate.from_template(self._prompt).format_messages(query=query)
        model_messages = ModelMessage.from_base_messages(messages)
        request = ModelRequest(model=self._model_name, messages=model_messages)
        response = await self._llm_client.generate(request=request)
        try:
            return json.loads(response.text)
        except:
            return [query]
