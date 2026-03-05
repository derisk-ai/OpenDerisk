import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP

# ------------------------ Request Model ------------------------
class SkillRequest(BaseModel):
    """Skill request model"""
    skill_code: Optional[str] = Field(None, description="skill code")
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="skill name")
    description: Optional[str] = Field(None, min_length=1, description="skill description")
    type: Optional[str] = Field(None, min_length=1, max_length=255, description="skill type")
    author: Optional[str] = Field(None, max_length=255, description="skill author")
    email: Optional[str] = Field(None, max_length=255, description="skill author email")

    version: Optional[str] = Field(None, max_length=255, description="skill version")
    path: Optional[str] = Field(None, description="skill path")
    content: Optional[str] = Field(None, description="skill content (markdown)")
    icon: Optional[str] = Field(None, description="skill icon")
    category: Optional[str] = Field(None, description="skill category")
    installed: Optional[int] = Field(None, ge=0, description="skill installed count")
    available: Optional[bool] = Field(None, description="skill availability status")
    
    # Git related fields
    repo_url: Optional[str] = Field(None, description="git repository url")
    branch: Optional[str] = Field(None, description="git branch")
    commit_id: Optional[str] = Field(None, description="git commit id")

    model_config = ConfigDict(
        title=f"SkillRequest for {SERVE_APP_NAME_HUMP}",
        json_schema_extra={
            "example": {
                "name": "my-skill",
                "description": "A sample skill",
                "type": "python",
                "version": "1.0.0"
            }
        }
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary with JSON handling"""
        return model_to_dict(self, **kwargs)


# ------------------------ Response Model ------------------------
class SkillResponse(BaseModel):
    """Skill response model"""

    skill_code: str = Field(..., description="skill code")
    name: str = Field(..., description="skill name")
    description: str = Field(..., description="skill description")
    type: str = Field(..., description="skill type")
    author: Optional[str] = Field(None, description="skill author")
    email: Optional[str] = Field(None, description="skill author email")

    version: Optional[str] = Field(None, description="skill version")
    path: Optional[str] = Field(None, description="skill path")
    content: Optional[str] = Field(None, description="skill content (markdown)")
    icon: Optional[str] = Field(None, description="skill icon")
    category: Optional[str] = Field(None, description="skill category")
    installed: Optional[int] = Field(None, description="skill installed count")
    available: Optional[bool] = Field(None, description="skill availability status")
    
    repo_url: Optional[str] = Field(None, description="git repository url")
    branch: Optional[str] = Field(None, description="git branch")
    commit_id: Optional[str] = Field(None, description="git commit id")

    gmt_created: str = Field(..., description="ISO format creation time")
    gmt_modified: str = Field(..., description="ISO format modification time")

    model_config = ConfigDict(
        title=f"SkillResponse for {SERVE_APP_NAME_HUMP}",
        json_encoders={datetime: lambda dt: dt.isoformat()},
        from_attributes=True
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a API-safe dictionary"""
        return model_to_dict(
            self,
            exclude_none=True,
            by_alias=True,
            **kwargs
        )

    @classmethod
    def parse_database_model(cls, entity: Any) -> 'SkillResponse':
        """Alternative constructor for database model conversion"""
        model_dict = entity.__dict__

        # Convert datetime to ISO strings
        for time_field in ['gmt_created', 'gmt_modified']:
            if isinstance(model_dict.get(time_field), datetime):
                model_dict[time_field] = model_dict[time_field].isoformat()

        return cls(**model_dict)


class SkillQueryFilter(BaseModel):
    filter: str = Field(None, description="skill name or description filter")


class SkillFileListResponse(BaseModel):
    """Response for skill file list"""

    skill_code: str = Field(..., description="skill code")
    skill_path: str = Field(..., description="skill directory path")
    files: List[Dict[str, Any]] = Field(..., description="list of files in skill directory")

    model_config = ConfigDict(
        title=f"SkillFileListResponse for {SERVE_APP_NAME_HUMP}",
        from_attributes=True
    )


class SkillFileReadRequest(BaseModel):
    """Request to read a skill file"""

    skill_code: str = Field(..., description="skill code")
    file_path: str = Field(..., description="relative file path within skill directory")

    model_config = ConfigDict(
        title=f"SkillFileReadRequest for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileReadResponse(BaseModel):
    """Response for skill file read"""

    skill_code: str = Field(..., description="skill code")
    file_path: str = Field(..., description="file path")
    content: str = Field(..., description="file content")
    file_type: str = Field(..., description="file type (md, py, js, etc.)")

    model_config = ConfigDict(
        title=f"SkillFileReadResponse for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileWriteRequest(BaseModel):
    """Request to write a skill file"""

    skill_code: str = Field(..., description="skill code")
    file_path: str = Field(..., description="relative file path within skill directory")
    content: str = Field(..., description="file content to write")

    model_config = ConfigDict(
        title=f"SkillFileWriteRequest for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileWriteResponse(BaseModel):
    """Response for skill file write"""

    skill_code: str = Field(..., description="skill code")
    file_path: str = Field(..., description="file path")
    success: bool = Field(..., description="write operation success")
    message: str = Field(..., description="operation message")

    model_config = ConfigDict(
        title=f"SkillFileWriteResponse for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileRenameRequest(BaseModel):
    """Request to rename a skill file"""

    skill_code: str = Field(..., description="skill code")
    old_path: str = Field(..., description="current relative file path within skill directory")
    new_path: str = Field(..., description="new relative file path within skill directory")

    model_config = ConfigDict(
        title=f"SkillFileRenameRequest for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileRenameResponse(BaseModel):
    """Response for skill file rename"""

    skill_code: str = Field(..., description="skill code")
    old_path: str = Field(..., description="old file path")
    new_path: str = Field(..., description="new file path")
    success: bool = Field(..., description="rename operation success")
    message: str = Field(..., description="operation message")

    model_config = ConfigDict(
        title=f"SkillFileRenameResponse for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileUploadItem(BaseModel):
    """Single file item for batch upload"""

    file_path: str = Field(..., description="relative file path within skill directory")
    content: str = Field(..., description="file content (base64 encoded for binary files)")
    is_base64: bool = Field(False, description="whether content is base64 encoded")

    model_config = ConfigDict(
        title=f"SkillFileUploadItem for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileBatchUploadRequest(BaseModel):
    """Request for batch file upload"""

    skill_code: str = Field(..., description="skill code")
    files: List[SkillFileUploadItem] = Field(..., description="list of files to upload")
    overwrite: bool = Field(False, description="whether to overwrite existing files")

    model_config = ConfigDict(
        title=f"SkillFileBatchUploadRequest for {SERVE_APP_NAME_HUMP}"
    )


class SkillFileBatchUploadResponse(BaseModel):
    """Response for batch file upload"""

    skill_code: str = Field(..., description="skill code")
    total_count: int = Field(..., description="total number of files to upload")
    success_count: int = Field(..., description="number of successfully uploaded files")
    failed_count: int = Field(..., description="number of failed uploads")
    success_files: List[str] = Field(default_factory=list, description="list of successfully uploaded file paths")
    failed_files: List[Dict[str, str]] = Field(default_factory=list, description="list of failed file paths with error messages")

    model_config = ConfigDict(
        title=f"SkillFileBatchUploadResponse for {SERVE_APP_NAME_HUMP}"
    )


# ------------------------ Sync Task Models ------------------------
class SkillSyncTaskRequest(BaseModel):
    """Request to create a sync task"""

    repo_url: str = Field(..., description="git repository url")
    branch: str = Field("main", description="git branch")
    force_update: bool = Field(False, description="force update existing skills")

    model_config = ConfigDict(
        title=f"SkillSyncTaskRequest for {SERVE_APP_NAME_HUMP}",
        json_schema_extra={
            "example": {
                "repo_url": "https://github.com/anthropics/skills",
                "branch": "main",
                "force_update": False
            }
        }
    )


class SkillSyncTaskResponse(BaseModel):
    """Response for sync task"""

    id: int = Field(..., description="task id")
    task_id: str = Field(..., description="unique task identifier")
    repo_url: str = Field(..., description="git repository url")
    branch: str = Field(..., description="git branch")
    force_update: bool = Field(..., description="force update flag")
    status: str = Field(..., description="task status: pending, running, completed, failed")
    progress: int = Field(..., description="progress percentage (0-100)")
    current_step: Optional[str] = Field(None, description="current step description")
    total_steps: int = Field(..., description="total number of steps")
    steps_completed: int = Field(..., description="number of steps completed")
    synced_skills_count: int = Field(..., description="number of skills synced")
    skill_codes: List[str] = Field(default_factory=list, description="list of synced skill codes")
    error_msg: Optional[str] = Field(None, description="error message if failed")
    error_details: Optional[str] = Field(None, description="detailed error information")
    start_time: Optional[str] = Field(None, description="task start time (ISO format)")
    end_time: Optional[str] = Field(None, description="task end time (ISO format)")
    gmt_created: str = Field(..., description="creation time (ISO format)")
    gmt_modified: str = Field(..., description="modification time (ISO format)")

    model_config = ConfigDict(
        title=f"SkillSyncTaskResponse for {SERVE_APP_NAME_HUMP}",
        from_attributes=True
    )

    @classmethod
    def from_entity(cls, entity: 'SkillSyncTaskEntity') -> 'SkillSyncTaskResponse':
        """Convert entity to response"""
        skill_codes_list = []
        if entity.skill_codes:
            try:
                import json as json_lib
                skill_codes_list = json_lib.loads(entity.skill_codes)
            except:
                pass

        return cls(
            id=entity.id,
            task_id=entity.task_id,
            repo_url=entity.repo_url,
            branch=entity.branch,
            force_update=entity.force_update,
            status=entity.status,
            progress=entity.progress,
            current_step=entity.current_step,
            total_steps=entity.total_steps,
            steps_completed=entity.steps_completed,
            synced_skills_count=entity.synced_skills_count,
            skill_codes=skill_codes_list,
            error_msg=entity.error_msg,
            error_details=entity.error_details,
            start_time=entity.start_time.isoformat() if entity.start_time else None,
            end_time=entity.end_time.isoformat() if entity.end_time else None,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else "",
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else "",
        )
