"""
场景管理 API 路由
提供场景定义的 CRUD 操作和场景管理功能

支持 Markdown 格式场景定义，使用 YAML Front Matter 管理元数据：

```markdown
---
id: code-review
name: 代码评审
description: 评审代码质量和规范
priority: 8
keywords: ["code", "review", "评审", "代码"]
allow_tools: ["read", "edit", "search", "ask"]
---

## 角色设定

你是一个资深的代码评审专家...

## 工作流程

...
```
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


# ==================== 数据模型 ====================


class SceneCreateRequest(BaseModel):
    """创建场景请求"""

    scene_id: str = Field(..., description="场景 ID")
    scene_name: str = Field(..., description="场景名称")
    description: str = Field(default="", description="场景描述")
    trigger_keywords: List[str] = Field(default_factory=list, description="触发关键词")
    trigger_priority: int = Field(default=5, description="触发优先级")
    scene_role_prompt: str = Field(default="", description="场景角色设定")
    scene_tools: List[str] = Field(default_factory=list, description="场景工具")
    md_content: Optional[str] = Field(
        default=None, description="MD 文件内容（YAML Front Matter + Markdown）"
    )


class SceneUpdateRequest(BaseModel):
    """更新场景请求"""

    scene_name: Optional[str] = None
    description: Optional[str] = None
    trigger_keywords: Optional[List[str]] = None
    trigger_priority: Optional[int] = None
    scene_role_prompt: Optional[str] = None
    scene_tools: Optional[List[str]] = None
    md_content: Optional[str] = None


class SceneResponse(BaseModel):
    """场景响应"""

    scene_id: str
    scene_name: str
    description: str
    trigger_keywords: List[str]
    trigger_priority: int
    scene_role_prompt: str
    scene_tools: List[str]
    md_content: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SceneActivateRequest(BaseModel):
    """激活场景请求"""

    session_id: str = Field(..., description="会话 ID")
    agent_id: str = Field(..., description="Agent ID")


class SceneSwitchRequest(BaseModel):
    """切换场景请求"""

    session_id: str = Field(..., description="会话 ID")
    agent_id: str = Field(..., description="Agent ID")
    from_scene: Optional[str] = Field(default=None, description="源场景")
    to_scene: str = Field(..., description="目标场景")
    reason: str = Field(default="", description="切换原因")


class ScenePromptInjectionRequest(BaseModel):
    """场景 Prompt 注入请求"""

    session_id: str = Field(..., description="会话 ID")
    scene_ids: List[str] = Field(default_factory=list, description="要注入的场景ID列表")
    inject_mode: str = Field(
        default="append", description="注入模式: append/prepend/replace"
    )


class ScenePromptInjectionResponse(BaseModel):
    """场景 Prompt 注入响应"""

    success: bool
    session_id: str
    injected_scenes: List[str]
    system_prompt: str
    message: str


# ==================== YAML Front Matter 解析工具 ====================


def parse_front_matter(content: str) -> Dict[str, Any]:
    """
    解析 Markdown 内容的 YAML Front Matter

    Args:
        content: Markdown 文件内容

    Returns:
        解析后的 front matter 字典和正文内容
    """
    result = {"front_matter": {}, "body": content}

    # 匹配 YAML front matter 格式: ---\n...\n---
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return result

    yaml_content = match.group(1)
    body = match.group(2)
    front_matter = {}

    # 简单解析 YAML 格式
    for line in yaml_content.split("\n"):
        line = line.strip()
        if ":" in line:
            colon_idx = line.index(":")
            key = line[:colon_idx].strip()
            value = line[colon_idx + 1 :].strip()

            # 解析数组格式 [item1, item2]
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                value = [item.strip().strip("\"'") for item in items if item.strip()]
            # 解析字符串（去除引号）
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            # 解析数字
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
            # 解析布尔值
            elif value.lower() in ("true", "yes"):
                value = True
            elif value.lower() in ("false", "no"):
                value = False

            front_matter[key] = value

    result["front_matter"] = front_matter
    result["body"] = body.strip()
    return result


def generate_front_matter(front_matter: Dict[str, Any], body: str) -> str:
    """
    生成带 YAML Front Matter 的 Markdown 内容

    Args:
        front_matter: front matter 字典
        body: 正文内容

    Returns:
        完整的 Markdown 内容
    """
    lines = []
    lines.append("---")

    for key, value in front_matter.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        elif isinstance(value, str):
            # 如果字符串包含特殊字符，添加引号
            if ":" in value or '"' in value or "\n" in value:
                escaped = value.replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
            else:
                lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")

    lines.append("---")
    lines.append("")
    lines.append(body.strip())

    return "\n".join(lines)


def extract_scene_from_content(scene_id: str, md_content: str) -> Dict[str, Any]:
    """
    从 Markdown 内容提取场景信息

    Args:
        scene_id: 场景ID
        md_content: Markdown 内容

    Returns:
        场景信息字典
    """
    parsed = parse_front_matter(md_content)
    fm = parsed.get("front_matter", {})
    body = parsed.get("body", "")

    # 提取场景角色设定（从 body 中）
    scene_role_prompt = ""
    role_match = re.search(
        r"##\s*(?:角色设定|Role).*?\n(.*?)(?=##|$)", body, re.DOTALL | re.IGNORECASE
    )
    if role_match:
        scene_role_prompt = role_match.group(1).strip()

    return {
        "scene_id": scene_id,
        "scene_name": fm.get("name", scene_id),
        "description": fm.get("description", ""),
        "trigger_keywords": fm.get("keywords", []),
        "trigger_priority": fm.get("priority", 5),
        "scene_role_prompt": scene_role_prompt,
        "scene_tools": fm.get("allow_tools", []),
    }


def build_system_prompt_from_scene(md_content: str) -> str:
    """
    从场景 Markdown 内容构建 System Prompt

    将场景的 YAML front matter 和 markdown 内容转换为 system prompt

    Args:
        md_content: 场景 Markdown 内容

    Returns:
        System Prompt 字符串
    """
    parsed = parse_front_matter(md_content)
    fm = parsed.get("front_matter", {})
    body = parsed.get("body", "")

    prompt_parts = []

    # 添加场景名称和描述
    if fm.get("name"):
        prompt_parts.append(f"# {fm['name']}")
    if fm.get("description"):
        prompt_parts.append(f"\n{fm['description']}\n")

    # 添加主体内容
    if body:
        prompt_parts.append(body)

    # 添加工具提示
    if fm.get("allow_tools"):
        tools = fm["allow_tools"]
        prompt_parts.append(f"\n## 可用工具\n")
        prompt_parts.append(f"你可以使用以下工具: {', '.join(tools)}")

    return "\n".join(prompt_parts)


# ==================== 模拟数据存储 ====================

# 在实际实现中，应该使用数据库
_scenes_db: Dict[str, Any] = {}
_sessions_db: Dict[str, Any] = {}


# 初始化一些示例场景
def _init_default_scenes():
    """初始化默认场景"""
    default_scenes = [
        {
            "scene_id": "coding",
            "scene_name": "代码编写",
            "description": "编写和修改代码",
            "md_content": """---
