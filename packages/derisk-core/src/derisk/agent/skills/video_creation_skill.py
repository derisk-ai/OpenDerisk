"""Video Creation Skill - 多模态视频创作技能定义.

该技能引导主 Agent 完成复杂的多模态视频创作工作流程。

使用方式:
- 主 Agent (ReactMasterAgent) 绑定此 Skill
- Skill 提供工作流程指导和约束
- Agent 使用 Todo 工具管理任务
- Agent 通过 spawn_agent_task 委派专业 Agent 执行具体生成任务
"""

from typing import Dict, Any, Optional, List
from derisk.agent.skills.skill_base import SkillBase, SkillMetadata, SkillContext, SkillResult
import logging

logger = logging.getLogger(__name__)


VIDEO_CREATION_SKILL_CONTENT = """# Video Creation Skill - 多模态视频创作

## 技能概述

本技能引导你完成从文本描述到高质量视频的完整创作流程。你将使用专业 Agent 和 AI 模型生成首帧图片、创建视频片段并合成最终视频。

## 工作流程阶段

### Phase 1: 需求分析

**目标**: 理解用户需求，拆解场景

**步骤**:
1. 分析用户的视频创作需求
2. 提取关键场景要素:
   - 场景描述 (环境、主体、风格)
   - 视觉风格 (色调、光线、构图)
   - 运动要求 (镜头运动、内容运动)
3. 将复杂需求拆解为多个场景片段
4. 使用 `todowrite` 工具创建任务清单

**输出**: 场景列表，每个场景包含:
```json
{
  "scene_id": "scene_1",
  "description": "无人机俯瞰城市夜景",
  "visual_style": "冷色调、霓虹灯光、科技感",
  "motion": "缓慢推镜头，城市建筑逐渐展现",
  "duration": 5
}
```

### Phase 2: 首帧图片生成

**目标**: 为每个场景生成高质量首帧图片

**步骤**:
1. 针对每个场景，构建图片生成提示词:
   - 场景描述 + 视觉风格 + 构图要求
   - 使用英文提示词 (Wan 模型要求)
   - 启用 thinking_mode 提升复杂场景质量
2. 使用 `spawn_agent_task` 委派 `frame-gen-agent` 执行图片生成:
   ```python
   spawn_agent_task(
       agent_name="frame-gen-agent",
       task_input={
           "prompt": "Drone aerial view of modern cityscape at night...",
           "model": "wan2.7-image-pro",
           "size": "1920x1080",
           "thinking_mode": True
       }
   )
   ```
3. 使用 `check_tasks` 监控生成进度
4. 使用 `wait_tasks` 等待所有图片生成完成
5. 收集生成的图片 URL

**Wan 图片生成参数**:
- `prompt`: 英文描述，包含场景、风格、构图
- `model`: wan2.7-image-pro (推荐) 或 wan2.7-image
- `size`: 1920x1080 (视频尺寸)
- `thinking_mode`: True (复杂场景)
- `bbox_list`: 构图区域控制 (可选)
- `color_palette`: 色调控制 (可选)

**输出**: 首帧图片 URL 列表

### Phase 3: 图片质量分析 (可选)

**目标**: 评估首帧图片质量，优化不足之处

**步骤**:
1. 使用 `analyze_image` 工具分析图片质量:
   - composition: 构图质量
   - lighting: 光线效果
   - color: 色调一致性
   - video_suitability: 视频适配性
2. 检查评分是否达标 (>= 7分)
3. 低评分图片重新生成:
   - 根据分析建议优化提示词
   - 调整参数重新生成

**使用示例**:
```python
analyze_image(
    image_url="https://...",
    analysis_type="video_suitability",
    context="原始提示词：..."
)
```

### Phase 4: 视频片段生成

**目标**: 基于首帧图片生成视频片段

**步骤**:
1. 为每个场景构建运动描述:
   - 镜头运动: push_in, pull_out, pan_left, pan_right
   - 内容运动: 风吹、水流、灯光变化
   - 运动幅度: gentle, moderate, dynamic
2. 使用 `spawn_agent_task` 委派 `video-gen-agent` 执行视频生成:
   ```python
   spawn_agent_task(
       agent_name="video-gen-agent",
       task_input={
           "first_frame_image_url": "https://...",
           "prompt": "Slow push in, city buildings gradually revealed...",
           "model": "doubao-seedance-1-5-pro-251215",
           "duration": 5,
           "camerafixed": False
       }
   )
   ```
3. 使用 `check_tasks` 和 `wait_tasks` 管理并发生成
4. 收集生成的视频 URL

**Seedance 视频生成参数**:
- `first_frame_image_url`: 首帧图片 URL (必须)
- `prompt`: 运动描述 (英文)
- `model`: doubao-seedance-1-5-pro-251215
- `duration`: 视频时长 (3-10秒)
- `camerafixed`: True=固定镜头，False=镜头可运动
- `watermark`: 是否添加水印

**输出**: 视频片段 URL 列表

### Phase 5: 视频合成

**目标**: 将多个视频片段合成为最终视频

**步骤**:
1. 确定视频片段顺序 (按场景 ID)
2. 选择转场效果:
   - none: 直接拼接
   - crossfade: 交叉淡入淡出 (推荐)
   - fade: 黑场过渡
3. 使用 `composite_video` 工具合成:
   ```python
   composite_video(
       video_urls=["https://v1.mp4", "https://v2.mp4", ...],
       transition="crossfade",
       transition_duration=0.5,
       output_resolution="1080p",
       output_fps=30
   )
   ```
4. 获取最终视频 URL

**输出**: 最终视频 URL

### Phase 6: 结果交付

**目标**: 向用户交付最终成果

**步骤**:
1. 整合所有生成的素材:
   - 首帧图片 (每个场景)
   - 视频片段 (每个场景)
   - 最终合成视频
2. 生成交付报告
3. 使用 `todoread` 标记所有任务完成

## 工具使用指南

### 任务管理工具

```python
# 创建任务清单
todowrite([
    {"id": "1", "task": "分析需求拆解场景", "status": "pending"},
    {"id": "2", "task": "生成首帧图片", "status": "pending"},
    {"id": "3", "task": "生成视频片段", "status": "pending"},
    {"id": "4", "task": "合成最终视频", "status": "pending"},
])

# 更新任务状态
todowrite([{"id": "1", "status": "completed"}, ...])

# 查看任务进度
todoread()
```

### 异步任务工具

```python
# 委派专业 Agent
task_id = spawn_agent_task(
    agent_name="frame-gen-agent",
    task_input={"prompt": "...", "model": "wan2.7-image-pro"}
)

# 并发委派多个任务
task_ids = []
for scene in scenes:
    tid = spawn_agent_task(
        agent_name="video-gen-agent",
        task_input={"first_frame_image_url": scene.image_url, "prompt": scene.motion}
    )
    task_ids.append(tid)

# 监控进度
status = check_tasks(task_ids)

# 等待完成
results = wait_tasks(task_ids, timeout=300)
```

### 图片生成工具

```python
generate_image(
    prompt="Drone aerial view of neon-lit cityscape...",
    model="wan2.7-image-pro",
    size="1920x1080",
    thinking_mode=True,
    color_palette=["#00FFFF", "#FF00FF", "#000033"]
)
```

### 视频生成工具

```python
generate_video(
    prompt="Slow push in, buildings revealed...",
    model="doubao-seedance-1-5-pro-251215",
    first_frame_image_url="https://...",
    duration=5,
    camerafixed=False
)
```

### 图片分析工具

```python
analyze_image(
    image_url="https://...",
    analysis_type="full",  # composition, lighting, color, video_suitability, full
    context="原始提示词..."
)
```

### 视频合成工具

```python
composite_video(
    video_urls=["https://v1.mp4", "https://v2.mp4"],
    transition="crossfade",
    transition_duration=0.5,
    output_resolution="1080p",
    output_fps=30
)
```

## 专业 Agent 资源

你拥有以下专业 Agent 可委派:

| Agent | 专长 | 工具 |
|-------|------|------|
| `frame-gen-agent` | 首帧图片生成 | generate_image |
| `video-gen-agent` | 视频片段生成 | generate_video |

**委派原则**:
- 每个专业 Agent 每次执行单次生成任务
- 批量生成通过并发委派多个 Agent 任务
- 使用 `spawn_agent_task` 委派，`wait_tasks` 等待结果

## 提示词优化技巧

### 图片提示词

1. **结构**: 主体 + 环境 + 风格 + 构图 + 光线
   - "主体: [描述主体]"
   - "环境: [描述背景]"
   - "风格: [视觉风格]"
   - "构图: [镜头角度、位置]"
   - "光线: [光源、阴影]"

2. **示例**:
   ```
   Drone aerial view of modern cityscape at night,
   neon lights reflecting on glass buildings,
   cyberpunk aesthetic,
   cold blue and purple tones,
   cinematic lighting with soft shadows,
   wide angle shot, 4K quality
   ```

3. **高级参数**:
   - `bbox_list`: 精确控制主体位置
   - `color_palette`: 保持色调一致性
   - `thinking_mode`: 复杂场景启用

### 视频运动描述

1. **镜头运动**:
   - push_in: 推镜头 (放大)
   - pull_out: 拉镜头 (缩小)
   - pan_left/right: 水平摇镜
   - tilt_up/down: 垂直摇镜

2. **内容运动**:
   - 风吹效果: "gentle wind blowing"
   - 水流效果: "water flowing smoothly"
   - 灯光变化: "lights flickering"
   - 人物动作: "person walking"

3. **示例**:
   ```
   Slow push in from aerial view,
   city buildings gradually revealed,
   neon lights flickering gently,
   camera moves forward at steady pace
   ```

## 错误处理

1. **图片生成失败**: 检查提示词、调整参数、切换模型
2. **视频生成超时**: 增加等待时间、检查首帧图片 URL
3. **合成失败**: 检查视频格式、调整转场参数

## 质量标准

- 首帧图片评分 >= 7分
- 视频时长 3-10 秒
- 转场流畅无跳跃
- 最终视频分辨率 >= 1080p

## 注意事项

1. Wan 图片生成提示词必须为英文
2. Seedance 视频生成必须提供首帧图片 URL
3. 并发任务数量建议控制在 5 个以内
4. 视频生成是异步任务，需要轮询等待
"""

