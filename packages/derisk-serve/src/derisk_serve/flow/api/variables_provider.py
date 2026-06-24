from typing import List, Literal, Optional

from derisk.core.interface.variables import (
    BUILTIN_VARIABLES_CORE_AGENTS,
    BUILTIN_VARIABLES_CORE_DATASOURCES,
    BUILTIN_VARIABLES_CORE_EMBEDDINGS,
    BUILTIN_VARIABLES_CORE_FLOW_NODES,
    BUILTIN_VARIABLES_CORE_FLOWS,
    BUILTIN_VARIABLES_CORE_KNOWLEDGE_SPACES,
    BUILTIN_VARIABLES_CORE_LLMS,
    BUILTIN_VARIABLES_CORE_SECRETS,
    BUILTIN_VARIABLES_CORE_VARIABLES,
    BuiltinVariablesProvider,
    StorageVariables,
)

from ..service.service import Service
from .endpoints import get_service, get_variable_service
from .schemas import ServerResponse


class BuiltinFlowVariablesProvider(BuiltinVariablesProvider):
    """Builtin flow variables provider.

    Provide all flows by variables "${derisk.core.flow.flows}"
    """

    name = BUILTIN_VARIABLES_CORE_FLOWS

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        service: Service = get_service()
        page_result = service.get_list_by_page(
            {
                "user_name": user_name,
                "sys_code": sys_code,
            },
            1,
            1000,
        )
        flows: List[ServerResponse] = page_result.items
        variables = []
        for flow in flows:
            variables.append(
                StorageVariables(
                    key=key,
                    name=flow.name,
                    label=flow.label,
                    value=flow.uid,
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                    description=flow.description,
                )
            )
        return variables


class BuiltinNodeVariablesProvider(BuiltinVariablesProvider):
    """Builtin node variables provider.

    Provide all nodes by variables "${derisk.core.flow.nodes}"
    """

    name = BUILTIN_VARIABLES_CORE_FLOW_NODES

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        from derisk.core.awel.flow.base import _OPERATOR_REGISTRY

        metadata_list = _OPERATOR_REGISTRY.metadata_list()
        variables = []
        for metadata in metadata_list:
            variables.append(
                StorageVariables(
                    key=key,
                    name=metadata["name"],
                    label=metadata["label"],
                    value=metadata["id"],
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                    description=metadata.get("description"),
                )
            )
        return variables


