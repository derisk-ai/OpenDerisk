# 多模态视频创作架构设计

## Skill + ReactMasterAgent + 专业子Agent协作方案

> **核心设计**: 直接使用现有 ReactMasterAgent 作为主调度 Agent，通过 VideoCreation Skill 约束工作流程，配合专业子 Agent 协作完成复杂多模态视频创作任务。

---

## 1. 核心架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        VideoCreationSkill (约束层)                               │
│  • 工作流程规范 (Phase 1-4 标准流程)                                              │
│  • 最佳实践 (提示词设计、参数选择、迭代策略)                                        │
│  • 质量检查点 (首帧审核、视频预览、最终验收)                                        │
│  • 子 Agent 使用指南 (何时 spawn、何时 review)                                    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ Skill 内容注入到 System Prompt
                                    │
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    ReactMasterAgent (现有主调度 Agent)                           │
│  ✅ 已具备核心能力:                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ • ReAct Loop (thinking + action)                                        │   │
│  │ • AsyncTaskManager + 4个 FunctionTool                                   │   │
│  │   - spawn_agent_task (启动后台子Agent)                                   │   │
│  │   - check_tasks (查看状态)                                               │   │
│  │   - wait_tasks (等待完成)                                                │   │
│  │   - cancel_task (取消任务)                                               │   │
│  │ • Todo 工具 (todowrite/todoread)                                        │   │
│  │ • Kanban 管理 (enable_kanban=True)                                      │   │
│  │ • Phase 管理 (enable_phase_management=True)                             │   │
│  │ • ReportGenerator (enable_auto_report)                                  │   │
│  │ • VIS 推送 (_system_event_manager)                                      │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  配置:                                                                          │
│  - agents: [AnalyzerAgent, FrameGenAgent, FrameReviewAgent,                   │
│             VideoGenAgent, CompositeAgent]                                     │
│  - tools: generate_image, generate_video, analyze_image, composite_video      │
│  - enable_kanban: True (可选，启用看板模式)                                     │
│  - enable_phase_management: True                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ spawn_agent_task (批量并发)
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         专门子 Agent (必须)                                      │
│                                                                                 │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐             │
│  │ FrameGenAgent               │  │ VideoGenAgent               │             │
│  │                             │  │                             │             │
│  │ • 执行图片生成任务           │  │ • 执行视频生成任务           │             │
│  │ • 每次生成一个图片           │  │ • 每次生成一个视频           │             │
│  │ • 批量由主Agent调度          │  │ • 批量由主Agent调度          │             │
│  │ • 使用 generate_image Tool  │  │ • 使用 generate_video Tool  │             │
│  └─────────────────────────────┘  └─────────────────────────────┘             │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ReactMasterAgent 直接处理                               │
│                                                                                 │
│  以下任务不需要专门子Agent，主Agent直接处理或调用Tool:                            │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                │
│  │ 需求分析        │  │ 图片质量分析    │  │ 视频合成        │                │
│  │                 │  │                 │  │                 │                │
│  │ thinking()中完成│  │ analyze_image   │  │ composite_video │                │
│  │ 输出场景分解    │  │ Tool            │  │ Tool            │                │
│  │ (纯LLM任务)     │  │ (多模态模型)    │  │ (FFmpeg操作)    │                │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                  │               │               │
                  ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Tool & Provider 层                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ generate    │  │ analyze     │  │ generate    │  │ composite   │           │
│  │ _image      │  │ _image      │  │ _video      │  │ _video      │           │
│  │ Tool        │  │ Tool        │  │ Tool        │  │ Tool        │           │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘           │
│  ┌───────────────────────────────────────────────────────────────────────┐    │
│  │                    Provider Registry                                   │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │    │
│  │  │ AliyunWan   │  │ Volcengine  │  │ OpenAI      │                    │    │
│  │  │ Provider    │  │ Provider    │  │ Provider    │                    │    │
│  │  │ (万相)      │  │ (Seedance)  │  │ (DALL-E)    │                    │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                    │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
                  │               │               │
                  ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        外部 API & 服务                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ 阿里云百炼  │  │ 火山引擎    │  │ OpenAI      │  │ 本地 FFmpeg │           │
