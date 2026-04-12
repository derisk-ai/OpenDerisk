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
- 根据文字描述生成图片 (如 DALL-E 3, 万相 wan2.7, Stable Diffusion, Flux)
- 生成数据可视化、插图、概念图等
- 图像编辑 (图生图、多图参考)
- 组图生成 (多张一致性图片)
- 生成的图片会自动保存并交付给用户

**推荐用法：**
```
# 文生图 (DALL-E)
generate_image(prompt="一只在星空下弹吉他的猫，赛博朋克风格", model="dall-e-3", size="1024x1024")

# 文生图 (万相 - 推荐，支持中文)
generate_image(prompt="无人机俯瞰城市夜景，霓虹灯光闪烁", provider="aliyun_wan", model="wan2.7-image-pro", size="2K", thinking_mode=true)

# 高质量文生图 (万相4K)
generate_image(prompt="精致的产品设计图", provider="aliyun_wan", model="wan2.7-image-pro", size="4K", thinking_mode=true)

# 组图生成 (多张一致性图片)
generate_image(prompt="四季变化，同一只猫在不同季节", provider="aliyun_wan", enable_sequential=true, n=4)

# 图像编辑 (多图参考)
generate_image(prompt="把图2的风格应用到图1", provider="aliyun_wan", images=["url1", "url2"])
```

**万相 (wan2.7) 特殊参数：**
- thinking_mode: 开启思考模式提升质量
- size: 1K/2K/4K (wan2.7-image-pro 文生图支持4K)
- images: 参考图片URL列表 (用于图生图/编辑)
- enable_sequential: 组图模式
- bbox_list: 框选区域 (交互式编辑)
- color_palette: 自定义颜色主题

**注意事项：**
- 生成图片需要消耗 API 配额，请合理使用
- 图片生成通常需要 10-30 秒
- 万相支持中文提示词，效果更佳
- 生成的图片会自动上传到存储并生成交付链接
"""

_GENERATE_VIDEO_PROMPT = """使用 AI 模型生成视频。

**使用场景：**
- 根据文字描述生成短视频 (如 Sora, doubao-seedance)
- 基于首帧图片生成视频 (图生视频)
- 生成产品演示、概念视频等
- 生成的视频会自动保存并交付给用户

**推荐用法：**
```
# 纯文生视频
generate_video(prompt="日落时分海浪拍打沙滩的慢镜头", model="sora", duration=5)

# 基于首帧图片生成视频 (火山引擎 Seedance - 推荐)
generate_video(
    prompt="无人机缓缓下降穿越城市建筑",
    provider="volcengine",
    model="doubao-seedance-1-5-pro-251215",
    first_frame_image_url="https://...",
    duration=5
)

# 长视频生成
generate_video(prompt="城市夜景航拍", provider="volcengine", duration=10)
```

**Seedance 特殊参数：**
- first_frame_image_url: 首帧图片URL (图生视频)
- duration: 视频时长 (秒)
- camerafixed: 是否固定镜头
- watermark: 是否添加水印

**注意事项：**
- 视频生成需要较长时间 (通常 1-5 分钟)
- 视频生成消耗较多 API 配额
- 首帧图片质量直接影响视频效果
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
                    "description": "图片描述 (支持中文和英文，万相推荐中文)",
                },
                "provider": {
                    "type": "string",
                    "description": "生成服务提供商",
                    "enum": ["openai", "aliyun_wan"],
                    "default": "aliyun_wan",
                },
                "model": {
                    "type": "string",
                    "description": "模型名称 (dall-e-3, wan2.7-image-pro, wan2.7-image 等)",
                    "default": "wan2.7-image-pro",
                },
                "size": {
                    "type": "string",
                    "description": "图片尺寸或分辨率规格。OpenAI: 1024x1024 等。万相: 1K/2K/4K",
                    "default": "2K",
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "hd"],
                    "description": "图片质量 (OpenAI dall-e-3 支持 hd)",
                    "default": "standard",
                },
                "style": {
                    "type": "string",
                    "enum": ["vivid", "natural"],
                    "description": "图片风格 (OpenAI dall-e-3 支持)",
                    "default": "vivid",
                },
                # 万相特殊参数
                "images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参考图片 URL 列表 (万相图生图/图像编辑场景)",
                },
                "bbox_list": {
                    "type": "array",
                    "description": "框选区域列表 (万相交互式编辑)",
                },
                "enable_sequential": {
                    "type": "boolean",
                    "description": "启用组图模式 (万相组图生成)",
                    "default": False,
                },
                "n": {
                    "type": "integer",
                    "description": "生成数量。普通模式1-4，组图模式1-12",
                    "default": 1,
                },
                "thinking_mode": {
                    "type": "boolean",
                    "description": "开启思考模式 (万相提升质量)",
                    "default": True,
                },
                "watermark": {
                    "type": "boolean",
                    "description": "是否添加水印",
                    "default": False,
                },
                "color_palette": {
                    "type": "array",
                    "description": "自定义颜色主题 (万相)",
                },
                "seed": {
                    "type": "integer",
                    "description": "随机种子 (可复现)",
                },
                "async_mode": {
                    "type": "boolean",
                    "description": "异步生成模式 (长耗时任务)",
                    "default": False,
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

        provider_name = args.get("provider", "aliyun_wan")
        model = args.get("model", "wan2.7-image-pro" if provider_name == "aliyun_wan" else "dall-e-3")
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
            # Build kwargs for all supported parameters
            gen_kwargs = {}
            for k in [
                "size", "quality", "style",  # OpenAI params
                "images", "bbox_list", "enable_sequential", "n",  # Wan params
                "thinking_mode", "watermark", "color_palette", "seed",  # Wan params
                "async_mode", "timeout",  # Async params
            ]:
                if k in args and args[k] is not None:
                    gen_kwargs[k] = args[k]

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
                    "description": "视频描述 (支持中文和英文)",
                },
                "provider": {
                    "type": "string",
                    "description": "生成服务提供商",
                    "enum": ["openai_video", "volcengine"],
                    "default": "volcengine",
                },
                "model": {
                    "type": "string",
                    "description": "模型名称 (sora, doubao-seedance-1-5-pro-251215 等)",
                    "default": "doubao-seedance-1-5-pro-251215",
                },
                "first_frame_image_url": {
                    "type": "string",
                    "description": "首帧图片 URL (火山引擎 Seedance 图生视频)",
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
                # 火山引擎 Seedance 特殊参数
                "camerafixed": {
                    "type": "boolean",
                    "description": "是否固定镜头 (火山引擎)",
                    "default": False,
                },
                "watermark": {
                    "type": "boolean",
                    "description": "是否添加水印",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "最大等待时间 (秒)",
                    "default": 300,
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

        provider_name = args.get("provider", "volcengine")
        model = args.get("model", "doubao-seedance-1-5-pro-251215" if provider_name == "volcengine" else "sora")
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
            # Build kwargs for all supported parameters
            gen_kwargs = {}
            for k in [
                "duration", "resolution", "aspect_ratio",  # Common params
                "first_frame_image_url", "camerafixed", "watermark",  # Volcengine params
                "timeout",  # Timeout
            ]:
                if k in args and args[k] is not None:
                    gen_kwargs[k] = args[k]

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
