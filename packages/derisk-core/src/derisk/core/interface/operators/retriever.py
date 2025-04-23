"""The Abstract Retriever Operator."""

from abc import abstractmethod

from derisk.core.awel import MapOperator
from derisk.core.awel.task.base import IN, OUT


class RetrieverOperator(MapOperator[IN, OUT]):
    """The Abstract Retriever Operator."""

    async def map(self, input_value: IN) -> OUT:
        """Map input value to output value.

        Args:
            input_value (IN): The input value.

        Returns:
            OUT: The output value.
        """
        # The retrieve function is blocking, so we need to wrap it in a
        # blocking_func_to_async.
        return await self.aretrieve(query=input_value)

    @abstractmethod
    async def aretrieve(self, query: IN) -> OUT:
        """Async Retrieve data for input value."""