│  │ (wan2.7)    │  │ (Seedance)  │  │ (DALL-E)    │  │ (视频合成)  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. VideoCreationSkill 设计

### 3.1 Skill 文件结构

```
.claude/skills/video-creation/
├── SKILL.md                    # Skill 主文件 (约束规范)
├── references/
│   ├── video-creation-spec.md  # 详细规格
│   ├── agents-guide.md         # 多 Agent 协作指南
│   └── tools-guide.md          # 工具使用指南
└── templates/
    ├── scene-analysis.md       # 场景分析模板
    ├── frame-prompt.md         # 首帧提示词模板
    └── video-prompt.md         # 视频提示词模板
```

### 3.2 SKILL.md 内容

```markdown
---
name: video-creation
description: 多模态视频创作 Skill - 基于 Skill 约束和多 Agent 协作的完整视频创作流程。支持需求分析、首帧生成、图片分析优化、视频生成、视频合成等全链路创作。
---

# VideoCreation Skill

多模态视频创作工作流 Skill，通过 Skill 约束和多 Agent 协作完成复杂视频创作任务。

## Trigger

Use this skill when user requests video creation tasks:
- 制作宣传片、广告视频、概念视频
- 需要多阶段创作的视频内容
- 需要迭代优化的视频项目
- 包含文本分析 + 图片生成 + 视频生成的复合任务

## 工作流程规范 (Phase Definition)

### Phase 1: 需求分析与场景分解

**目标**: 理解用户需求，输出结构化的创作方案和场景分解。

**执行方式**:
- 主 Agent 使用文本模型进行分析
- 或 spawn `analyzer_agent` 子 Agent 执行分析任务

**产出物**:
- 分析报告文本 (AnalysisArtifact)
- 场景分解列表 (每个场景包含: scene_id, description, duration, frame_prompt, video_prompt)

**质量检查点**:
- 场景数量是否合理 (3-8 个)
- 每个场景的 frame_prompt 是否详细具体
- video_prompt 是否包含镜头运动描述

### Phase 2: 首帧图片生成

**目标**: 为每个场景生成高质量首帧图片。

**执行方式**:
- 主 Agent 直接调用 `generate_image` Tool
- 或 spawn `frame_gen_agent` 子 Agent 执行批量生成

**推荐配置**:
```
provider: aliyun_wan
model: wan2.7-image-pro
size: 2K
thinking_mode: true
n: 1
```

**产出物**:
- 首帧图片 (ImageArtifact)
- 包含 scene_id、prompt、file_url

**质量检查点**:
- 图片风格是否一致
- 图片构图是否合理
- 是否适合作为视频首帧

### Phase 3: 首帧图片分析与优化 (可选)

**目标**: 使用图片理解模型分析首帧质量，提供优化建议。

**执行方式**:
- spawn `frame_review_agent` 子 Agent
- 使用支持图片输入的模型 (如 claude-sonnet-4-6) 分析图片

**分析维度**:
1. 构图质量 (composition quality)
2. 光线效果 (lighting quality)
3. 色调一致性 (color consistency)
4. 视频生成适配性 (video generation suitability)
5. 优化建议 (optimization suggestions)

**产出物**:
- 图片分析报告
- 优化后的提示词建议

### Phase 4: 视频片段生成

**目标**: 基于首帧图片生成视频片段。

**执行方式**:
- 主 Agent 调用 `generate_video` Tool
- 或 spawn `video_gen_agent` 子 Agent 执行批量生成

**推荐配置**:
```
provider: volcengine
model: doubao-seedance-1-5-pro-251215
first_frame_image_url: {frame.file_url}
duration: {scene.duration}
```

**产出物**:
- 视频片段 (VideoArtifact)
- 包含 scene_id、first_frame_source、duration

### Phase 5: 视频合成

**目标**: 将所有视频片段合成为最终视频。

**执行方式**:
- spawn `composite_agent` 子 Agent
- 使用 FFmpeg 或云端剪辑服务

**产出物**:
- 最终视频 (VideoArtifact)
- 包含 workflow_id、segment_count、total_duration

### Phase 6: 交付与报告

**目标**: 生成交付文档和最终报告。

**执行方式**:
- 主 Agent 或 spawn `report_gen_agent`

**产出物**:
- 交付文档 (包含视频链接、创作说明)
- 最终视频 Artifact

---

## 多 Agent 协作指南

### 主 Agent (VideoCreatorAgent)

**职责**:
- 整体调度和进度管理
- Todo 机制跟踪阶段目标
- 决策何时 spawn 子 Agent
- 处理异步任务通知
- 最终产物整合

**关键决策点**:

| 场景 | 决策 | 理由 |
|------|------|------|
| 场景数量 > 4 | spawn frame_gen_agent | 并发效率更高 |
| 需要首帧质量评估 | spawn frame_review_agent | 专业 Agent 深度分析 |
| 视频生成耗时 > 3分钟 | spawn video_gen_agent | 避免阻塞主 Agent |
| 需要迭代优化 | 重新生成特定场景 | Agent 自主决策 |

### 子 Agent 定义

| Agent | 用途 | 核心能力 | 推荐模型 |
|-------|------|----------|----------|
| analyzer_agent | 文本分析、场景分解 | LLM 分析、结构化输出 | claude-sonnet-4-6 |
| frame_gen_agent | 批量首帧生成 | 图片生成、并发执行 | - |
| frame_review_agent | 图片分析评估 | 图片理解、质量评估 | claude-sonnet-4-6 |
| video_gen_agent | 批量视频生成 | 视频生成、异步执行 | - |
| composite_agent | 视频合成 | FFmpeg 操作 | - |
| report_gen_agent | 报告生成 | 文档撰写 | claude-sonnet-4-6 |

---

## Todo 推进机制

主 Agent 使用 Todo 列表跟踪阶段目标:

```json
[
  {"id": "todo_1", "subject": "完成需求分析与场景分解", "status": "completed"},
  {"id": "todo_2", "subject": "生成所有场景首帧图片", "status": "in_progress", "artifacts": ["frame_1", "frame_2"]},
  {"id": "todo_3", "subject": "首帧图片质量评估", "status": "pending"},
  {"id": "todo_4", "subject": "生成视频片段", "status": "pending"},
  {"id": "todo_5", "subject": "视频合成与交付", "status": "pending"}
]
```

**推进逻辑**:
1. 每 Todo 对应一个 Phase
2. Agent 根据 Skill 约束选择执行方式
3. 完成后标记 Todo 为 completed
4. 异步任务完成后收到通知，更新 Todo

---

## 最佳实践

### 提示词设计

**首帧提示词模板**:
```
{场景主体描述}, {构图方式}, {光线条件}, {色调风格}, {细节补充}

