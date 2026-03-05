"""
SceneSandboxInitializer - 场景文件沙箱初始化器

在绑定了场景的agent运行时，将场景文件初始化到沙箱环境目录
支持多Agent隔离，每个Agent有独立的场景文件目录

设计原则:
- Agent隔离：每个Agent的场景文件放在独立子目录
- 自动检测：自动检测应用绑定的场景
- 文件写入：将场景文件写入沙箱工作目录
- 懒加载：首次需要时初始化，避免不必要的文件操作
- 动态路径：使用沙箱实际工作目录，支持local/docker/k8s等多种沙箱类型

目录结构:
{ sandbox.work_dir }/
└── .scenes/
    ├── {agent_name_1}/
    │   ├── scene1.md
    │   ├── scene2.md
    │   └── README.md
    └── {agent_name_2}/
        ├── scene1.md
        └── README.md

注意：沙箱工作目录根据沙箱类型动态确定：
- local沙箱：使用本地文件系统路径（如 /Users/xxx/pilot）
- docker沙箱：使用容器内路径（如 /home/ubuntu）
- k8s沙箱：使用容器内路径（如 /home/ubuntu）

使用方式:
    initializer = SceneSandboxInitializer(sandbox_manager)
    await initializer.initialize_scenes_for_agent(
        app_code=app.app_code,
        agent_name=agent_name,
        scenes=scenes
    )

    # 或在agent构建时自动调用
    await scene_sandbox_initializer.initialize_scenes_for_agent(
        app_code=app.app_code,
        agent_name=recipient.profile.name,
        scenes=app.scenes,
        sandbox_manager=sandbox_manager
    )
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from derisk.agent.core.sandbox_manager import SandboxManager

logger = logging.getLogger(__name__)


class SceneSandboxInitializer:
    """
    场景文件沙箱初始化器

    职责：
    1. 从API获取场景定义和文件内容
    2. 将场景文件写入沙箱工作目录（按Agent隔离）
    3. 维护场景文件索引
    4. 支持增量更新
    """

    # 场景文件在沙箱中的根目录
    SCENES_ROOT_DIR = ".scenes"

    def __init__(self, sandbox_manager: SandboxManager):
        """
        初始化场景文件沙箱初始化器

        Args:
            sandbox_manager: 沙箱管理器实例
        """
        self.sandbox_manager = sandbox_manager
        self._initialized_agents: set = set()  # 已初始化的Agent (app_code:agent_name)
        self._scene_files_cache: Dict[str, Dict[str, str]] = {}  # 场景文件缓存

    async def initialize_scenes_for_agent(
        self,
        app_code: str,
        agent_name: str,
        scenes: List[str],
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        为指定Agent初始化场景文件到沙箱

        Args:
            app_code: 应用代码
            agent_name: Agent名称（用于隔离目录）
            scenes: 场景ID列表
            force_refresh: 是否强制刷新（重新写入）

        Returns:
            初始化结果信息
        """
        if not scenes or len(scenes) == 0:
            logger.info(
                f"[SceneSandboxInitializer] No scenes to initialize for {app_code}/{agent_name}"
            )
            return {"success": True, "message": "No scenes", "files": []}

        # 检查是否已初始化
        cache_key = f"{app_code}:{agent_name}:{':'.join(sorted(scenes))}"
        if cache_key in self._initialized_agents and not force_refresh:
            logger.info(
                f"[SceneSandboxInitializer] Scenes already initialized for {app_code}/{agent_name}"
            )
            return {"success": True, "message": "Already initialized", "files": []}

        try:
            # 1. 获取场景文件内容
            scene_files = await self._fetch_scene_files(scenes)
            if not scene_files:
                logger.warning(
                    f"[SceneSandboxInitializer] No scene files found for {scenes}"
                )
                return {"success": True, "message": "No scene files found", "files": []}

            # 2. 写入沙箱（按Agent隔离）
            written_files = await self._write_scenes_to_sandbox(agent_name, scene_files)

            # 3. 更新缓存
            self._initialized_agents.add(cache_key)
            cache_key_app_agent = f"{app_code}:{agent_name}"
            self._scene_files_cache[cache_key_app_agent] = scene_files

            logger.info(
                f"[SceneSandboxInitializer] Initialized {len(written_files)} scene files "
                f"for {app_code}/{agent_name}"
            )

            scenes_dir = await self._get_agent_scenes_dir(agent_name)
            return {
                "success": True,
                "message": f"Initialized {len(written_files)} scene files",
                "files": written_files,
                "scenes_dir": scenes_dir,
                "agent_name": agent_name,
            }

        except Exception as e:
            logger.error(
                f"[SceneSandboxInitializer] Failed to initialize scenes: {e}",
                exc_info=True,
            )
            return {"success": False, "message": str(e), "files": []}

    async def _get_agent_scenes_dir(self, agent_name: str) -> str:
        """
        获取Agent的场景文件目录

        Args:
            agent_name: Agent名称

        Returns:
            场景文件目录路径
        """
        # 确保沙箱管理器已初始化
        if not self.sandbox_manager.initialized:
            logger.info(
                "[SceneSandboxInitializer] Waiting for sandbox manager initialization..."
            )
            if self.sandbox_manager.init_task:
                try:
                    await self.sandbox_manager.init_task
                except Exception as e:
                    logger.error(
                        f"[SceneSandboxInitializer] Sandbox initialization failed: {e}"
                    )
                    raise RuntimeError(f"Sandbox not initialized: {e}")

        # 获取沙箱工作目录
        work_dir = self.sandbox_manager.work_dir
        if not work_dir:
            raise RuntimeError(
                "Sandbox work_dir not available. "
                "Please ensure sandbox is properly initialized."
            )

        # 清理agent_name，避免路径问题
        safe_agent_name = "".join(
            c for c in agent_name if c.isalnum() or c in "-_"
        ).lower()
        if not safe_agent_name:
            safe_agent_name = "default_agent"
        return os.path.join(work_dir, self.SCENES_ROOT_DIR, safe_agent_name)

    async def _fetch_scene_files(self, scene_ids: List[str]) -> Dict[str, str]:
        """
        从API获取场景文件内容

        Args:
            scene_ids: 场景ID列表

        Returns:
            场景文件内容字典 {filename: content}
        """
        scene_files = {}

        try:
            # 使用sceneApi获取场景详情
            from derisk_serve.scene.api import _scenes_db

            for scene_id in scene_ids:
                # 先从内存缓存获取（如果API使用内存缓存）
                if scene_id in _scenes_db:
                    scene_data = _scenes_db[scene_id]
                    md_content = scene_data.get("md_content", "")
                    if md_content:
                        filename = f"{scene_id}.md"
                        scene_files[filename] = md_content
                        logger.debug(
                            f"[SceneSandboxInitializer] Fetched scene: {filename}"
                        )
                else:
                    # 尝试从数据库或其他存储获取
                    logger.warning(
                        f"[SceneSandboxInitializer] Scene not found in cache: {scene_id}"
                    )

        except ImportError:
            logger.warning(
                "[SceneSandboxInitializer] Cannot import scene api, scenes will not be loaded"
            )
        except Exception as e:
            logger.error(f"[SceneSandboxInitializer] Error fetching scenes: {e}")

        return scene_files

    async def _write_scenes_to_sandbox(
        self, agent_name: str, scene_files: Dict[str, str]
    ) -> List[str]:
        """
        将场景文件写入沙箱（按Agent隔离）

        Args:
            agent_name: Agent名称
            scene_files: 场景文件内容字典

        Returns:
            已写入的文件路径列表
        """
        written_files = []

        if not self.sandbox_manager or not self.sandbox_manager.client:
            logger.error(
                "[SceneSandboxInitializer] Sandbox manager or client not available"
            )
            return written_files

        scenes_dir = await self._get_agent_scenes_dir(agent_name)

        try:
            # 1. 创建场景目录
            await self._ensure_directory(scenes_dir)
            logger.info(
                f"[SceneSandboxInitializer] Created scenes directory: {scenes_dir}"
            )

            # 2. 写入每个场景文件
            for filename, content in scene_files.items():
                try:
                    file_path = os.path.join(scenes_dir, filename)
                    await self._write_file(file_path, content)
                    written_files.append(file_path)
                    logger.debug(
                        f"[SceneSandboxInitializer] Wrote scene file: {file_path}"
                    )
                except Exception as e:
                    logger.error(
                        f"[SceneSandboxInitializer] Failed to write {filename}: {e}"
                    )

            # 3. 创建索引文件
            if written_files:
                await self._create_index_file(agent_name, scenes_dir, scene_files)

        except Exception as e:
            logger.error(
                f"[SceneSandboxInitializer] Error writing scenes to sandbox: {e}",
                exc_info=True,
            )

        return written_files

    async def _ensure_directory(self, path: str) -> None:
        """
        确保目录存在

        Args:
            path: 目录路径
        """
        try:
            # 使用沙箱的shell命令创建目录
            import shlex

            command = f"mkdir -p {shlex.quote(path)}"

            result = await self.sandbox_manager.client.shell.exec_command(
                command=command, timeout=30.0, work_dir=None
            )

            if getattr(result, "status", None) != "completed":
                from derisk.sandbox.sandbox_utils import collect_shell_output

                output = collect_shell_output(result)
                raise RuntimeError(f"Failed to create directory: {output}")

        except Exception as e:
            logger.error(
                f"[SceneSandboxInitializer] Failed to ensure directory {path}: {e}"
            )
            raise

    async def _write_file(self, file_path: str, content: str) -> None:
        """
        写入文件到沙箱

        Args:
            file_path: 文件完整路径
            content: 文件内容
        """
        try:
            # 使用沙箱的file客户端写入文件
            if (
                hasattr(self.sandbox_manager.client, "file")
                and self.sandbox_manager.client.file
            ):
                await self.sandbox_manager.client.file.create(file_path, content)
            else:
                # 回退：使用shell命令写入
                import base64
                import shlex

                # 使用base64编码避免特殊字符问题
                content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                command = f"echo {content_b64} | base64 -d > {shlex.quote(file_path)}"

                result = await self.sandbox_manager.client.shell.exec_command(
                    command=command, timeout=30.0, work_dir=None
                )

                if getattr(result, "status", None) != "completed":
                    from derisk.sandbox.sandbox_utils import collect_shell_output

                    output = collect_shell_output(result)
                    raise RuntimeError(f"Failed to write file: {output}")

        except Exception as e:
            logger.error(
                f"[SceneSandboxInitializer] Failed to write file {file_path}: {e}"
            )
            raise

    async def _create_index_file(
        self, agent_name: str, scenes_dir: str, scene_files: Dict[str, str]
    ) -> None:
        """
        创建场景索引文件

        Args:
            agent_name: Agent名称
            scenes_dir: 场景目录
            scene_files: 场景文件字典
        """
        try:
            index_content = self._generate_index_content(agent_name, scene_files)
            index_path = os.path.join(scenes_dir, "README.md")
            await self._write_file(index_path, index_content)
            logger.info(f"[SceneSandboxInitializer] Created index file: {index_path}")
        except Exception as e:
            logger.warning(
                f"[SceneSandboxInitializer] Failed to create index file: {e}"
            )

    def _generate_index_content(
        self, agent_name: str, scene_files: Dict[str, str]
    ) -> str:
        """
        生成索引文件内容

        Args:
            agent_name: Agent名称
            scene_files: 场景文件字典

        Returns:
            Markdown格式的索引内容
        """
        lines = [
            f"# {agent_name} 的场景文件索引",
            "",
            f"本目录包含 **{agent_name}** Agent 的所有场景定义文件。",
            "",
            "## 文件列表",
            "",
        ]

        for filename in sorted(scene_files.keys()):
            scene_id = filename.replace(".md", "")
            lines.append(f"- [{filename}](./{filename}) - 场景ID: `{scene_id}`")

        lines.extend(
            [
                "",
                "## 使用说明",
                "",
                "场景文件使用 YAML Front Matter 格式定义，包含：",
                "- `id`: 场景唯一标识",
                "- `name`: 场景名称",
                "- `description`: 场景描述",
                "- `priority`: 优先级 (1-10)",
                "- `keywords`: 触发关键词列表",
                "- `allow_tools`: 允许使用的工具列表",
                "",
                "## 生成时间",
                "",
                f"{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ]
        )

        return "\n".join(lines)

    async def get_scene_file_path(
        self, agent_name: str, scene_id: str
    ) -> Optional[str]:
        """
        获取场景文件在沙箱中的路径

        Args:
            agent_name: Agent名称
            scene_id: 场景ID

        Returns:
            场景文件路径，如果未初始化则返回None
        """
        scenes_dir = await self._get_agent_scenes_dir(agent_name)
        file_path = os.path.join(scenes_dir, f"{scene_id}.md")
        return file_path

    async def read_scene_file(self, agent_name: str, scene_id: str) -> Optional[str]:
        """
        从沙箱读取场景文件内容

        Args:
            agent_name: Agent名称
            scene_id: 场景ID

        Returns:
            场景文件内容，如果文件不存在则返回None
        """
        file_path = await self.get_scene_file_path(agent_name, scene_id)

        try:
            if (
                hasattr(self.sandbox_manager.client, "file")
                and self.sandbox_manager.client.file
            ):
                file_info = await self.sandbox_manager.client.file.read(file_path)
                return file_info.content if file_info else None
            else:
                # 回退：使用shell命令读取
                import shlex

                command = f"cat {shlex.quote(file_path)}"

                result = await self.sandbox_manager.client.shell.exec_command(
                    command=command, timeout=10.0, work_dir=None
                )

                if getattr(result, "status", None) == "completed":
                    from derisk.sandbox.sandbox_utils import collect_shell_output

                    return collect_shell_output(result)

        except Exception as e:
            logger.error(
                f"[SceneSandboxInitializer] Failed to read scene file {scene_id}: {e}"
            )

        return None

    async def cleanup_agent(self, app_code: str, agent_name: str) -> None:
        """
        清理指定Agent的场景文件

        Args:
            app_code: 应用代码
            agent_name: Agent名称
        """
        try:
            scenes_dir = await self._get_agent_scenes_dir(agent_name)

            # 使用shell命令删除目录
            import shlex

            command = f"rm -rf {shlex.quote(scenes_dir)}"

            result = await self.sandbox_manager.client.shell.exec_command(
                command=command, timeout=30.0, work_dir=None
            )

            if getattr(result, "status", None) == "completed":
                logger.info(
                    f"[SceneSandboxInitializer] Cleaned up scenes directory: {scenes_dir}"
                )

                # 清理缓存
                keys_to_remove = [
                    k
                    for k in self._initialized_agents
                    if k.startswith(f"{app_code}:{agent_name}:")
                ]
                for key in keys_to_remove:
                    self._initialized_agents.discard(key)
                cache_key = f"{app_code}:{agent_name}"
                self._scene_files_cache.pop(cache_key, None)
            else:
                from derisk.sandbox.sandbox_utils import collect_shell_output

                output = collect_shell_output(result)
                logger.warning(
                    f"[SceneSandboxInitializer] Cleanup may have failed: {output}"
                )

        except Exception as e:
            logger.error(f"[SceneSandboxInitializer] Failed to cleanup: {e}")


# 全局实例缓存
_scene_initializer_cache: Dict[str, SceneSandboxInitializer] = {}


def get_scene_initializer(sandbox_manager: SandboxManager) -> SceneSandboxInitializer:
    """
    获取或创建场景初始化器

    Args:
        sandbox_manager: 沙箱管理器

    Returns:
        SceneSandboxInitializer 实例
    """
    cache_key = id(sandbox_manager)

    if cache_key not in _scene_initializer_cache:
        _scene_initializer_cache[cache_key] = SceneSandboxInitializer(sandbox_manager)

    return _scene_initializer_cache[cache_key]


async def initialize_scenes_for_agent(
    app_code: str, agent_name: str, scenes: List[str], sandbox_manager: SandboxManager
) -> Dict[str, Any]:
    """
    便捷函数：为Agent初始化场景文件

    Args:
        app_code: 应用代码
        agent_name: Agent名称（用于隔离）
        scenes: 场景ID列表
        sandbox_manager: 沙箱管理器

    Returns:
        初始化结果
    """
    initializer = get_scene_initializer(sandbox_manager)
    return await initializer.initialize_scenes_for_agent(
        app_code=app_code, agent_name=agent_name, scenes=scenes
    )


__all__ = [
    "SceneSandboxInitializer",
    "get_scene_initializer",
    "initialize_scenes_for_agent",
]
