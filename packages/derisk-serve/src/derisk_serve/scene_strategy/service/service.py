"""
Scene Strategy Service

场景策略服务层，提供业务逻辑处理
"""

import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from derisk.component import SystemApp, BaseComponent, ComponentType
from derisk_serve.scene_strategy.models.models import (
    SceneStrategyEntity,
    SceneStrategyDao,
    AppSceneBindingEntity,
    AppSceneBindingDao,
)
from derisk_serve.scene_strategy.api.schemas import (
    SceneStrategyCreateRequest,
    SceneStrategyUpdateRequest,
    SceneStrategyResponse,
    SceneStrategyListResponse,
    SceneStrategyBriefResponse,
    AppSceneBindingRequest,
    AppSceneBindingResponse,
    PreviewSystemPromptRequest,
    PreviewSystemPromptResponse,
    SystemPromptTemplateSchema,
    ContextPolicySchema,
    PromptPolicySchema,
    ToolPolicySchema,
    ReasoningPolicySchema,
    HookConfigSchema,
)
from derisk.agent.core_v2.scene_strategy import (
    SceneStrategyRegistry,
    SceneStrategy,
    SystemPromptTemplate,
    ContextProcessorExtension,
    ToolSelectorExtension,
    OutputRendererExtension,
)
from derisk.agent.core_v2.task_scene import (
    ContextPolicy,
    PromptPolicy,
    ToolPolicy,
)

logger = logging.getLogger(__name__)


