from abc import ABC, abstractmethod
from typing import Any

from derisk.agent import AgentMessage, AgentContext


class ReasoningArgSupplier(ABC):
    _registry: dict[str, "ReasoningArgSupplier"] = {}

    @classmethod
    def register(cls, subclass):
        """
        Reasoning arg supplier register

        Example:
            @ReasoningArgSupplier.register
            def MySupplier(ReasoningArgSupplier):
                ...

        """

        if not issubclass(subclass, cls):
            raise TypeError(f"{subclass.__name__} must be subclass of {cls.__name__}")
        instance = subclass()
        if instance.name in cls._registry:
            raise ValueError(f"Supplier {instance.name} already registered!")
        cls._registry[instance.name] = instance
        return subclass

    @classmethod
    def get_supplier(cls, name, *args, **kwargs) -> "ReasoningArgSupplier":
        """
        Get supplier by name

          name:
            supplier name
        """

        return cls._registry.get(name)

    @classmethod
    def get_all_suppliers(cls) -> dict[str, "ReasoningArgSupplier"]:
        """
        Get all arg suppliers
        :return:
        """
        return cls._registry

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the reasoning-arg-supplier."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the description of the reasoning-arg-supplier."""

    @property
    @abstractmethod
    def arg_key(self) -> str:
        """Return name of the arg which the reasoning-arg-supplier supply."""

    @abstractmethod
    async def supply(
        self,
        prompt_param: dict,
        agent: Any,
        agent_context: AgentContext,
        received_message: AgentMessage,
        step_id: str,
        **kwargs,
    ) -> None:
        """Supply the arg value"""
