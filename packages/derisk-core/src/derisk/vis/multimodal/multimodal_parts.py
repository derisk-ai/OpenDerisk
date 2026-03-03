"""
多模态Part支持

支持音频、视频等富媒体Part类型
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from derisk._private.pydantic import Field
from derisk.vis.parts import PartType, PartStatus, VisPart

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 音频Part
# ═══════════════════════════════════════════════════════════════

class AudioPart(VisPart):
    """
    音频Part - 支持音频播放和转写
    
    示例:
        # 从URL创建
        part = AudioPart.from_url(
            url="https://example.com/audio.mp3",
            transcript="这是一段音频转写文本"
        )
        
        # 从本地文件创建
        part = AudioPart.from_file(
            path="/path/to/audio.wav",
            transcript="本地音频转写"
        )
    """
    
    type: PartType = Field(default=PartType.IMAGE, description="类型标记")  # 复用IMAGE类型或扩展新类型
    
    # 音频特有的字段
    audio_url: Optional[str] = Field(None, description="音频URL")
    audio_data: Optional[str] = Field(None, description="Base64编码的音频数据")
    audio_format: str = Field(default="mp3", description="音频格式: mp3, wav, ogg等")
    duration: Optional[float] = Field(None, description="音频时长(秒)")
    transcript: Optional[str] = Field(None, description="音频转写文本")
    transcript_language: Optional[str] = Field(None, description="转写语言")
    waveform_data: Optional[List[float]] = Field(None, description="波形数据(用于可视化)")
    
    @classmethod
    def from_url(
        cls,
        url: str,
        audio_format: str = "mp3",
        transcript: Optional[str] = None,
        duration: Optional[float] = None,
        **kwargs
    ) -> "AudioPart":
        """
        从URL创建音频Part
        
        Args:
            url: 音频URL
            audio_format: 音频格式
            transcript: 转写文本
            duration: 时长
            **kwargs: 额外参数
            
        Returns:
            AudioPart实例
        """
        return cls(
            audio_url=url,
            audio_format=audio_format,
            transcript=transcript,
            duration=duration,
            content=f"[Audio: {url}]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )
    
    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        transcript: Optional[str] = None,
        **kwargs
    ) -> "AudioPart":
        """
        从本地文件创建音频Part
        
        Args:
            path: 文件路径
            transcript: 转写文本
            **kwargs: 额外参数
            
        Returns:
            AudioPart实例
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {path}")
        
        # 读取文件并编码
        audio_data = base64.b64encode(path.read_bytes()).decode('utf-8')
        
        # 推断格式
        audio_format = path.suffix.lstrip('.')
        
        return cls(
            audio_data=audio_data,
            audio_format=audio_format,
            transcript=transcript,
            content=f"[Audio: {path.name}]",
            metadata={"filename": path.name, **kwargs},
            status=PartStatus.COMPLETED,
        )
    
    @classmethod
    def from_base64(
        cls,
        data: str,
        audio_format: str = "mp3",
        transcript: Optional[str] = None,
        **kwargs
    ) -> "AudioPart":
        """
        从Base64数据创建音频Part
        
        Args:
            data: Base64编码的音频数据
            audio_format: 音频格式
            transcript: 转写文本
            **kwargs: 额外参数
            
        Returns:
            AudioPart实例
        """
        return cls(
            audio_data=data,
            audio_format=audio_format,
            transcript=transcript,
            content="[Audio: base64 data]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )


# ═══════════════════════════════════════════════════════════════
# 视频Part
# ═══════════════════════════════════════════════════════════════

class VideoPart(VisPart):
    """
    视频Part - 支持视频播放和帧提取
    
    示例:
        # 从URL创建
        part = VideoPart.from_url(
            url="https://example.com/video.mp4",
            thumbnail="https://example.com/thumb.jpg",
            duration=120.5
        )
        
        # 带字幕
        part = VideoPart.from_url(
            url="...",
            subtitles=[{"start": 0, "end": 5, "text": "Hello"}]
        )
    """
    
    type: PartType = Field(default=PartType.IMAGE, description="类型标记")
    
    # 视频特有字段
    video_url: Optional[str] = Field(None, description="视频URL")
    video_data: Optional[str] = Field(None, description="Base64编码的视频数据")
    video_format: str = Field(default="mp4", description="视频格式: mp4, webm等")
    duration: Optional[float] = Field(None, description="视频时长(秒)")
    thumbnail: Optional[str] = Field(None, description="缩略图URL")
    width: Optional[int] = Field(None, description="视频宽度")
    height: Optional[int] = Field(None, description="视频高度")
    fps: Optional[float] = Field(None, description="帧率")
    subtitles: Optional[List[Dict[str, Any]]] = Field(None, description="字幕列表")
    frames: Optional[List[str]] = Field(None, description="关键帧(Base64)")
    
    @classmethod
    def from_url(
        cls,
        url: str,
        video_format: str = "mp4",
        thumbnail: Optional[str] = None,
        duration: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **kwargs
    ) -> "VideoPart":
        """从URL创建视频Part"""
        return cls(
            video_url=url,
            video_format=video_format,
            thumbnail=thumbnail,
            duration=duration,
            width=width,
            height=height,
            content=f"[Video: {url}]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )
    
    def add_subtitles(self, subtitles: List[Dict[str, Any]]) -> "VideoPart":
        """
        添加字幕
        
        Args:
            subtitles: 字幕列表 [{"start": 0.0, "end": 5.0, "text": "..."}, ...]
            
        Returns:
            新的VideoPart实例
        """
        return self.copy(update={"subtitles": subtitles})
    
    def add_frame(self, frame_data: str) -> "VideoPart":
        """
        添加关键帧
        
        Args:
            frame_data: Base64编码的帧图像
            
        Returns:
            新的VideoPart实例
        """
        frames = self.frames or []
        frames.append(frame_data)
        return self.copy(update={"frames": frames})


# ═══════════════════════════════════════════════════════════════
# 嵌入Part (iframe, 嵌入内容)
# ═══════════════════════════════════════════════════════════════

class EmbedPart(VisPart):
    """
    嵌入Part - 支持iframe嵌入和第三方内容
    
    示例:
        # 嵌入YouTube视频
        part = EmbedPart.youtube("dQw4w9WgXcQ")
        
        # 嵌入地图
        part = EmbedPart.google_maps(lat=37.7749, lng=-122.4194)
        
        # 自定义嵌入
        part = EmbedPart.custom(
            html='<iframe src="..."></iframe>',
            width=800,
            height=600
        )
    """
    
    type: PartType = Field(default=PartType.IMAGE, description="类型标记")
    
    # 嵌入特有字段
    embed_type: str = Field(default="iframe", description="嵌入类型: iframe, html, widget")
    embed_url: Optional[str] = Field(None, description="嵌入URL")
    embed_html: Optional[str] = Field(None, description="嵌入HTML")
    provider: Optional[str] = Field(None, description="提供者: youtube, vimeo, google_maps等")
    width: Optional[int] = Field(None, description="宽度")
    height: Optional[int] = Field(None, description="高度")
    allow_scripts: bool = Field(default=False, description="是否允许脚本")
    sandbox: Optional[str] = Field(None, description="沙箱设置")
    
    @classmethod
    def youtube(cls, video_id: str, **kwargs) -> "EmbedPart":
        """嵌入YouTube视频"""
        url = f"https://www.youtube.com/embed/{video_id}"
        return cls(
            embed_type="iframe",
            embed_url=url,
            provider="youtube",
            width=kwargs.get("width", 560),
            height=kwargs.get("height", 315),
            content=f"[YouTube: {video_id}]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )
    
    @classmethod
    def vimeo(cls, video_id: str, **kwargs) -> "EmbedPart":
        """嵌入Vimeo视频"""
        url = f"https://player.vimeo.com/video/{video_id}"
        return cls(
            embed_type="iframe",
            embed_url=url,
            provider="vimeo",
            width=kwargs.get("width", 640),
            height=kwargs.get("height", 360),
            content=f"[Vimeo: {video_id}]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )
    
    @classmethod
    def google_maps(
        cls,
        lat: float,
        lng: float,
        zoom: int = 15,
        **kwargs
    ) -> "EmbedPart":
        """嵌入Google地图"""
        url = f"https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d zoom!2d{lng}!3d{lat}"
        return cls(
            embed_type="iframe",
            embed_url=url,
            provider="google_maps",
            width=kwargs.get("width", 600),
            height=kwargs.get("height", 450),
            content=f"[Map: {lat}, {lng}]",
            metadata={"lat": lat, "lng": lng, "zoom": zoom, **kwargs},
            status=PartStatus.COMPLETED,
        )
    
    @classmethod
    def custom(
        cls,
        html: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **kwargs
    ) -> "EmbedPart":
        """自定义嵌入"""
        return cls(
            embed_type="html",
            embed_html=html,
            width=width,
            height=height,
            content="[Custom Embed]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )


# ═══════════════════════════════════════════════════════════════
# 3D模型Part
# ═══════════════════════════════════════════════════════════════

class Model3DPart(VisPart):
    """
    3D模型Part - 支持3D模型展示
    
    支持格式: GLTF, GLB, OBJ, STL等
    """
    
    type: PartType = Field(default=PartType.IMAGE, description="类型标记")
    
    model_url: Optional[str] = Field(None, description="模型URL")
    model_data: Optional[str] = Field(None, description="Base64编码的模型数据")
    model_format: str = Field(default="gltf", description="模型格式")
    poster: Optional[str] = Field(None, description="预览图")
    camera_position: Optional[Dict[str, float]] = Field(None, description="相机位置")
    auto_rotate: bool = Field(default=False, description="自动旋转")
    scale: float = Field(default=1.0, description="缩放比例")
    
    @classmethod
    def from_url(
        cls,
        url: str,
        model_format: str = "gltf",
        **kwargs
    ) -> "Model3DPart":
        """从URL创建3D模型Part"""
        return cls(
            model_url=url,
            model_format=model_format,
            content=f"[3D Model: {url}]",
            metadata=kwargs,
            status=PartStatus.COMPLETED,
        )


# ═══════════════════════════════════════════════════════════════
# 扩展Part类型枚举
# ═══════════════════════════════════════════════════════════════

class ExtendedPartType(str, PartType):
    """扩展的Part类型"""
    AUDIO = "audio"
    VIDEO = "video"
    EMBED = "embed"
    MODEL_3D = "model_3d"