"""
Scene Strategy Database Models

场景策略数据库模型，用于持久化场景配置
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, Boolean, Integer, JSON, DateTime
from sqlalchemy.orm import mapped_column

from derisk.storage.metadata import BaseDao, Model, dynamic_db_name


@dynamic_db_name("scene_strategy")
class SceneStrategyEntity(Model):
    """场景策略实体"""
    __tablename__ = "scene_strategy"
    
    id: int = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    scene_code: str = mapped_column(String(128), unique=True, nullable=False, comment="场景编码")
    scene_name: str = mapped_column(String(256), nullable=False, comment="场景名称")
    scene_type: str = mapped_column(String(64), nullable=False, default="custom", comment="场景类型")
    description: Optional[str] = mapped_column(Text, comment="场景描述")
    icon: Optional[str] = mapped_column(String(256), comment="场景图标")
    tags: Optional[str] = mapped_column(Text, comment="场景标签(JSON数组)")
    
    base_scene: Optional[str] = mapped_column(String(128), comment="继承的基础场景")
    
    system_prompt_config: Optional[str] = mapped_column(Text, comment="System Prompt配置(JSON)")
    context_policy_config: Optional[str] = mapped_column(Text, comment="上下文策略配置(JSON)")
    prompt_policy_config: Optional[str] = mapped_column(Text, comment="Prompt策略配置(JSON)")
    tool_policy_config: Optional[str] = mapped_column(Text, comment="工具策略配置(JSON)")
    hooks_config: Optional[str] = mapped_column(Text, comment="钩子配置(JSON数组)")
    extensions_config: Optional[str] = mapped_column(Text, comment="扩展配置(JSON)")
    
    is_builtin: bool = mapped_column(Boolean, default=False, comment="是否内置场景")
    is_active: bool = mapped_column(Boolean, default=True, comment="是否启用")
    
    user_code: Optional[str] = mapped_column(String(128), comment="创建用户")
    sys_code: Optional[str] = mapped_column(String(128), comment="所属系统")
    
    version: str = mapped_column(String(32), default="1.0.0", comment="版本号")
    author: Optional[str] = mapped_column(String(128), comment="作者")
    
    created_at: datetime = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: datetime = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    ext_metadata: Optional[str] = mapped_column(Text, comment="扩展元数据(JSON)")


@dynamic_db_name("scene_strategy")
class AppSceneBindingEntity(Model):
    """应用-场景绑定实体"""
    __tablename__ = "app_scene_binding"
    
    id: int = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    app_code: str = mapped_column(String(128), nullable=False, index=True, comment="应用编码")
    scene_code: str = mapped_column(String(128), nullable=False, index=True, comment="场景编码")
    
    is_primary: bool = mapped_column(Boolean, default=True, comment="是否主要场景")
    custom_overrides: Optional[str] = mapped_column(Text, comment="自定义覆盖配置(JSON)")
    
    user_code: Optional[str] = mapped_column(String(128), comment="创建用户")
    created_at: datetime = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: datetime = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class SceneStrategyDao(BaseDao):
    """场景策略DAO"""
    
    def create_scene(self, entity: SceneStrategyEntity) -> SceneStrategyEntity:
        """创建场景策略"""
        with self.session() as session:
            session.add(entity)
            session.commit()
            return entity
    
    def get_scene_by_code(self, scene_code: str) -> Optional[SceneStrategyEntity]:
        """根据编码获取场景"""
        with self.session() as session:
            return session.query(SceneStrategyEntity).filter(
                SceneStrategyEntity.scene_code == scene_code
            ).first()
    
    def list_scenes(
        self,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
        scene_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        include_builtin: bool = True,
    ) -> List[SceneStrategyEntity]:
        """列出场景"""
        with self.session() as session:
            query = session.query(SceneStrategyEntity)
            
            if user_code:
                query = query.filter(SceneStrategyEntity.user_code == user_code)
            if sys_code:
                query = query.filter(SceneStrategyEntity.sys_code == sys_code)
            if scene_type:
                query = query.filter(SceneStrategyEntity.scene_type == scene_type)
            if is_active is not None:
                query = query.filter(SceneStrategyEntity.is_active == is_active)
            if not include_builtin:
                query = query.filter(SceneStrategyEntity.is_builtin == False)
            
            return query.order_by(SceneStrategyEntity.created_at.desc()).all()
    
    def update_scene(self, scene_code: str, updates: Dict[str, Any]) -> Optional[SceneStrategyEntity]:
        """更新场景"""
        with self.session() as session:
            entity = session.query(SceneStrategyEntity).filter(
                SceneStrategyEntity.scene_code == scene_code
            ).first()
            if entity:
                for key, value in updates.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)
                session.commit()
            return entity
    
    def delete_scene(self, scene_code: str) -> bool:
        """删除场景"""
        with self.session() as session:
            entity = session.query(SceneStrategyEntity).filter(
                SceneStrategyEntity.scene_code == scene_code
            ).first()
            if entity and not entity.is_builtin:
                session.delete(entity)
                session.commit()
                return True
            return False


class AppSceneBindingDao(BaseDao):
    """应用-场景绑定DAO"""
    
    def create_binding(self, entity: AppSceneBindingEntity) -> AppSceneBindingEntity:
        """创建绑定"""
        with self.session() as session:
            session.add(entity)
            session.commit()
            return entity
    
    def get_binding(self, app_code: str, scene_code: str) -> Optional[AppSceneBindingEntity]:
        """获取绑定"""
        with self.session() as session:
            return session.query(AppSceneBindingEntity).filter(
                AppSceneBindingEntity.app_code == app_code,
                AppSceneBindingEntity.scene_code == scene_code,
            ).first()
    
    def list_bindings_by_app(self, app_code: str) -> List[AppSceneBindingEntity]:
        """获取应用的所有绑定"""
        with self.session() as session:
            return session.query(AppSceneBindingEntity).filter(
                AppSceneBindingEntity.app_code == app_code
            ).all()
    
    def get_primary_scene(self, app_code: str) -> Optional[AppSceneBindingEntity]:
        """获取应用的主要场景"""
        with self.session() as session:
            return session.query(AppSceneBindingEntity).filter(
                AppSceneBindingEntity.app_code == app_code,
                AppSceneBindingEntity.is_primary == True,
            ).first()
    
    def delete_binding(self, app_code: str, scene_code: str) -> bool:
        """删除绑定"""
        with self.session() as session:
            entity = session.query(AppSceneBindingEntity).filter(
                AppSceneBindingEntity.app_code == app_code,
                AppSceneBindingEntity.scene_code == scene_code,
            ).first()
            if entity:
                session.delete(entity)
                session.commit()
                return True
            return False
    
    def update_binding(self, app_code: str, scene_code: str, updates: Dict[str, Any]) -> Optional[AppSceneBindingEntity]:
        """更新绑定"""
        with self.session() as session:
            entity = session.query(AppSceneBindingEntity).filter(
                AppSceneBindingEntity.app_code == app_code,
                AppSceneBindingEntity.scene_code == scene_code,
            ).first()
            if entity:
                for key, value in updates.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)
                session.commit()
            return entity