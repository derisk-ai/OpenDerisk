"""Composite Video Tool.

Uses FFmpeg to composite multiple video segments into a final video.
"""

import asyncio
import logging
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from derisk.agent.tools.base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import Artifact, ToolResult

logger = logging.getLogger(__name__)

_COMPOSITE_VIDEO_PROMPT = """将多个视频片段合成为最终视频。

**使用场景：**
- 将多段视频拼接成一个完整视频
- 添加转场效果
- 控制输出分辨率和帧率

**推荐用法：**
```
# 基础合成 (无转场)
composite_video(
    video_urls=["https://video1.mp4", "https://video2.mp4", "https://video3.mp4"]
)

# 带转场效果
composite_video(
    video_urls=["https://video1.mp4", "https://video2.mp4"],
    transition="crossfade",
    transition_duration=0.5
)

# 高清输出
composite_video(
    video_urls=["..."],
    output_resolution="1080p",
    output_fps=30
)
```

**转场效果类型：**
- none: 无转场，直接拼接
- fade: 黑场过渡
- crossfade: 交叉淡入淡出 (推荐)
- wipe: 滑动过渡

**注意事项：**
- 视频片段需要先下载到本地
- 输出视频格式为 MP4
- 合成时间取决于视频数量和长度
"""


def _get_agent_file_system(context: Optional[ToolContext]) -> Any:
    """Get AgentFileSystem from tool context."""
    if context is None:
        return None

    if isinstance(context, dict):
        afs = context.get("agent_file_system")
        if afs:
            return afs
        config = context.get("config", {})
        afs = config.get("agent_file_system")
        if afs:
            return afs
        return None

    afs = context.config.get("agent_file_system")
    if afs:
        return afs
    afs = context.get_resource("agent_file_system")
    if afs:
        return afs
    return None