示例:
"A drone hovering above a modern cityscape at night,
wide-angle shot showing skyscrapers with neon lights,
dramatic lighting with city glow,
cool blue and warm orange color palette,
high detail, cinematic style, 4K quality"
```

**视频提示词模板**:
```
{动作描述}, {镜头运动}, {速度/节奏}, {氛围/效果}

示例:
"The drone smoothly descends through the city buildings,
camera tracking forward with slight downward tilt,
medium speed creating dynamic feel,
atmospheric with lens flare and light reflections"
```

### 迭代优化策略

| 问题类型 | 优化策略 | 工具调用 |
|----------|----------|----------|
| 首帧构图不佳 | 优化 frame_prompt | generate_image (新参数) |
| 首帧风格不一致 | 添加 style_reference | generate_image (多图输入) |
| 视频效果不理想 | 优化 video_prompt | generate_video (新提示词) |
| 场景衔接不流畅 | 调整转场效果 | composite_video (添加过渡) |

---

## 质量检查清单

### Phase 1 检查
- [ ] 场景数量 3-8 个
- [ ] 每个场景有明确的 frame_prompt
- [ ] 每个场景有明确的 video_prompt
- [ ] 时长分配合理

### Phase 2 检查
- [ ] 所有场景首帧已生成
- [ ] 图片风格一致
- [ ] 图片质量达标

### Phase 3 检查 (可选)
- [ ] 首帧分析完成
- [ ] 获取优化建议
- [ ] 决定是否重新生成

### Phase 4 检查
- [ ] 所有视频片段已生成
- [ ] 视频时长符合预期
- [ ] 视频效果达标

### Phase 5 检查
- [ ] 最终视频合成完成
- [ ] 视频总时长符合预期
- [ ] 转场效果流畅

---

## References

- `references/video-creation-spec.md` - 详细技术规格
- `references/agents-guide.md` - Agent 实现指南
- `references/tools-guide.md` - Tool 使用说明

## Templates

- `templates/scene-analysis.md` - 场景分析输出模板
- `templates/frame-prompt.md` - 首帧提示词模板
- `templates/video-prompt.md` - 视频提示词模板
```

