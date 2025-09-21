from abc import ABC, abstractmethod
from typing import Any, Optional

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
    def detail(self) -> Optional[str]:
        """Return the detail description of the reasoning-arg-supplier."""
        return None

    @property
    @abstractmethod
    def arg_key(self) -> str:
        """Return name of the arg which the reasoning-arg-supplier supply."""

    @property
    def params(self):
        """Return the params of the reasoning-arg-supplier."""
        return None

    @abstractmethod
    async def supply(
        self,
        prompt_param: dict,
        agent: Any,
        agent_context: Optional[AgentContext] = None,
        received_message: Optional[AgentMessage] = None,
        step_id: Optional[str] = None,
        current_step_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> None:
        """Supply the arg value"""
