"""Skill Sync Task Model

Manages async git sync tasks for skills.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    update as sql_update,
)

from derisk.storage.metadata import BaseDao, Model, db

from derisk._private.pydantic import BaseModel


class SkillSyncTaskEntity(Model):
    """Async skill git sync task entity"""

    __tablename__ = "skill_sync_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), unique=True, nullable=False, comment="unique task identifier")

    # Task parameters
    repo_url = Column(String(500), nullable=False, comment="git repository url")
    branch = Column(String(100), nullable=False, comment="git branch")
    force_update = Column(Boolean, default=False, comment="force update existing skills")

    # Task status
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        comment="task status: pending, running, completed, failed",
    )
    progress = Column(Integer, default=0, comment="progress percentage (0-100)")
    current_step = Column(String(200), comment="current step description")
    total_steps = Column(Integer, default=0, comment="total number of steps")
    steps_completed = Column(Integer, default=0, comment="number of steps completed")

    # Results
    synced_skills_count = Column(Integer, default=0, comment="number of skills synced")
    skill_codes = Column(Text, comment="JSON list of synced skill codes")

    # Error handling
    error_msg = Column(Text, comment="error message if failed")
    error_details = Column(Text, comment="detailed error information")

    # Timestamps
    start_time = Column(DateTime, comment="task start time")
    end_time = Column(DateTime, comment="task end time")
    gmt_created = Column(DateTime, name="gmt_create", default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return (
            f"SkillSyncTaskEntity(id={self.id}, task_id='{self.task_id}', "
            f"status='{self.status}', progress={self.progress})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary."""
        skill_codes_list = []
        if self.skill_codes:
            try:
                skill_codes_list = json.loads(self.skill_codes)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "id": self.id,
            "task_id": self.task_id,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "force_update": self.force_update,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "steps_completed": self.steps_completed,
            "synced_skills_count": self.synced_skills_count,
            "skill_codes": skill_codes_list,
            "error_msg": self.error_msg,
            "error_details": self.error_details,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "gmt_created": self.gmt_created.isoformat() if self.gmt_created else None,
            "gmt_modified": self.gmt_modified.isoformat() if self.gmt_modified else None,
        }


class SkillSyncTaskDao(BaseDao[SkillSyncTaskEntity, BaseModel, BaseModel]):
    """DAO for skill sync tasks"""

    def create_task(
        self,
        task_id: str,
        repo_url: str,
        branch: str,
        force_update: bool = False,
    ) -> SkillSyncTaskEntity:
        """Create a new sync task"""
        entity = SkillSyncTaskEntity(
            task_id=task_id,
            repo_url=repo_url,
            branch=branch,
            force_update=force_update,
            status="pending",
            progress=0,
            start_time=datetime.now(),
        )
        session = self.get_raw_session()
        try:
            session.add(entity)
            session.commit()
            session.refresh(entity)
            return entity
        finally:
            session.close()

    def get_task_by_id(self, task_id: str) -> Optional[SkillSyncTaskEntity]:
        """Get task by task_id"""
        session = self.get_raw_session()
        try:
            return session.query(SkillSyncTaskEntity).filter(
                SkillSyncTaskEntity.task_id == task_id
            ).first()
        finally:
            session.close()

    def update_task_status(
        self,
        task_id: str,
        status: str,
        progress: Optional[int] = None,
        current_step: Optional[str] = None,
        steps_completed: Optional[int] = None,
        error_msg: Optional[str] = None,
        error_details: Optional[str] = None,
    ) -> bool:
        """Update task status"""
        session = self.get_raw_session()
        try:
            updates = {"status": status}
            if progress is not None:
                updates["progress"] = progress
            if current_step is not None:
                updates["current_step"] = current_step
            if steps_completed is not None:
                updates["steps_completed"] = steps_completed
            if error_msg is not None:
                updates["error_msg"] = error_msg
            if error_details is not None:
                updates["error_details"] = error_details

            # Add end_time if task is completed or failed
            if status in ["completed", "failed"]:
                updates["end_time"] = datetime.now()

            result = session.query(SkillSyncTaskEntity).filter(
                SkillSyncTaskEntity.task_id == task_id
            ).update(updates)
            session.commit()
            session.flush()
            return result > 0
        finally:
            session.close()

    def update_task_init_steps(self, task_id: str, total_steps: int, current_step: str = ""):
        """Initialize task steps"""
        session = self.get_raw_session()
        try:
            result = session.query(SkillSyncTaskEntity).filter(
                SkillSyncTaskEntity.task_id == task_id
            ).update(
                {
                    "total_steps": total_steps,
                    "current_step": current_step,
                    "steps_completed": 0,
                }
            )
            session.commit()
            return result > 0
        finally:
            session.close()

    def increment_progress(self, task_id: str, current_step: str = ""):
        """Increment task progress"""
        session = self.get_raw_session()
        try:
            task = session.query(SkillSyncTaskEntity).filter(
                SkillSyncTaskEntity.task_id == task_id
            ).first()
            if task:
                new_progress = min(100, int((task.steps_completed / task.total_steps) * 100)) if task.total_steps > 0 else 0
                task.current_step = current_step
                task.steps_completed = task.steps_completed + 1
                task.progress = new_progress
                session.commit()
                return True
            return False
        finally:
            session.close()

    def update_synced_skills(self, task_id: str, skill_codes: List[str]):
        """Update synced skills list"""
        session = self.get_raw_session()
        try:
            skill_codes_json = json.dumps(skill_codes)
            result = session.query(SkillSyncTaskEntity).filter(
                SkillSyncTaskEntity.task_id == task_id
            ).update({"synced_skills_count": len(skill_codes), "skill_codes": skill_codes_json})
            session.commit()
            return result > 0
        finally:
            session.close()

    def get_recent_tasks(
        self,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> List[SkillSyncTaskEntity]:
        """Get recent tasks"""
        session = self.get_raw_session()
        try:
            query = session.query(SkillSyncTaskEntity)
            if status:
                query = query.filter(SkillSyncTaskEntity.status == status)
            return query.order_by(SkillSyncTaskEntity.gmt_created.desc()).limit(limit).all()
        finally:
            session.close()


# Tables will be created by serve.py's before_start() method
# db.create_all()