---

## 4. Agent 层设计

### 4.1 主调度 Agent - 直接使用 ReactMasterAgent

**不需要 VideoCreatorAgent**，现有 `ReactMasterAgent` 已具备调度能力：

| 能力 | ReactMasterAgent 已有 | 说明 |
|------|----------------------|------|
| ReAct 循环 | ✅ thinking() + action() | 思考-行动循环 |
| 异步任务管理 | ✅ AsyncTaskManager + 4个 FunctionTool | spawn_agent_task, check_tasks, wait_tasks, cancel_task |
| Todo 推进 | ✅ todowrite/todoread 系统工具 | 任务列表管理 |
| Kanban 管理 | ✅ enable_kanban=True | 看板模式（可选） |
| VIS 推送 | ✅ _system_event_manager | 前端可视化推送 |

### 4.2 专门执行 Agent (必须)

图片生成和视频生成需要专门的 Agent，每次生成一个，批量由主 Agent 调度：

#### FrameGenAgent (图片生成 Agent)

```python
# packages/derisk-ext/src/derisk_ext/agents/frame_gen_agent.py

class FrameGenAgent(AgentBase):
    """
    图片生成 Agent - 执行单次图片生成任务

    特点:
    - 每次生成一张图片
    - 批量由主 Agent 多次 spawn 实现
    - 使用 generate_image Tool
    """

    info = AgentInfo(
        name="frame_gen",
        display_name="图片生成 Agent",
        description="执行图片生成任务",
        system_prompt="""
你是一个图片生成执行 Agent。你的任务是生成一张高质量图片。

## 输入参数
- prompt: 图片描述（英文）
- scene_id: 场景标识
- provider: aliyun_wan (万相)
- model: wan2.7-image-pro
- size: 2K
- thinking_mode: true (开启思考模式)

## 执行步骤
1. 调用 generate_image Tool
2. 等待生成完成
3. 返回图片 URL 和 artifact_id

## 输出格式
返回单个图片信息:
```json
{
  "scene_id": "scene_1",
  "image_url": "...",
  "artifact_id": "...",
  "prompt_used": "..."
}
```
""",
        tools=["generate_image"],
        max_steps=5,
    )
```

#### VideoGenAgent (视频生成 Agent)