class CompositeVideoTool(ToolBase):
    """视频合成工具 - 使用 FFmpeg 合成多个视频片段"""

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="composite_video",
            display_name="Composite Video",
            description=_COMPOSITE_VIDEO_PROMPT,
            category=ToolCategory.MEDIA_GEN,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=120,
            tags=["video", "composite", "ffmpeg", "edit"],
            author="openderisk",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "video_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "视频片段 URL 列表 (按顺序排列)",
                    "minItems": 1,
                },
                "transition": {
                    "type": "string",
                    "enum": ["none", "fade", "crossfade", "wipe"],
                    "description": "转场效果类型",
                    "default": "none",
                },
                "transition_duration": {
                    "type": "number",
                    "description": "转场时长 (秒)",
                    "default": 0.5,
                    "minimum": 0.1,
                    "maximum": 2.0,
                },
                "output_resolution": {
                    "type": "string",
                    "enum": ["720p", "1080p", "4K"],
                    "description": "输出分辨率",
                    "default": "1080p",
                },
                "output_fps": {
                    "type": "integer",
                    "description": "输出帧率",
                    "default": 30,
                    "minimum": 24,
                    "maximum": 60,
                },
                "description": {
                    "type": "string",
                    "description": "交付文件描述 (可选)",
                },
            },
            "required": ["video_urls"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        video_urls = args.get("video_urls", [])
        if not video_urls:
            return ToolResult.fail(error="video_urls 不能为空", tool_name=self.name)

        transition = args.get("transition", "none")
        transition_duration = args.get("transition_duration", 0.5)
        output_resolution = args.get("output_resolution", "1080p")
        output_fps = args.get("output_fps", 30)
        description = args.get("description", "").strip() or f"合成视频: {len(video_urls)} 个片段"

        try:
            # Download videos
            logger.info(f"[composite_video] Downloading {len(video_urls)} videos...")
            video_paths = await self._download_videos(video_urls)

            # Composite using FFmpeg
            logger.info(f"[composite_video] Compositing with transition={transition}...")
            composite_result = await self._composite_with_ffmpeg(
                video_paths=video_paths,
                transition=transition,
                transition_duration=transition_duration,
                output_resolution=output_resolution,
                output_fps=output_fps,
            )

            # Calculate total duration
            total_duration = composite_result.get("duration", 0)

            # Save to AgentFileSystem
            file_name = f"composite_video_{uuid.uuid4().hex[:8]}.mp4"
            preview_url = None
            dattach_md = ""

            afs = _get_agent_file_system(context)
            if afs and composite_result.get("data"):
                try:
                    from derisk.agent.core.memory.gpts.file_base import FileType

                    file_key = file_name.rsplit(".", 1)[0]
                    file_metadata = await afs.save_binary_file(
                        file_key=file_key,
                        data=composite_result["data"],
                        file_type=FileType.DELIVERABLE,
                        extension="mp4",
                        file_name=file_name,
                        tool_name="composite_video",
                        is_deliverable=True,
                        description=description,
                        metadata={
                            "file_category": "deliverable",
                            "mime_type": "video/mp4",
                            "segment_count": len(video_urls),
                            "transition": transition,
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
                                mime_type="video/mp4",
                            )
                        except Exception as e:
                            logger.warning(f"[composite_video] d-attach render failed: {e}")

                except Exception as e:
                    logger.warning(f"[composite_video] AFS save failed: {e}", exc_info=True)

            # Build output
            parts = [
                f"✅ 视频合成成功: {file_name}",
                f"📋 描述: {description}",
                f"🎬 片段数: {len(video_urls)}",
                f"⏱️ 总时长: {total_duration}s",
                f"📺 分辨率: {output_resolution}",
                f"🎞️ 转场: {transition}",
            ]

            if preview_url:
                parts.append(f"\n[视频: {description}]({preview_url})")

            if dattach_md:
                parts.append(f"\n\n**交付文件:**\n{dattach_md}")
            elif preview_url:
                parts.append(f"\n**下载链接:** {preview_url}")

            artifact = Artifact(
                name=file_name,
                type="video",
                url=preview_url,
                mime_type="video/mp4",
                metadata={
                    "segment_count": len(video_urls),
                    "transition": transition,
                    "duration": total_duration,
                },
            )

            return ToolResult.ok(
                output="\n".join(parts),
                tool_name=self.name,
                artifacts=[artifact],
            )

        except Exception as e:
            logger.error(f"[composite_video] Composite failed: {e}", exc_info=True)
            return ToolResult.fail(
                error=f"视频合成失败: {e}",
                tool_name=self.name,
            )

    async def _download_videos(self, video_urls: List[str]) -> List[str]:
        """Download videos to temporary files."""
        import httpx

        client = httpx.AsyncClient(timeout=60)
        video_paths = []

        try:
            for i, url in enumerate(video_urls):
                logger.debug(f"[composite_video] Downloading video {i+1}/{len(video_urls)}")
                response = await client.get(url)
                response.raise_for_status()

                # Save to temp file
                temp_path = tempfile.mktemp(suffix=".mp4", prefix=f"video_{i}_")
                with open(temp_path, "wb") as f:
                    f.write(response.content)
                video_paths.append(temp_path)

        finally:
            await client.aclose()

        return video_paths

    async def _composite_with_ffmpeg(
        self,
        video_paths: List[str],
        transition: str,
        transition_duration: float,
        output_resolution: str,
        output_fps: int,
    ) -> Dict[str, Any]:
        """Composite videos using FFmpeg."""
        # Map resolution to FFmpeg scale
        resolution_map = {
            "720p": "1280:720",
            "1080p": "1920:1080",
            "4K": "3840:2160",
        }
        scale = resolution_map.get(output_resolution, "1920:1080")

        output_path = tempfile.mktemp(suffix=".mp4", prefix="composite_")

        if transition == "none" or len(video_paths) == 1:
            # Simple concat without transition
            concat_file = tempfile.mktemp(suffix=".txt", prefix="concat_")
            with open(concat_file, "w") as f:
                for path in video_paths:
                    f.write(f"file '{path}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-vf", f"scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2",
                "-r", str(output_fps),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                output_path,
            ]

        elif transition == "crossfade":
            # Crossfade transition using xfade filter
            # Build complex filter chain
            inputs = []
            for i, path in enumerate(video_paths):
                inputs.extend(["-i", path])

            # Build xfade chain
            filter_parts = []
            current_input = "[0:v]"

            for i in range(1, len(video_paths)):
                offset = transition_duration * i
                next_input = f"[{i}:v]"
                output_label = f"[v{i}]"

                filter_parts.append(
                    f"{current_input}{next_input}xfade=transition=fade:duration={transition_duration}:offset={offset}{output_label}"
                )
                current_input = output_label

            # Add scale filter
            filter_parts.append(f"{current_input}scale={scale}:force_original_aspect_ratio=decrease")

            filter_complex = ";".join(filter_parts)

            cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-r", str(output_fps),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-an",  # No audio for simplicity with transitions
                output_path,
            ]

        else:
            # Fallback to simple concat with fade
            concat_file = tempfile.mktemp(suffix=".txt", prefix="concat_")
            with open(concat_file, "w") as f:
                for path in video_paths:
                    f.write(f"file '{path}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-vf", f"scale={scale}:force_original_aspect_ratio=decrease",
                "-r", str(output_fps),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                output_path,
            ]

        # Execute FFmpeg
        logger.debug(f"[composite_video] Running FFmpeg: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise RuntimeError(f"FFmpeg failed: {error_msg}")

        # Read output video
        with open(output_path, "rb") as f:
            video_data = f.read()

        # Get duration using ffprobe
        duration = await self._get_video_duration(output_path)

        # Cleanup temp files
        for path in video_paths:
            try:
                os.remove(path)
            except:
                pass
        try:
            os.remove(output_path)
        except:
                pass

        return {
            "data": video_data,
            "duration": duration,
        }

    async def _get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            try:
                return float(stdout.decode().strip())
            except:
                return 0.0

        return 0.0


__all__ = ["CompositeVideoTool"]