id: coding
name: 代码编写
description: 编写和修改代码
priority: 8
keywords: ["code", "coding", "编程", "写代码"]
allow_tools: ["read", "write", "edit", "search", "execute"]
---

## 角色设定

你是一个资深的软件工程师，专注于编写高质量、可维护的代码。

## 工作原则

1. 编写清晰、简洁的代码
2. 遵循最佳实践和设计模式
3. 添加适当的注释和文档
4. 考虑边界情况和错误处理

## 工作流程

1. 理解需求和上下文
2. 设计解决方案
3. 编写代码实现
4. 验证代码正确性
""",
        },
        {
            "scene_id": "code-review",
            "scene_name": "代码评审",
            "description": "评审代码质量和规范",
            "md_content": """---
id: code-review
name: 代码评审
description: 评审代码质量和规范
priority: 7
keywords: ["review", "评审", "code review", "代码评审"]
allow_tools: ["read", "ask"]
---

## 角色设定

你是一个严格的代码评审专家，专注于发现代码中的问题和改进点。

## 评审维度

1. 代码正确性和逻辑
2. 代码风格和规范
3. 性能和效率
4. 安全性和异常处理
5. 可读性和可维护性

## 输出格式

- 严重问题（必须修复）
- 建议改进（可选）
- 正面反馈
""",
        },
    ]

    for scene in default_scenes:
        if scene["scene_id"] not in _scenes_db:
            now = datetime.now()
            scene["created_at"] = now
            scene["updated_at"] = now
            scene["trigger_keywords"] = scene.get("trigger_keywords", [])
            scene["trigger_priority"] = scene.get("trigger_priority", 5)
            scene["scene_role_prompt"] = ""
            scene["scene_tools"] = []
            _scenes_db[scene["scene_id"]] = scene


_init_default_scenes()


# ==================== CRUD API ====================


@router.get("", response_model=List[SceneResponse])
async def list_scenes(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)
):
    """
    列出所有场景

    Args:
        skip: 跳过数量
        limit: 返回数量限制

    Returns:
        场景列表
    """
    scenes = list(_scenes_db.values())
    return scenes[skip : skip + limit]


@router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(scene_id: str):
    """
    获取场景详情

    Args:
        scene_id: 场景 ID

    Returns:
        场景详情
    """
    if scene_id not in _scenes_db:
        raise HTTPException(status_code=404, detail="Scene not found")

    return _scenes_db[scene_id]


@router.post("", response_model=SceneResponse)
async def create_scene(request: SceneCreateRequest):
    """
    创建场景

    支持通过 YAML Front Matter 格式定义场景元数据：
    - id: 场景ID
    - name: 场景名称
    - description: 描述
    - priority: 优先级(1-10)
    - keywords: 触发关键词列表
    - allow_tools: 允许使用的工具列表

    Args:
        request: 创建请求

    Returns:
        创建的场景
    """
    if request.scene_id in _scenes_db:
        raise HTTPException(status_code=400, detail="Scene already exists")

    now = datetime.now()

    # 如果有 md_content，解析并提取信息
    if request.md_content:
        extracted = extract_scene_from_content(request.scene_id, request.md_content)
        scene = {
            "scene_id": request.scene_id,
            "scene_name": extracted.get("scene_name", request.scene_name),
            "description": extracted.get("description", request.description),
            "trigger_keywords": extracted.get(
                "trigger_keywords", request.trigger_keywords or []
            ),
            "trigger_priority": extracted.get(
                "trigger_priority", request.trigger_priority or 5
            ),
            "scene_role_prompt": extracted.get(
                "scene_role_prompt", request.scene_role_prompt or ""
            ),
            "scene_tools": extracted.get("scene_tools", request.scene_tools or []),
            "md_content": request.md_content,
            "created_at": now,
            "updated_at": now,
        }
    else:
        # 生成默认的 md_content
        md_content = f"""---