```python
# packages/derisk-ext/src/derisk_ext/agents/video_gen_agent.py

class VideoGenAgent(AgentBase):
    """
    视频生成 Agent - 执行单次视频生成任务

    特点:
    - 每次生成一段视频
    - 批量由主 Agent 多次 spawn 实现
    - 使用 generate_video Tool
    - 处理长耗时任务 (1-5分钟)
    """

    info = AgentInfo(
        name="video_gen",
        display_name="视频生成 Agent",
        description="执行视频生成任务",
        system_prompt="""
你是一个视频生成执行 Agent。你的任务是生成一段视频。

## 输入参数
- prompt: 视频动作描述（英文）
- scene_id: 场景标识
- first_frame_image_url: 首帧图片 URL
- duration: 视频时长（秒）
- provider: volcengine (火山引擎)
- model: doubao-seedance-1-5-pro-251215

## 执行步骤
1. 调用 generate_video Tool
2. 等待生成完成（1-5分钟）
3. 返回视频 URL 和 artifact_id

## 输出格式
返回单个视频信息:
```json
{
  "scene_id": "scene_1",
  "video_url": "...",
  "duration": 5,
  "artifact_id": "...",
  "first_frame_source": "..."
}
```
""",
        tools=["generate_video"],
        max_steps=5,
    )
```

### 4.3 主 Agent 调度方式

ReactMasterAgent 通过多次 `spawn_agent_task` 实现批量并发：

```python
# 主 Agent thinking() 中决策
场景数量 = len(scenes)

# 方式1: 多次 spawn 实现并发批量
for scene in scenes:
    spawn_agent_task(
        agent_name="frame_gen",
        task=f"为场景 {scene['scene_id']} 生成首帧图片: {scene['frame_prompt']}"
    )

# 方式2: 等待所有完成
wait_tasks(task_ids=[...], timeout=300)

# 方式3: 检查状态后继续
check_tasks()
```

---

## 5. Tool 层扩展

### 5.1 新增 Provider

#### AliyunWanProvider (万相图片生成)

```python
# packages/derisk-core/src/derisk/agent/util/media_gen/aliyun_wan_provider.py

@MediaGenProviderRegistry.register(name="aliyun_wan", env_key="DASHSCOPE_API_KEY")
class AliyunWanProvider(MediaGenProvider):
    """阿里云万相图像生成 Provider"""

    def supported_image_models(self) -> List[str]:
        return ["wan2.7-image-pro", "wan2.7-image"]

    def supported_video_models(self) -> List[str]:
        return []

    async def generate_image(self, prompt: str, model: str, **kwargs) -> MediaGenResult:
        """
        万相图像生成

        支持参数:
        - images: List[str] - 参考图片 URL (用于图像编辑)
        - bbox_list: List - 框选区域 (交互式编辑)
        - enable_sequential: bool - 组图模式
        - n: int - 生成数量
        - size: str - 分辨率 (1K/2K/4K)
        - thinking_mode: bool - 思考模式
        - watermark: bool - 水印
        """
        # 实现 API 调用
        ...
```

#### VolcengineVideoProvider (火山引擎视频生成)

```python
# packages/derisk-core/src/derisk/agent/util/media_gen/volcengine_video_provider.py

@MediaGenProviderRegistry.register(name="volcengine", env_key="ARK_API_KEY")
class VolcengineVideoProvider(MediaGenProvider):
    """火山引擎 doubao-seedance 视频生成 Provider"""

    def supported_image_models(self) -> List[str]:
        return []

    def supported_video_models(self) -> List[str]:
        return ["doubao-seedance-1-5-pro-251215"]

    async def generate_video(self, prompt: str, model: str, **kwargs) -> MediaGenResult:
        """
        Seedance 视频生成

        支持参数:
        - first_frame_image_url: str - 首帧图片 URL
        - duration: int - 视频时长 (秒)
        - camera_fixed: bool - 是否固定镜头
        - watermark: bool - 是否添加水印
        """
        from volcenginesdkarkruntime import Ark

        client = Ark(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=self.api_key,
        )

        # Step 1: 提交任务
        content = [{"type": "text", "text": prompt}]
        if kwargs.get("first_frame_image_url"):
            content.append({
                "type": "image_url",
                "image_url": {"url": kwargs["first_frame_image_url"]}
            })

        task = client.content_generation.tasks.create(
            model=model,
            content=content,
        )

        # Step 2: 轮询等待
        ...

        # Step 3: 下载视频
        ...
```

### 5.2 新增 Tools

#### AnalyzeImageTool (图片分析)

