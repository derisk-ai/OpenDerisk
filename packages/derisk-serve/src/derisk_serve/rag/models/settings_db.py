from datetime import datetime
from typing import List, Optional, Dict, Any

from derisk.storage.metadata import Model, BaseDao
from pydantic import BaseModel, Field

from sqlalchemy import Column, DateTime, Integer, String
import logging

logger = logging.getLogger(__name__)


class SettingsEntity(Model):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    setting_key = Column(String(100))
    value = Column(String(1000))
    description = Column(String(100))
    operator = Column(String(100))
    gmt_created = Column(DateTime, name="gmt_create")
    gmt_modified = Column(DateTime)

    def __repr__(self):
        return (
            f"SettingsEntity(id={self.id}, setting_key='{self.setting_key}', "
            f"value='{self.value}', description='{self.description}', operator='{self.operator}', "
            f"gmt_created='{self.gmt_created}', gmt_modified='{self.gmt_modified}')"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "setting_key": self.setting_key,
            "value": self.value,
            "description": self.description,
            "operator": self.operator,
            "gmt_created": self.gmt_created,
            "gmt_modified": self.gmt_modified,
        }

class SettingsRequest(BaseModel):
    """Settings request."""
    id: Optional[int] = Field(None, description="The primary id")
    setting_key: Optional[str] = Field(None, description="The configuration key")
    value: Optional[str] = Field(None, description="The configuration value")
    description: Optional[str] = Field(None, description="The configuration description")


class SettingsResponse(BaseModel):
    id: Optional[int] = Field(None, description="The primary id")
    setting_key: str = Field(..., description="The configuration key")
    value: Optional[str] = Field(None, description="The configuration value")
    description: Optional[str] = Field(None, description="The configuration description")

class SettingsDao(BaseDao):

    def create_settings(self, settings: List, batch_size: Optional[int] = 200):
        session = self.get_raw_session()

        try:
            for i in range(0, len(settings), batch_size):
                batch = settings[i:i + batch_size]

                settings = [
                    SettingsEntity(
                        setting_key=setting.setting_key,
                        value=setting.value,
                        description=setting.description,
                        operator=setting.operator,
                        gmt_created=datetime.now(),
                        gmt_modified=datetime.now(),
                    )
                    for setting in batch
                ]

                # Add current batch to the session
                session.add_all(settings)

                # Commit the current batch
                session.commit()

        except Exception as e:
            # If there is an error, rollback the session
            session.rollback()
            logger.error(f"Error in create_settings: {str(e)}")
            raise

        finally:
            # Always ensure the session is closed
            session.close()


    def get_settings(self, query: SettingsEntity, page=1, page_size=20):
        session = self.get_raw_session()
        settings = session.query(SettingsEntity)
        if query.id is not None:
            settings = settings.filter(SettingsEntity.id == query.id)
        if query.setting_key is not None:
            settings = settings.filter(SettingsEntity.setting_key == query.setting_key)
        if query.value is not None:
            settings = settings.filter(SettingsEntity.value == query.value)
        if query.description is not None:
            settings = settings.filter(SettingsEntity.description == query.description)
        if query.operator is not None:
            settings = settings.filter(SettingsEntity.operator == query.operator)

        settings = settings.order_by(SettingsEntity.id.asc())
        settings = settings.offset((page - 1) * page_size).limit(page_size
        )

        result = settings.all()
        session.close()
        return result


    def update_setting(self, setting: SettingsEntity):
        session = self.get_raw_session()
        try:
            session.query(SettingsEntity).filter(
                SettingsEntity.id == setting.id
            ).update({
                "setting_key": setting.setting_key,
                "value": setting.value,
                "description": setting.description,
                "operator": setting.operator,
                "gmt_modified": datetime.now(),
            })
            session.commit()
        except Exception as e:
            logger.error(f"Error in update_setting: {str(e)}")
            raise
        finally:
            session.close()

    def from_request(self, request: SettingsRequest) -> Dict[str, Any]:
        request_dict = (
            request.dict() if isinstance(request, SettingsRequest) else request
        )
        entity = SettingsEntity(**request_dict)
        return entity

    def to_response(self, entity: SettingsEntity) -> SettingsResponse:
        return SettingsResponse(
            id=entity.id,
            setting_key=entity.setting_key,
            value=entity.value,
            description=entity.description,
        )

    def to_request(self, entity: SettingsEntity) -> SettingsRequest:
        return SettingsRequest(
            id=entity.id,
            setting_key=entity.setting_key,
            value=entity.value,
            description=entity.description,
        )

