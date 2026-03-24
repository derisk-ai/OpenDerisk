"""Media Generation Tools.

Agent tools for generating images and videos using AI models.
Integrates with MediaGenProviderRegistry for multi-provider support
and AgentFileSystem/d-attach for file delivery.
"""

import logging
import os
import uuid
from typing import Any, Dict, Optional

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import Artifact, ToolResult

logger = logging.getLogger(__name__)

_GENERATE_IMAGE_PROMPT = """使用 AI 模型生成图片。

**使用场景：**
- 根据文字描述生成图片 (如 DALL-E 3, Stable Diffusion, Flux)
- 生成数据可视化、插图、概念图等
- 生成的图片会自动保存并交付给用户

**推荐用法：**
```
# 生成一张图片
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", model="dall-e-3", size="1024x1024")

# 生成高质量图片
generate_image(prompt="产品界面设计图", model="dall-e-3", quality="hd", size="1792x1024")
```

**注意事项：**
- 生成图片需要消耗 API 配额，请合理使用
- 图片生成通常需要 10-30 秒
- 生成的图片会自动上传到存储并生成交付链接
"""

_GENERATE_VIDEO_PROMPT = """使用 AI 模型生成视频。

**使用场景：**
- 根据文字描述生成短视频 (如 Sora, Runway)
- 生成产品演示、概念视频等
- 生成的视频会自动保存并交付给用户

**推荐用法：**
```
# 生成一段视频
generate_video(prompt="日落时分海浪拍打沙滩的慢镜头", model="sora", duration=5)
```

**注意事项：**
- 视频生成需要较长时间 (通常 1-5 分钟)
- 视频生成消耗较多 API 配额
- 生成的视频会自动上传到存储并生成交付链接
"""


def _get_agent_file_system(context: Optional[ToolContext]) -> Any:
    """Get AgentFileSystem from tool context."""
    if context is None:
        return None

    if isinstance(context, dict):
        # From config dict
        afs = context.get("agent_file_system")
        if afs:
            return afs
        config = context.get("config", {})
        afs = config.get("agent_file_system")
        if afs:
            return afs
        # From sandbox_manager
        sm = config.get("sandbox_manager") or context.get("sandbox_manager")
        if sm and hasattr(sm, "agent_file_system"):
            return sm.agent_file_system
        # From sandbox_client
        sc = config.get("sandbox_client") or context.get("sandbox_client")
        if sc and hasattr(sc, "agent_file_system"):
            return sc.agent_file_system
        return None

    # ToolContext object
    afs = context.config.get("agent_file_system")
    if afs:
        return afs
    afs = context.get_resource("agent_file_system")
    if afs:
        return afs
    # From sandbox_manager
    sm = context.config.get("sandbox_manager")
    if sm and hasattr(sm, "agent_file_system"):
        return sm.agent_file_system
    # From sandbox_client
    sc = context.config.get("sandbox_client")
    if sc and hasattr(sc, "agent_file_system"):
        return sc.agent_file_system
    return None


def _resolve_api_key(provider_name: str, context: Optional[ToolContext]) -> Optional[str]:
    """Resolve API key from context config or environment variables."""
    from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

    # 1. From context config
    if context:
        config = context.config if not isinstance(context, dict) else context
        media_gen_config = config.get("media_gen_config") if isinstance(config, dict) else config.get("media_gen_config")
        if media_gen_config:
            if hasattr(media_gen_config, "api_key") and media_gen_config.api_key:
                return media_gen_config.api_key
            if isinstance(media_gen_config, dict) and media_gen_config.get("api_key"):
                return media_gen_config["api_key"]

    # 2. From provider-specific env var
    env_key = MediaGenProviderRegistry.get_env_key(provider_name)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val

    # 3. Common fallbacks
    for key in ["OPENAI_API_KEY", "MEDIA_GEN_API_KEY"]:
        val = os.environ.get(key)
        if val:
            return val

    return None