```python
# packages/derisk-core/src/derisk/agent/tools/builtin/media_gen/analyze_image_tool.py

class AnalyzeImageTool(ToolBase):
    """图片分析工具 - 使用多模态模型分析图片内容"""

    name = "analyze_image"

    def _define_parameters(self):
        return {
            "type": "object",
            "properties": {
                "image_url": {
                    "type": "string",
                    "description": "图片 URL",
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["composition", "quality", "video_suitability", "full"],
                    "description": "分析类型",
                    "default": "full",
                },
                "context": {
                    "type": "string",
                    "description": "分析上下文 (如原始提示词)",
                },
            },
            "required": ["image_url"],
        }

    async def execute(self, args, context) -> ToolResult:
        image_url = args["image_url"]
        analysis_type = args.get("analysis_type", "full")

        # 构建分析提示词
        analysis_prompt = self._build_analysis_prompt(analysis_type, args.get("context"))

        # 使用多模态 LLM 分析
        llm_result = await self._call_multimodal_llm(
            prompt=analysis_prompt,
            images=[image_url],
        )

        return ToolResult.ok(
            output=llm_result.output,
            artifacts=[ImageArtifact(
                file_url=image_url,
                metadata={"analysis": llm_result.output},
            )]
        )
```

#### CompositeVideoTool (视频合成)

```python
# packages/derisk-core/src/derisk/agent/tools/builtin/media_gen/composite_video_tool.py

class CompositeVideoTool(ToolBase):
    """视频合成工具 - 将多个视频片段合成为最终视频"""

    name = "composite_video"

    def _define_parameters(self):
        return {
            "type": "object",
            "properties": {
                "video_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "视频片段 URL 列表 (按顺序)",
                },
                "transition": {
                    "type": "string",
                    "enum": ["none", "fade", "crossfade", "wipe"],
                    "description": "转场效果",
                    "default": "crossfade",
                },
                "transition_duration": {
                    "type": "number",
                    "description": "转场时长 (秒)",
                    "default": 0.5,
                },
                "output_resolution": {
                    "type": "string",
                    "enum": ["720p", "1080p", "4K"],
                    "description": "输出分辨率",
                    "default": "1080p",
                },
            },
            "required": ["video_urls"],
        }

    async def execute(self, args, context) -> ToolResult:
        video_urls = args["video_urls"]
        transition = args.get("transition", "crossfade")

        # 使用 FFmpeg 合成
        composite_result = await self._composite_with_ffmpeg(
            video_urls, transition, args
        )

        # 保存到 AFS
        afs = context.get_resource("agent_file_system")
        file_meta = await afs.save_binary_file(
            file_key="final_video",
            data=composite_result.data,
            file_type=FileType.DELIVERABLE,
            extension="mp4",
            ...
        )

        return ToolResult.ok(
            output=f"视频合成完成: {file_meta.preview_url}",
            artifacts=[VideoArtifact(
                file_name=file_meta.file_name,
                file_url=file_meta.preview_url,
                duration_seconds=composite_result.duration,
                metadata={
                    "segment_count": len(video_urls),
                    "transition": transition,
                }
            )]
        )
```

---

## 6. 完整执行流程示例

