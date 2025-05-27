import asyncio
from typing import Optional

from derisk.core import LLMClient
from derisk.core.awel import MapOperator
from derisk.core.awel.task.base import IN, OUT
from derisk.rag.transformer.summary_extractor import SummaryExtractor
from derisk_serve.rag.api.schemas import KnowledgeSearchResponse, DocumentSearchResponse


class SummaryOperator(MapOperator[IN, OUT]):
    """The Base Assembler Operator."""

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str,
        prompt: Optional[str] = None,
        **kwargs,
    ):
        """Initialize the SummaryOperator.

        Args:
            llm_client (LLMClient): The LLM client.
            model_name (str): The model name.
            prompt (Optional[str]): The prompt template. Defaults to None.
        """
        self._extractor = SummaryExtractor(
            llm_client=llm_client,
            model_name=model_name,
            prompt=prompt,
        )
        super().__init__(**kwargs)

    async def map(self, input_value: IN) -> OUT:
        """Map input value to output value.

        Args:
            input_value (IN): The input value.

        Returns:
            OUT: The output value.
        """
        query_summary_map = {}
        # raw_query = input_value.pop("query")
        raw_query = input_value.raw_query
        summary_tasks = []
        references = input_value.references
        for query, candidates in references.items():
            text = "\n".join([chunk.get("content") for chunk in candidates])
            text += "\n query:" + query
            query_summary_map[query] = query
            summary_tasks.append(self._extractor.extract(text=text))
        summary_results = await asyncio.gather(*summary_tasks)
        for query, summary in zip(query_summary_map.keys(), summary_results):
            query_summary_map[query] = summary
        if len(summary_results) == 1:
            # only one query
            refine_summary = summary_results[0]
        else:
            refine_text = "\n".join(
                [
                    f"{sub_query}:{sub_summary}"
                    for sub_query, sub_summary in query_summary_map.items()
                ]
            )
            refine_text += "\n 用户初始问题:" + raw_query
            refine_summary = await self._extractor.extract(text=refine_text)
        document_response_list = []
        for query, reference in references.items():
            document_response_list.extend([
                DocumentSearchResponse(
                    content=r.get("content"),
                    score=r.get("score"),
                    doc_name=r.get("metadata").get("doc_name"),
                )
                for r in reference
            ])
        return KnowledgeSearchResponse(
            document_response_list=document_response_list,
            sub_queries=query_summary_map,
            summary_content=refine_summary,
            references=references,
            raw_query=raw_query,
        )