# 注册 Skill 到系统
class VideoCreationSkill(SkillBase):
    """多模态视频创作技能"""

    def _define_metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="video_creation",
            version="1.0.0",
            description="多模态视频创作工作流程技能，引导从文本到视频的完整创作流程",
            author="OpenDeRisk",
            tags=["video", "multimodal", "generation", "creative"],
            requires=[
                "todowrite",
                "todoread",
                "spawn_agent_task",
                "check_tasks",
                "wait_tasks",
                "generate_image",
                "generate_video",
                "analyze_image",
                "composite_video",
            ],
            enabled=True,
        )

    async def execute(
        self,
        context: SkillContext,
        user_request: str,
        **kwargs
    ) -> SkillResult:
        """
        执行视频创作技能

        注意: 此 Skill 主要提供指导，实际执行由 Agent 完成

        Args:
            context: 技能执行上下文
            user_request: 用户视频创作请求
            **kwargs: 其他参数

        Returns:
            SkillResult: 包含工作流程指导
        """
        # Skill 主要提供指导，返回工作流程框架
        return SkillResult(
            success=True,
            data={
                "skill_content": VIDEO_CREATION_SKILL_CONTENT,
                "workflow_phases": [
                    "Phase 1: 需求分析",
                    "Phase 2: 首帧图片生成",
                    "Phase 3: 图片质量分析 (可选)",
                    "Phase 4: 视频片段生成",
                    "Phase 5: 视频合成",
                    "Phase 6: 结果交付",
                ],
                "available_agents": ["frame-gen-agent", "video-gen-agent"],
            },
            message="视频创作技能已激活，请按照工作流程指导执行",
            metadata={
                "user_request": user_request,
                "agent_name": context.agent_name,
            },
        )


__all__ = ["VideoCreationSkill", "VIDEO_CREATION_SKILL_CONTENT"]