```
用户: "制作一个无人机穿越城市夜景的宣传视频，时长约30秒"

=== Phase 1: 需求分析 ===

VideoCreatorAgent think():
  - 读取 VideoCreation Skill 约束
  - 分析用户需求
  - 决策: 直接执行分析 (场景较少)

VideoCreatorAgent act():
  - 调用文本模型进行分析
  - 输出场景分解:
    ```json
    {
      "scenes": [
        {"scene_id": "scene_1", "description": "城市夜景俯瞰",
         "frame_prompt": "Night cityscape from drone view...",
         "video_prompt": "Smooth descending through buildings..."},
        {"scene_id": "scene_2", "description": "霓虹街道穿梭",
         ...},
        {"scene_id": "scene_3", "description": "高楼之间飞行",
         ...},
        {"scene_id": "scene_4", "description": "最终俯冲落地",
         ...}
      ]
    }
    ```
  - 更新 Todo: todo_1 = completed

=== Phase 2: 首帧生成 ===

VideoCreatorAgent think():
  - 4个场景，数量适中
  - 决策: spawn frame_gen_agent 子 Agent (并发效率更高)

VideoCreatorAgent act():
  - spawn_agent_task(agent_name="frame_gen", task="生成4个场景首帧")
  - 返回: task_id = "atask_frame_001"
  - 更新 Todo: todo_2 = in_progress

[后台执行: frame_gen_agent 并发生成4张首帧]

VideoCreatorAgent think():
  - 收到异步任务通知:
    ```
    [异步任务完成通知]
    Task atask_frame_001 (frame_gen) completed
    结果: 生成了 4 张首帧图片
    Artifacts: [frame_scene_1.png, frame_scene_2.png, ...]
    ```
  - 决策: 检查首帧质量，决定是否需要 review

VideoCreatorAgent act():
  - 更新 Todo: todo_2 = completed, artifacts=[frame_1, frame_2, ...]
  - 决策: 进行首帧质量评估 (执行 Phase 3)

=== Phase 3: 首帧分析与优化 ===

VideoCreatorAgent think():
  - 需要专业图片分析
  - 决策: spawn frame_review_agent 子 Agent

VideoCreatorAgent act():
  - spawn_agent_task(agent_name="frame_review", task="分析4张首帧质量")
  - 返回: task_id = "atask_review_001"
  - 更新 Todo: todo_3 = in_progress

[后台执行: frame_review_agent 使用多模态模型分析图片]

VideoCreatorAgent think():
  - 收到异步任务通知:
    ```
    [异步任务完成通知]
    Task atask_review_001 (frame_review) completed
    结果:
    - frame_scene_1: score=8, 建议优化光线
    - frame_scene_2: score=9, 质量优秀
    - frame_scene_3: score=7, 建议调整构图
    - frame_scene_4: score=8, 可直接使用
    ```
  - 决策: scene_3 需要重新生成

VideoCreatorAgent act():
  - 重新生成 scene_3 首帧 (使用优化后的 prompt)
  - 更新 Todo: todo_3 = completed

=== Phase 4: 视频生成 ===

VideoCreatorAgent think():
  - 4个视频片段，耗时较长 (每个约2分钟)
  - 决策: spawn video_gen_agent 子 Agent (避免阻塞)

VideoCreatorAgent act():
  - spawn_agent_task(agent_name="video_gen",
                     task="基于首帧生成4个视频片段")
  - 返回: task_id = "atask_video_001"
  - 更新 Todo: todo_4 = in_progress

[后台执行: video_gen_agent 生成视频 (约8分钟)]

VideoCreatorAgent think():
  - 收到异步任务通知: 视频生成完成
  - 决策: 进行视频合成

VideoCreatorAgent act():
  - 更新 Todo: todo_4 = completed, artifacts=[video_1, video_2, ...]

=== Phase 5: 视频合成 ===

VideoCreatorAgent think():
  - 需要专业视频合成
  - 决策: spawn composite_agent 子 Agent

VideoCreatorAgent act():
  - spawn_agent_task(agent_name="composite",
                     task="合成最终视频")
  - 返回: task_id = "atask_composite_001"
  - 更新 Todo: todo_5 = in_progress

[后台执行: composite_agent 使用 FFmpeg 合成]

VideoCreatorAgent think():
  - 收到异步任务通知: 视频合成完成
  - 决策: 生成交付报告

VideoCreatorAgent act():
  - 更新 Todo: todo_5 = completed
  - 输出最终交付:
    ```
    ✅ 视频创作完成!

    **最终视频**: [d-attach: final_video_abc.mp4]
    - 时长: 28秒
    - 分辨率: 1920x1080
    - 场景数: 4

    **创作说明**:
    - 场景1: 城市夜景俯瞰 (5秒)
    - 场景2: 霓虹街道穿梭 (7秒)
    - 场景3: 高楼飞行 (8秒)
    - 场景4: 最终落地 (8秒)

    **下载链接**: https://...
    ```
```