class GenerateImageTool(ToolBase):
    """AI 图片生成工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_image",
            display_name="Generate Image",
            description=_GENERATE_IMAGE_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            timeout=120,
            tags=["image", "generation", "ai", "media", "dall-e"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "图片描述 (英文效果更佳)",
                },
                "provider": {
                    "type": "string",
                    "description": "生成服务提供商",
                    "default": "openai",
                },
                "model": {
                    "type": "string",
                    "description": "模型名称 (dall-e-3, dall-e-2, gpt-image-1 等)",
                    "default": "dall-e-3",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1024x1792", "1792x1024", "512x512", "256x256"],
                    "description": "图片尺寸",
                    "default": "1024x1024",
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "hd"],
                    "description": "图片质量 (dall-e-3 支持 hd)",
                    "default": "standard",
                },
                "style": {
                    "type": "string",
                    "enum": ["vivid", "natural"],
                    "description": "图片风格 (dall-e-3 支持)",
                    "default": "vivid",
                },
                "description": {
                    "type": "string",
                    "description": "交付文件描述 (可选)",
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        prompt = args.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail(error="prompt 不能为空", tool_name=self.name)

        provider_name = args.get("provider", "openai")
        model = args.get("model", "dall-e-3")
        description = args.get("description", "").strip() or f"AI 生成图片: {prompt[:50]}"

        # Resolve provider
        from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

        api_key = _resolve_api_key(provider_name, context)
        if not api_key:
            return ToolResult.fail(
                error=f"未找到 {provider_name} 的 API Key。请设置环境变量或在配置中提供。",
                tool_name=self.name,
            )

        provider = MediaGenProviderRegistry.create_provider(
            name=provider_name, api_key=api_key
        )
        if not provider:
            available = list(MediaGenProviderRegistry.list_providers().keys())
            return ToolResult.fail(
                error=f"未找到生成服务 '{provider_name}'。可用服务: {available}",
                tool_name=self.name,
            )

        # Generate image
        try:
            gen_kwargs = {
                k: v
                for k, v in args.items()
                if k in ("size", "quality", "style") and v
            }
            result = await provider.generate_image(prompt, model, **gen_kwargs)
        except NotImplementedError:
            return ToolResult.fail(
                error=f"服务 '{provider_name}' 不支持图片生成",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[generate_image] Generation failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"图片生成失败: {e}",
                tool_name=self.name,
            )

        # Save and deliver
        file_name = f"generated_image_{uuid.uuid4().hex[:8]}.{result.format}"
        return await self._save_and_deliver(
            result, file_name, description, context, prompt
        )

    async def _save_and_deliver(
        self,
        result: Any,
        file_name: str,
        description: str,
        context: Optional[ToolContext],
        prompt: str,
    ) -> ToolResult:
        """Save generated media to storage and render d-attach component."""
        afs = _get_agent_file_system(context)

        preview_url = None
        dattach_md = ""

        if afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                file_key = file_name.rsplit(".", 1)[0]
                extension = file_name.rsplit(".", 1)[1] if "." in file_name else result.format

                file_metadata = await afs.save_binary_file(
                    file_key=file_key,
                    data=result.data,
                    file_type=FileType.DELIVERABLE,
                    extension=extension,
                    file_name=file_name,
                    tool_name="generate_image",
                    is_deliverable=True,
                    description=description,
                    metadata={
                        "file_category": "deliverable",
                        "mime_type": result.mime_type,
                        "prompt": prompt[:200],
                        **(result.metadata or {}),
                    },
                )

                if file_metadata:
                    preview_url = file_metadata.preview_url

                    # Render d-attach component
                    try:
                        from derisk.agent.core.file_system.dattach_utils import render_dattach

                        dattach_md = render_dattach(
                            file_name=file_name,
                            file_url=preview_url or "",
                            file_type="deliverable",
                            object_path=file_metadata.metadata.get("object_path") if file_metadata.metadata else None,
                            preview_url=preview_url,
                            download_url=file_metadata.download_url or preview_url,
                            description=description,
                            mime_type=result.mime_type,
                        )
                    except Exception as e:
                        logger.warning(f"[generate_image] d-attach render failed: {e}")

            except Exception as e:
                logger.warning(f"[generate_image] AFS save failed: {e}", exc_info=True)

        # Build output
        parts = [
            f"✅ 图片生成成功: {file_name}",
            f"📋 描述: {description}",
            f"🎨 模型: {result.metadata.get('model', 'unknown')}",
        ]

        if result.metadata.get("revised_prompt"):
            parts.append(f"📝 优化后的提示词: {result.metadata['revised_prompt']}")

        if preview_url:
            parts.append(f"\n![{description}]({preview_url})")

        if dattach_md:
            parts.append(f"\n\n**交付文件:**\n{dattach_md}")
        elif preview_url:
            parts.append(f"\n**下载链接:** {preview_url}")

        artifact = Artifact(
            name=file_name,
            type="image",
            url=preview_url,
            mime_type=result.mime_type,
            size=len(result.data),
            metadata=result.metadata,
        )

        return ToolResult.ok(
            output="\n".join(parts),
            tool_name=self.name,
            artifacts=[artifact],
        )


class GenerateVideoTool(ToolBase):
    """AI 视频生成工具"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_video",
            display_name="Generate Video",
            description=_GENERATE_VIDEO_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=True,
            timeout=600,
            tags=["video", "generation", "ai", "media", "sora"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "视频描述 (英文效果更佳)",
                },
                "provider": {
                    "type": "string",
                    "description": "生成服务提供商",
                    "default": "openai_video",
                },
                "model": {
                    "type": "string",
                    "description": "模型名称 (sora 等)",
                    "default": "sora",
                },
                "duration": {
                    "type": "integer",
                    "description": "视频时长 (秒)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 60,
                },
                "resolution": {
                    "type": "string",
                    "enum": ["720p", "1080p"],
                    "description": "视频分辨率",
                    "default": "1080p",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["16:9", "9:16", "1:1"],
                    "description": "视频宽高比",
                    "default": "16:9",
                },
                "description": {
                    "type": "string",
                    "description": "交付文件描述 (可选)",
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        prompt = args.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail(error="prompt 不能为空", tool_name=self.name)

        provider_name = args.get("provider", "openai_video")
        model = args.get("model", "sora")
        description = args.get("description", "").strip() or f"AI 生成视频: {prompt[:50]}"

        from derisk.agent.util.media_gen.provider_registry import MediaGenProviderRegistry

        api_key = _resolve_api_key(provider_name, context)
        if not api_key:
            return ToolResult.fail(
                error=f"未找到 {provider_name} 的 API Key。请设置环境变量或在配置中提供。",
                tool_name=self.name,
            )

        provider = MediaGenProviderRegistry.create_provider(
            name=provider_name, api_key=api_key
        )
        if not provider:
            available = list(MediaGenProviderRegistry.list_providers().keys())
            return ToolResult.fail(
                error=f"未找到生成服务 '{provider_name}'。可用服务: {available}",
                tool_name=self.name,
            )

        # Generate video
        try:
            gen_kwargs = {
                k: v
                for k, v in args.items()
                if k in ("duration", "resolution", "aspect_ratio") and v
            }
            result = await provider.generate_video(prompt, model, **gen_kwargs)
        except NotImplementedError:
            return ToolResult.fail(
                error=f"服务 '{provider_name}' 不支持视频生成",
                tool_name=self.name,
            )
        except TimeoutError as e:
            return ToolResult.fail(
                error=f"视频生成超时: {e}",
                tool_name=self.name,
            )
        except Exception as e:
            logger.error(f"[generate_video] Generation failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"视频生成失败: {e}",
                tool_name=self.name,
            )

        # Save and deliver
        file_name = f"generated_video_{uuid.uuid4().hex[:8]}.{result.format}"
        return await self._save_and_deliver(
            result, file_name, description, context, prompt
        )

    async def _save_and_deliver(
        self,
        result: Any,
        file_name: str,
        description: str,
        context: Optional[ToolContext],
        prompt: str,
    ) -> ToolResult:
        """Save generated video to storage and render d-attach component."""
        afs = _get_agent_file_system(context)

        preview_url = None
        dattach_md = ""

        if afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                file_key = file_name.rsplit(".", 1)[0]
                extension = file_name.rsplit(".", 1)[1] if "." in file_name else result.format

                file_metadata = await afs.save_binary_file(
                    file_key=file_key,
                    data=result.data,
                    file_type=FileType.DELIVERABLE,
                    extension=extension,
                    file_name=file_name,
                    tool_name="generate_video",
                    is_deliverable=True,
                    description=description,
                    metadata={
                        "file_category": "deliverable",
                        "mime_type": result.mime_type,
                        "prompt": prompt[:200],
                        **(result.metadata or {}),
                    },
                )

                if file_metadata:
                    preview_url = file_metadata.preview_url

                    try:
                        from derisk.agent.core.file_system.dattach_utils import render_dattach

                        dattach_md = render_dattach(
                            file_name=file_name,
                            file_url=preview_url or "",
                            file_type="deliverable",
                            object_path=file_metadata.metadata.get("object_path") if file_metadata.metadata else None,
                            preview_url=preview_url,
                            download_url=file_metadata.download_url or preview_url,
                            description=description,
                            mime_type=result.mime_type,
                        )
                    except Exception as e:
                        logger.warning(f"[generate_video] d-attach render failed: {e}")

            except Exception as e:
                logger.warning(f"[generate_video] AFS save failed: {e}", exc_info=True)

        # Build output
        parts = [
            f"✅ 视频生成成功: {file_name}",
            f"📋 描述: {description}",
            f"🎬 模型: {result.metadata.get('model', 'unknown')}",
        ]

        if result.duration_seconds:
            parts.append(f"⏱️ 时长: {result.duration_seconds}s")

        if preview_url:
            parts.append(f"\n[视频: {description}]({preview_url})")

        if dattach_md:
            parts.append(f"\n\n**交付文件:**\n{dattach_md}")
        elif preview_url:
            parts.append(f"\n**下载链接:** {preview_url}")

        artifact = Artifact(
            name=file_name,
            type="file",
            url=preview_url,
            mime_type=result.mime_type,
            size=len(result.data),
            metadata=result.metadata,
        )

        return ToolResult.ok(
            output="\n".join(parts),
            tool_name=self.name,
            artifacts=[artifact],
        )
