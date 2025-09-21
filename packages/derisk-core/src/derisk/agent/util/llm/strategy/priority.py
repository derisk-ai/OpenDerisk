"""Priority strategy for LLM."""

import json
import logging
from typing import List, Optional, Union, Dict, Tuple, Any

from ..llm import LLMStrategy, LLMStrategyType, register_llm_strategy_cls

logger = logging.getLogger(__name__)


class LLMStrategyPriority(LLMStrategy):
    """Priority strategy for llm model service."""
    async def models(self) -> List[str]:
        all_models = await self._llm_client.models()
        return [item.model for item in all_models]

    @property
    def type(self) -> LLMStrategyType:
        """Return the strategy type."""
        return LLMStrategyType.Priority

    def my_models(self)-> Optional[List[str]]:
        if not self._context:
            raise ValueError("No context provided for priority strategy!")
        try:
            context: Union[str, List[str]] = self._context
            # 如果是字符串，先解析
            if isinstance(context, str):
                context = json.loads(context)

            # 确保是字符串列表
            return [str(item) for item in context]

        except json.JSONDecodeError:
            logger.error(f"模型策略[{self.type}]获取配置模型列表时异常!")
            raise ValueError(f"模型策略[{self.type}]获取配置模型列表时异常!「{self._context}」")


register_llm_strategy_cls(LLMStrategyType.Priority, LLMStrategyPriority)