---

## 7. 文件结构规划

```
packages/derisk-core/src/derisk/agent/
├── tools/builtin/media_gen/
│   ├── media_gen_tools.py          # 现有，扩展参数
│   ├── analyze_image_tool.py       # 新增: 图片分析
│   ├── composite_video_tool.py     # 新增: 视频合成
│   └── __init__.py                 # 注册新 Tools
│
├── util/media_gen/
│   ├── base.py                     # 现有
│   ├── provider_registry.py        # 现有
│   ├── aliyun_wan_provider.py      # 新增: 万相 Provider
│   ├── volcengine_provider.py      # 新增: 火山引擎 Provider
│   └── __init__.py

packages/derisk-ext/src/derisk_ext/agents/
├── frame_gen_agent.py              # 新增: 图片生成 Agent (必须)
├── video_gen_agent.py              # 新增: 视频生成 Agent (必须)
└── __init__.py

.claude/skills/video-creation/
├── SKILL.md                        # Skill 主文件（约束规范）
├── references/
│   ├── video-creation-spec.md      # 详细规格
│   └── tools-guide.md              # 工具使用说明
└── templates/
    ├── scene-analysis.md           # 场景分析模板
    ├── frame-prompt.md             # 首帧提示词模板
    └── video-prompt.md             # 视频提示词模板

⚠️ 说明:
- 主调度: ReactMasterAgent (现有，无需新建)
- 专门Agent: FrameGenAgent + VideoGenAgent (必须)
- 其他任务: 主Agent直接处理或调用Tool
```

---

## 8. 实现步骤规划

### Step 1: Provider 层扩展（核心）
1. 实现 `AliyunWanProvider` (万相图片生成)
2. 实现 `VolcengineVideoProvider` (Seedance 视频生成)
3. 扩展 `MediaGenProviderRegistry`

### Step 2: Tool 层扩展（核心）
1. 扩展 `GenerateImageTool` 支持万相参数 (images, bbox_list, thinking_mode 等)
2. 扩展 `GenerateVideoTool` 支持首帧图片输入 (first_frame_image_url)
3. 新增 `AnalyzeImageTool` (图片分析)
4. 新增 `CompositeVideoTool` (视频合成)

### Step 3: Agent 层实现（必须）
1. 实现 `FrameGenAgent` (图片生成 Agent)
2. 实现 `VideoGenAgent` (视频生成 Agent)
3. 配置 ReactMasterAgent 绑定这两个子 Agent

### Step 4: Skill 层定义（约束）
1. 创建 VideoCreation Skill 目录结构
2. 编写 SKILL.md (工作流程规范、最佳实践)
3. 编写提示词模板和工具使用指南

### Step 5: 测试与验证
1. 单元测试各 Provider 和 Tool
2. 测试子 Agent 单次生成
3. 端到端测试完整视频创作场景（主 Agent 调度批量）

---

## 9. 优势总结

| 优势 | 说明 |
|------|------|
| **最小 Agent 设计** | 只需 2 个专门 Agent，主调度用现有 ReactMasterAgent |
| **Skill 约束** | 最佳实践通过 Skill 文档化，而非代码固化 |
| **批量由调度实现** | 子 Agent 单次生成，主 Agent 多次 spawn 并发 |
| **现有能力复用** | Todo、AsyncTask、Kanban 全部已有 |
| **产物追踪** | ToolResult.artifacts 自动流转 |

---

## 附录 A: 相关文档

- `docs/ASYNC_TASK_SYSTEM.md` - 异步任务系统详细说明
- `docs/TOOL_SYSTEM_ARCHITECTURE.md` - Tool 系统架构
- `.claude/skills/openderisk-dev/SKILL.md` - OpenDeRisk 开发 Skill

## 附录 B: API 参考

- 万相 API: https://help.aliyun.com/zh/model-studio/wan-image-generation-api-reference
- Seedance API: https://www.volcengine.com/docs/82379/1521675