class BuiltinAllVariablesProvider(BuiltinVariablesProvider):
    """Builtin all variables provider.

    Provide all variables by variables "${derisk.core.variables}"
    """

    name = BUILTIN_VARIABLES_CORE_VARIABLES

    def _get_variables_from_db(
        self,
        key: str,
        scope: str,
        scope_key: Optional[str],
        sys_code: Optional[str],
        user_name: Optional[str],
        category: Literal["common", "secret"] = "common",
    ) -> List[StorageVariables]:
        storage_variables = get_variable_service().list_all_variables(category)
        variables = []
        for var in storage_variables:
            variables.append(
                StorageVariables(
                    key=key,
                    name=var.name,
                    label=var.label,
                    value=var.value,
                    category=var.category,
                    value_type=var.value_type,
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                    enabled=1 if var.enabled else 0,
                    description=var.description,
                )
            )
        return variables

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables.

        TODO: Return all builtin variables
        """
        return self._get_variables_from_db(key, scope, scope_key, sys_code, user_name)


class BuiltinAllSecretVariablesProvider(BuiltinAllVariablesProvider):
    """Builtin all secret variables provider.

    Provide all secret variables by variables "${derisk.core.secrets}"
    """

    name = BUILTIN_VARIABLES_CORE_SECRETS

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        return self._get_variables_from_db(
            key, scope, scope_key, sys_code, user_name, "secret"
        )


class BuiltinLLMVariablesProvider(BuiltinVariablesProvider):
    """Builtin LLM variables provider.

    Provide all LLM variables by variables "${derisk.core.llmv}"
    """

    name = BUILTIN_VARIABLES_CORE_LLMS

    def support_async(self) -> bool:
        """Whether the dynamic options support async."""
        return True

    async def _get_models(
        self,
        key: str,
        scope: str,
        scope_key: Optional[str],
        sys_code: Optional[str],
        user_name: Optional[str],
        expect_worker_type: str = "llm",
    ) -> List[StorageVariables]:
        model_names: List[str] = []
        system_app = self.system_app
        if system_app and system_app.config:
            agent_llm_conf = system_app.config.get("agent.llm")
            if not agent_llm_conf:
                agent_conf = system_app.config.get("agent")
                if isinstance(agent_conf, dict):
                    agent_llm_conf = agent_conf.get("llm")

            if agent_llm_conf:
                if isinstance(agent_llm_conf.get("provider"), list):
                    for p_conf in agent_llm_conf.get("provider"):
                        if isinstance(p_conf, dict) and "model" in p_conf:
                            p_models = p_conf.get("model")
                            if isinstance(p_models, list):
                                for m in p_models:
                                    if isinstance(m, dict) and "name" in m:
                                        model_names.append(m.get("name"))
                if isinstance(agent_llm_conf.get("models"), list):
                    for m in agent_llm_conf.get("models"):
                        if isinstance(m, dict) and "model" in m:
                            model_names.append(m.get("model"))
                elif agent_llm_conf.get("model"):
                    model_names.append(agent_llm_conf.get("model"))

        seen = set()
        variables = []
        for worker_name in model_names:
            if not worker_name or worker_name in seen:
                continue
            seen.add(worker_name)
            variables.append(
                StorageVariables(
                    key=key,
                    name=worker_name,
                    label=worker_name,
                    value=worker_name,
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                )
            )
        return variables

    async def async_get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        return await self._get_models(key, scope, scope_key, sys_code, user_name)

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        raise NotImplementedError(
            "Not implemented get variables sync, please use async_get_variables"
        )


class BuiltinEmbeddingsVariablesProvider(BuiltinLLMVariablesProvider):
    """Builtin embeddings variables provider.

    Provide all embeddings variables by variables "${derisk.core.embeddings}"
    """

    name = BUILTIN_VARIABLES_CORE_EMBEDDINGS

    async def async_get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        return await self._get_models(
            key, scope, scope_key, sys_code, user_name, "text2vec"
        )


class BuiltinDatasourceVariablesProvider(BuiltinVariablesProvider):
    """Builtin datasource variables provider.

    Provide all datasource variables by variables "${derisk.core.datasource}"
    """

    name = BUILTIN_VARIABLES_CORE_DATASOURCES

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        from derisk_serve.datasource.service.service import (
            DatasourceServeResponse,
            Service,
        )

        all_datasource: List[DatasourceServeResponse] = Service.get_instance(
            self.system_app
        ).list()

        variables = []
        for datasource in all_datasource:
            label = f"[{datasource.db_type}]{datasource.db_name}"
            variables.append(
                StorageVariables(
                    key=key,
                    name=datasource.db_name,
                    label=label,
                    value=datasource.db_name,
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                    description=datasource.comment,
                )
            )
        return variables


class BuiltinAgentsVariablesProvider(BuiltinVariablesProvider):
    """Builtin agents variables provider.

    Provide all agents variables by variables "${derisk.core.agent.agents}"
    """

    name = BUILTIN_VARIABLES_CORE_AGENTS

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        from derisk.agent.core.agent_manage import get_agent_manager

        agent_manager = get_agent_manager(self.system_app)
        agents = agent_manager.list_agents()
        variables = []
        for agent in agents:
            variables.append(
                StorageVariables(
                    key=key,
                    name=agent["name"],
                    label=agent["name"],
                    value=agent["name"],
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                    description=agent["desc"],
                )
            )
        return variables


class BuiltinKnowledgeSpacesVariablesProvider(BuiltinVariablesProvider):
    """Builtin knowledge variables provider.

    Provide all knowledge variables by variables "${derisk.core.knowledge_spaces}"
    """

    name = BUILTIN_VARIABLES_CORE_KNOWLEDGE_SPACES

    def get_variables(
        self,
        key: str,
        scope: str = "global",
        scope_key: Optional[str] = None,
        sys_code: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> List[StorageVariables]:
        """Get the builtin variables."""
        # TODO: rewire to new knowledge module (Task #9)
        from derisk_serve.rag.service.service import Service, SpaceServeRequest  # type: ignore

        # TODO: Query with user_name and sys_code
        knowledge_list = Service.get_instance(self.system_app).get_list(
            SpaceServeRequest()
        )
        variables = []
        for k in knowledge_list:
            variables.append(
                StorageVariables(
                    key=key,
                    name=k.name,
                    label=k.name,
                    value=k.name,
                    scope=scope,
                    scope_key=scope_key,
                    sys_code=sys_code,
                    user_name=user_name,
                    description=k.desc,
                )
            )
        return variables