id: {request.scene_id}
name: {request.scene_name}
description: {request.description}
priority: {request.trigger_priority or 5}
keywords: [{", ".join(request.trigger_keywords or [])}]
allow_tools: [{", ".join(request.scene_tools or [])}]
---

## 角色设定

{request.scene_role_prompt or "请设置场景角色..."}
"""
        scene = {
            "scene_id": request.scene_id,
            "scene_name": request.scene_name,
            "description": request.description,
            "trigger_keywords": request.trigger_keywords or [],
            "trigger_priority": request.trigger_priority or 5,
            "scene_role_prompt": request.scene_role_prompt or "",
            "scene_tools": request.scene_tools or [],
            "md_content": md_content,
            "created_at": now,
            "updated_at": now,
        }

    _scenes_db[request.scene_id] = scene

    logger.info(f"[SceneAPI] Created scene: {request.scene_id}")

    return scene


@router.put("/{scene_id}", response_model=SceneResponse)
async def update_scene(scene_id: str, request: SceneUpdateRequest):
    """
    更新场景

    Args:
        scene_id: 场景 ID
        request: 更新请求

    Returns:
        更新后的场景
    """
    if scene_id not in _scenes_db:
        raise HTTPException(status_code=404, detail="Scene not found")

    scene = _scenes_db[scene_id]

    # 更新字段
    if request.scene_name is not None:
        scene["scene_name"] = request.scene_name
    if request.description is not None:
        scene["description"] = request.description
    if request.trigger_keywords is not None:
        scene["trigger_keywords"] = request.trigger_keywords
    if request.trigger_priority is not None:
        scene["trigger_priority"] = request.trigger_priority
    if request.scene_role_prompt is not None:
        scene["scene_role_prompt"] = request.scene_role_prompt
    if request.scene_tools is not None:
        scene["scene_tools"] = request.scene_tools
    if request.md_content is not None:
        scene["md_content"] = request.md_content
        # 重新解析 front matter 更新其他字段
        extracted = extract_scene_from_content(scene_id, request.md_content)
        scene["scene_name"] = extracted.get("scene_name", scene["scene_name"])
        scene["description"] = extracted.get("description", scene["description"])
        scene["trigger_keywords"] = extracted.get(
            "trigger_keywords", scene["trigger_keywords"]
        )
        scene["trigger_priority"] = extracted.get(
            "trigger_priority", scene["trigger_priority"]
        )
        scene["scene_role_prompt"] = extracted.get(
            "scene_role_prompt", scene["scene_role_prompt"]
        )
        scene["scene_tools"] = extracted.get("scene_tools", scene["scene_tools"])

    scene["updated_at"] = datetime.now()

    logger.info(f"[SceneAPI] Updated scene: {scene_id}")

    return scene


@router.delete("/{scene_id}")
async def delete_scene(scene_id: str):
    """
    删除场景

    Args:
        scene_id: 场景 ID

    Returns:
        删除结果
    """
    if scene_id not in _scenes_db:
        raise HTTPException(status_code=404, detail="Scene not found")

    del _scenes_db[scene_id]

    logger.info(f"[SceneAPI] Deleted scene: {scene_id}")

    return {"success": True, "message": f"Scene {scene_id} deleted"}


# ==================== 场景管理 API ====================


@router.post("/activate", response_model=Dict[str, Any])
async def activate_scene(request: SceneActivateRequest):
    """
    激活场景

    Args:
        request: 激活请求

    Returns:
        激活结果
    """
    session_id = request.session_id

    if session_id not in _sessions_db:
        _sessions_db[session_id] = {
            "current_scene": None,
            "history": [],
            "system_prompts": [],
        }

    _sessions_db[session_id]["current_scene"] = {
        "scene_id": request.agent_id,  # 简化示例
        "activated_at": datetime.now(),
    }

    return {"success": True, "session_id": session_id, "activated_at": datetime.now()}


@router.post("/switch", response_model=Dict[str, Any])
async def switch_scene(request: SceneSwitchRequest):
    """
    切换场景

    Args:
        request: 切换请求

    Returns:
        切换结果
    """
    session_id = request.session_id

    if session_id not in _sessions_db:
        raise HTTPException(status_code=404, detail="Session not found")

    # 记录切换历史
    switch_record = {
        "from_scene": request.from_scene,
        "to_scene": request.to_scene,
        "timestamp": datetime.now(),
        "reason": request.reason,
    }

    _sessions_db[session_id]["history"].append(switch_record)
    _sessions_db[session_id]["current_scene"] = {
        "scene_id": request.to_scene,
        "activated_at": datetime.now(),
    }

    return {
        "success": True,
        "session_id": session_id,
        "switched_at": datetime.now(),
        "from_scene": request.from_scene,
        "to_scene": request.to_scene,
    }


@router.get("/history/{session_id}")
async def get_scene_history(session_id: str):
    """
    获取场景切换历史

    Args:
        session_id: 会话 ID

    Returns:
        切换历史
    """
    if session_id not in _sessions_db:
        return {"history": []}

    return {"history": _sessions_db[session_id]["history"]}


# ==================== 场景 Prompt 注入 API ====================


@router.post("/inject-prompt", response_model=ScenePromptInjectionResponse)
async def inject_scene_prompt(request: ScenePromptInjectionRequest):
    """
    将场景内容注入 System Prompt

    自动将场景定义转换为 System Prompt 并注入到会话中

    Args:
        request: 注入请求，包含场景ID列表和注入模式

    Returns:
        注入结果，包含生成的 System Prompt
    """
    session_id = request.session_id
    scene_ids = request.scene_ids
    inject_mode = request.inject_mode

    # 获取场景内容
    scenes_content = []
    for scene_id in scene_ids:
        if scene_id in _scenes_db:
            scene = _scenes_db[scene_id]
            if scene.get("md_content"):
                scenes_content.append(
                    {
                        "scene_id": scene_id,
                        "name": scene.get("scene_name", scene_id),
                        "prompt": build_system_prompt_from_scene(scene["md_content"]),
                    }
                )

    if not scenes_content:
        raise HTTPException(status_code=400, detail="No valid scenes found")

    # 构建完整的 system prompt
    if len(scenes_content) == 1:
        final_prompt = scenes_content[0]["prompt"]
    else:
        # 多个场景时，按优先级组合
        prompt_parts = [f"# 多场景模式\n"]
        prompt_parts.append(f"当前会话关联 {len(scenes_content)} 个场景:\n")
        for i, sc in enumerate(scenes_content, 1):
            prompt_parts.append(f"\n## 场景 {i}: {sc['name']}")
            prompt_parts.append(sc["prompt"])
        final_prompt = "\n".join(prompt_parts)

    # 存储到会话
    if session_id not in _sessions_db:
        _sessions_db[session_id] = {
            "current_scene": None,
            "history": [],
            "system_prompts": [],
        }

    _sessions_db[session_id]["system_prompts"] = {
        "injected_scenes": scene_ids,
        "system_prompt": final_prompt,
        "inject_mode": inject_mode,
        "injected_at": datetime.now(),
    }

    logger.info(
        f"[SceneAPI] Injected {len(scene_ids)} scenes into session {session_id}"
    )

    return ScenePromptInjectionResponse(
        success=True,
        session_id=session_id,
        injected_scenes=scene_ids,
        system_prompt=final_prompt,
        message=f"Successfully injected {len(scene_ids)} scene(s) into system prompt",
    )


@router.get("/prompt/{session_id}")
async def get_session_scene_prompt(session_id: str):
    """
    获取会话的场景 System Prompt

    Args:
        session_id: 会话 ID

    Returns:
        当前会话的 System Prompt
    """
    if session_id not in _sessions_db:
        return {"has_prompt": False, "system_prompt": None, "injected_scenes": []}

    prompt_data = _sessions_db[session_id].get("system_prompts", {})

    return {
        "has_prompt": bool(prompt_data.get("system_prompt")),
        "system_prompt": prompt_data.get("system_prompt"),
        "injected_scenes": prompt_data.get("injected_scenes", []),
        "injected_at": prompt_data.get("injected_at"),
        "inject_mode": prompt_data.get("inject_mode"),
    }


# ==================== 导出路由 ====================

__all__ = ["router"]