class SceneStrategyService(BaseComponent):
    """场景策略服务"""
    
    name = "scene_strategy_service"
    
    def __init__(self, system_app: SystemApp):
        super().__init__(system_app)
        self._scene_dao: Optional[SceneStrategyDao] = None
        self._binding_dao: Optional[AppSceneBindingDao] = None
    
    def init_app(self, system_app: SystemApp):
        self.system_app = system_app
        self._scene_dao = SceneStrategyDao()
        self._binding_dao = AppSceneBindingDao()
        self._sync_builtin_scenes()
    
    def _sync_builtin_scenes(self):
        """同步内置场景到数据库"""
        builtin_scenes = [
            ("general", "通用模式", "适用于大多数任务的通用场景"),
            ("coding", "编码模式", "针对代码编写优化的专业场景"),
            ("analysis", "分析模式", "数据分析和日志分析场景"),
            ("creative", "创意模式", "创意写作和头脑风暴场景"),
            ("research", "研究模式", "深度研究和信息收集场景"),
        ]
        
        for code, name, desc in builtin_scenes:
            existing = self._scene_dao.get_scene_by_code(code)
            if not existing:
                entity = SceneStrategyEntity(
                    scene_code=code,
                    scene_name=name,
                    scene_type="builtin",
                    description=desc,
                    is_builtin=True,
                )
                self._scene_dao.create_scene(entity)
    
    async def create_scene(
        self,
        request: SceneStrategyCreateRequest,
        user_code: Optional[str] = None,
    ) -> SceneStrategyResponse:
        """创建场景策略"""
        existing = self._scene_dao.get_scene_by_code(request.scene_code)
        if existing:
            raise ValueError(f"Scene code '{request.scene_code}' already exists")
        
        entity = SceneStrategyEntity(
            scene_code=request.scene_code,
            scene_name=request.scene_name,
            scene_type=request.scene_type,
            description=request.description,
            icon=request.icon,
            tags=json.dumps(request.tags) if request.tags else None,
            base_scene=request.base_scene,
            system_prompt_config=self._serialize_field(request.system_prompt),
            context_policy_config=self._serialize_field(request.context_policy),
            prompt_policy_config=self._serialize_field(request.prompt_policy),
            tool_policy_config=self._serialize_field(request.tool_policy),
            hooks_config=self._serialize_field(request.hooks),
            user_code=user_code or request.user_code,
            sys_code=request.sys_code,
            is_builtin=False,
            is_active=True,
        )
        
        entity = self._scene_dao.create_scene(entity)
        
        self._register_to_memory(entity)
        
        return self._entity_to_response(entity)
    
    async def get_scene(self, scene_code: str) -> Optional[SceneStrategyResponse]:
        """获取场景策略"""
        entity = self._scene_dao.get_scene_by_code(scene_code)
        if entity:
            return self._entity_to_response(entity)
        return None
    
    async def list_scenes(
        self,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
        scene_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        include_builtin: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> SceneStrategyListResponse:
        """列出场景策略"""
        entities = self._scene_dao.list_scenes(
            user_code=user_code,
            sys_code=sys_code,
            scene_type=scene_type,
            is_active=is_active,
            include_builtin=include_builtin,
        )
        
        total = len(entities)
        start = (page - 1) * page_size
        end = start + page_size
        items = [self._entity_to_response(e) for e in entities[start:end]]
        
        return SceneStrategyListResponse(
            total_count=total,
            total_page=(total + page_size - 1) // page_size,
            current_page=page,
            page_size=page_size,
            items=items,
        )
    
    async def update_scene(
        self,
        scene_code: str,
        request: SceneStrategyUpdateRequest,
    ) -> Optional[SceneStrategyResponse]:
        """更新场景策略"""
        entity = self._scene_dao.get_scene_by_code(scene_code)
        if not entity:
            return None
        
        if entity.is_builtin:
            raise ValueError("Cannot modify builtin scene")
        
        updates = {}
        if request.scene_name is not None:
            updates["scene_name"] = request.scene_name
        if request.description is not None:
            updates["description"] = request.description
        if request.icon is not None:
            updates["icon"] = request.icon
        if request.tags is not None:
            updates["tags"] = json.dumps(request.tags)
        if request.is_active is not None:
            updates["is_active"] = request.is_active
        if request.system_prompt is not None:
            updates["system_prompt_config"] = self._serialize_field(request.system_prompt)
        if request.context_policy is not None:
            updates["context_policy_config"] = self._serialize_field(request.context_policy)
        if request.prompt_policy is not None:
            updates["prompt_policy_config"] = self._serialize_field(request.prompt_policy)
        if request.tool_policy is not None:
            updates["tool_policy_config"] = self._serialize_field(request.tool_policy)
        if request.hooks is not None:
            updates["hooks_config"] = self._serialize_field(request.hooks)
        
        entity = self._scene_dao.update_scene(scene_code, updates)
        
        if entity:
            self._register_to_memory(entity)
            return self._entity_to_response(entity)
        
        return None
    
    async def delete_scene(self, scene_code: str) -> bool:
        """删除场景策略"""
        entity = self._scene_dao.get_scene_by_code(scene_code)
        if entity and entity.is_builtin:
            raise ValueError("Cannot delete builtin scene")
        
        return self._scene_dao.delete_scene(scene_code)
    
    async def bind_scene_to_app(
        self,
        request: AppSceneBindingRequest,
    ) -> AppSceneBindingResponse:
        """将场景绑定到应用"""
        scene = self._scene_dao.get_scene_by_code(request.scene_code)
        if not scene:
            raise ValueError(f"Scene '{request.scene_code}' not found")
        
        existing = self._binding_dao.get_binding(request.app_code, request.scene_code)
        if existing:
            entity = self._binding_dao.update_binding(
                request.app_code,
                request.scene_code,
                {
                    "is_primary": request.is_primary,
                    "custom_overrides": json.dumps(request.custom_overrides),
                }
            )
        else:
            entity = AppSceneBindingEntity(
                app_code=request.app_code,
                scene_code=request.scene_code,
                is_primary=request.is_primary,
                custom_overrides=json.dumps(request.custom_overrides),
            )
            entity = self._binding_dao.create_binding(entity)
        
        return AppSceneBindingResponse(
            app_code=entity.app_code,
            scene_code=entity.scene_code,
            scene_name=scene.scene_name,
            scene_icon=scene.icon,
            is_primary=entity.is_primary,
            custom_overrides=request.custom_overrides,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
    
    async def unbind_scene_from_app(self, app_code: str, scene_code: str) -> bool:
        """解除应用场景绑定"""
        return self._binding_dao.delete_binding(app_code, scene_code)
    
    async def get_app_scenes(self, app_code: str) -> List[AppSceneBindingResponse]:
        """获取应用绑定的所有场景"""
        bindings = self._binding_dao.list_bindings_by_app(app_code)
        results = []
        
        for binding in bindings:
            scene = self._scene_dao.get_scene_by_code(binding.scene_code)
            if scene:
                results.append(AppSceneBindingResponse(
                    app_code=binding.app_code,
                    scene_code=binding.scene_code,
                    scene_name=scene.scene_name,
                    scene_icon=scene.icon,
                    is_primary=binding.is_primary,
                    custom_overrides=json.loads(binding.custom_overrides or "{}"),
                    created_at=binding.created_at,
                    updated_at=binding.updated_at,
                ))
        
        return results
    
    async def get_app_primary_scene(self, app_code: str) -> Optional[SceneStrategyResponse]:
        """获取应用的主要场景"""
        binding = self._binding_dao.get_primary_scene(app_code)
        if binding:
            entity = self._scene_dao.get_scene_by_code(binding.scene_code)
            if entity:
                response = self._entity_to_response(entity)
                custom_overrides = json.loads(binding.custom_overrides or "{}")
                if custom_overrides:
                    response = self._apply_overrides(response, custom_overrides)
                return response
        return None
    
    async def preview_system_prompt(
        self,
        request: PreviewSystemPromptRequest,
    ) -> PreviewSystemPromptResponse:
        """预览System Prompt"""
        template = None
        
        if request.scene_code:
            entity = self._scene_dao.get_scene_by_code(request.scene_code)
            if entity and entity.system_prompt_config:
                schema = SystemPromptTemplateSchema(**json.loads(entity.system_prompt_config))
                template = self._schema_to_prompt_template(schema)
        
        if request.system_prompt and not template:
            template = self._schema_to_prompt_template(request.system_prompt)
        
        if not template:
            return PreviewSystemPromptResponse(
                rendered_prompt="",
                scene_code=request.scene_code,
                variables_used=[],
            )
        
        rendered = template.build(request.variables)
        variables_used = list(request.variables.keys())
        
        return PreviewSystemPromptResponse(
            rendered_prompt=rendered,
            scene_code=request.scene_code,
            variables_used=variables_used,
        )
    
    async def list_brief_scenes(
        self,
        include_builtin: bool = True,
        user_code: Optional[str] = None,
    ) -> List[SceneStrategyBriefResponse]:
        """获取场景简要列表（用于选择器）"""
        entities = self._scene_dao.list_scenes(
            user_code=user_code,
            is_active=True,
            include_builtin=include_builtin,
        )
        
        return [
            SceneStrategyBriefResponse(
                scene_code=e.scene_code,
                scene_name=e.scene_name,
                scene_type=e.scene_type,
                description=e.description,
                icon=e.icon,
                is_builtin=e.is_builtin,
                is_active=e.is_active,
            )
            for e in entities
        ]
    
    async def clone_scene(
        self,
        scene_code: str,
        new_scene_code: str,
        new_scene_name: str,
        user_code: Optional[str] = None,
    ) -> SceneStrategyResponse:
        """克隆场景"""
        source = self._scene_dao.get_scene_by_code(scene_code)
        if not source:
            raise ValueError(f"Scene '{scene_code}' not found")
        
        existing = self._scene_dao.get_scene_by_code(new_scene_code)
        if existing:
            raise ValueError(f"Scene code '{new_scene_code}' already exists")
        
        entity = SceneStrategyEntity(
            scene_code=new_scene_code,
            scene_name=new_scene_name,
            scene_type="custom",
            description=source.description,
            icon=source.icon,
            tags=source.tags,
            base_scene=scene_code,
            system_prompt_config=source.system_prompt_config,
            context_policy_config=source.context_policy_config,
            prompt_policy_config=source.prompt_policy_config,
            tool_policy_config=source.tool_policy_config,
            hooks_config=source.hooks_config,
            user_code=user_code,
            is_builtin=False,
            is_active=True,
        )
        
        entity = self._scene_dao.create_scene(entity)
        return self._entity_to_response(entity)
    
    async def export_scene(self, scene_code: str) -> Dict[str, Any]:
        """导出场景配置"""
        entity = self._scene_dao.get_scene_by_code(scene_code)
        if not entity:
            raise ValueError(f"Scene '{scene_code}' not found")
        
        response = self._entity_to_response(entity)
        return response.dict()
    
    async def import_scene(
        self,
        config: Dict[str, Any],
        user_code: Optional[str] = None,
    ) -> SceneStrategyResponse:
        """导入场景配置"""
        request = SceneStrategyCreateRequest(**config)
        return await self.create_scene(request, user_code)
    
    def _serialize_field(self, value: Any) -> Optional[str]:
        """序列化字段"""
        if value is None:
            return None
        if isinstance(value, dict):
            return json.dumps(value)
        if hasattr(value, 'dict'):
            return json.dumps(value.dict())
        return json.dumps(value)
    
    def _deserialize_field(self, value: Optional[str]) -> Optional[Dict[str, Any]]:
        """反序列化字段"""
        if not value:
            return None
        return json.loads(value)
    
    def _entity_to_response(self, entity: SceneStrategyEntity) -> SceneStrategyResponse:
        """将实体转换为响应"""
        try:
            tags = json.loads(entity.tags) if entity.tags else []
        except:
            tags = []
        
        return SceneStrategyResponse(
            scene_code=entity.scene_code,
            scene_name=entity.scene_name,
            scene_type=entity.scene_type,
            description=entity.description,
            icon=entity.icon,
            tags=tags,
            base_scene=entity.base_scene,
            system_prompt=self._deserialize_to_schema(entity.system_prompt_config, SystemPromptTemplateSchema),
            context_policy=self._deserialize_to_schema(entity.context_policy_config, ContextPolicySchema),
            prompt_policy=self._deserialize_to_schema(entity.prompt_policy_config, PromptPolicySchema),
            tool_policy=self._deserialize_to_schema(entity.tool_policy_config, ToolPolicySchema),
            hooks=self._deserialize_to_list(entity.hooks_config, HookConfigSchema),
            is_builtin=entity.is_builtin,
            is_active=entity.is_active,
            user_code=entity.user_code,
            sys_code=entity.sys_code,
            version=entity.version,
            author=entity.author,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
    
    def _deserialize_to_schema(self, value: Optional[str], schema_class):
        """反序列化为指定Schema"""
        if not value:
            return None
        try:
            return schema_class(**json.loads(value))
        except:
            return None
    
    def _deserialize_to_list(self, value: Optional[str], schema_class) -> List:
        """反序列化为列表"""
        if not value:
            return []
        try:
            items = json.loads(value)
            return [schema_class(**item) for item in items]
        except:
            return []
    
    def _schema_to_prompt_template(self, schema: SystemPromptTemplateSchema) -> SystemPromptTemplate:
        """将Schema转换为Prompt模板"""
        return SystemPromptTemplate(
            base_template=schema.base_template or "",
            role_definition=schema.role_definition or "",
            capabilities=schema.capabilities or "",
            constraints=schema.constraints or "",
            guidelines=schema.guidelines or "",
            examples=schema.examples or "",
            sections_order=schema.sections_order,
        )
    
    def _register_to_memory(self, entity: SceneStrategyEntity):
        """注册场景到内存"""
        pass
    
    def _apply_overrides(
        self,
        response: SceneStrategyResponse,
        overrides: Dict[str, Any],
    ) -> SceneStrategyResponse:
        """应用自定义覆盖"""
        if "prompt_policy" in overrides and response.prompt_policy:
            policy_dict = response.prompt_policy.dict()
            policy_dict.update(overrides["prompt_policy"])
            response.prompt_policy = PromptPolicySchema(**policy_dict)
        
        if "context_policy" in overrides and response.context_policy:
            policy_dict = response.context_policy.dict()
            policy_dict.update(overrides["context_policy"])
            response.context_policy = ContextPolicySchema(**policy_dict)
        
        return response
    
    @classmethod
    def get_instance(cls, system_app: SystemApp) -> "SceneStrategyService":
        """获取服务实例"""
        return system_app.get_component(cls.name, SceneStrategyService)