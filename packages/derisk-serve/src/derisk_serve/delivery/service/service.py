"""Delivery service — dispatch to channel handlers."""
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import DeliveryListFilter, DeliveryRequest, DeliveryResponse
from ..config import ServeConfig
from ..models.models import DeliveryDao, DeliveryEntity

DELIVERY_SERVICE_COMPONENT_NAME = "serve_delivery_service"
logger = logging.getLogger(__name__)


class DeliveryService(BaseService[DeliveryEntity, DeliveryRequest, DeliveryResponse]):
    name = DELIVERY_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig,
        dao: Optional[DeliveryDao] = None,
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: DeliveryDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        super().init_app(system_app)
        self._dao = self._dao or DeliveryDao()
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao:
        return self._dao

    @property
    def config(self) -> ServeConfig:
        return self._serve_config

    def create(self, request: DeliveryRequest) -> DeliveryResponse:
        response = self._dao.create(request)
        return response

    def send(self, delivery_id: int) -> DeliveryResponse:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(DeliveryEntity).filter(
                DeliveryEntity.id == delivery_id
            ).first()
            if not entity:
                raise ValueError(f"delivery {delivery_id} not found")
            result: dict = {}
            try:
                if entity.channel == "email":
                    result = self._send_email(entity)
                elif entity.channel == "in_app":
                    result = {"delivered": True, "channel": "in_app"}
                elif entity.channel == "feishu":
                    result = {"delivered": True, "channel": "feishu", "note": "feishu handler not wired in MVP"}
                else:
                    raise ValueError(f"unsupported channel: {entity.channel}")
                entity.status = "sent"
                entity.sent_at = datetime.now()
                entity.result_json = json.dumps(result, ensure_ascii=False)
            except Exception as e:
                entity.status = "failed"
                entity.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
                logger.exception("delivery send failed")
            session.commit()
            return self._dao.to_response(entity)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _send_email(self, entity: DeliveryEntity) -> dict:
        cfg = self._serve_config
        if not cfg.smtp_host or not cfg.smtp_from:
            return {"delivered": False, "reason": "smtp not configured"}
        msg = MIMEMultipart("alternative")
        msg["From"] = cfg.smtp_from
        msg["To"] = entity.target
        msg["Subject"] = entity.title or "Derisk Delivery"
        msg.attach(MIMEText(entity.message or "", "html", "utf-8"))
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port or 587) as server:
            if cfg.smtp_user and cfg.smtp_password:
                server.login(cfg.smtp_user, cfg.smtp_password)
            server.sendmail(cfg.smtp_from, [entity.target], msg.as_string())
        return {"delivered": True, "channel": "email", "to": entity.target}

    def list_deliveries(self, f: DeliveryListFilter) -> List[DeliveryResponse]:
        return self._dao.list_by_filter(f)

    def get_by_id(self, delivery_id: int) -> Optional[DeliveryResponse]:
        session = self._dao.get_raw_session()
        try:
            entity = session.query(DeliveryEntity).filter(
                DeliveryEntity.id == delivery_id
            ).first()
            return self._dao.to_response(entity) if entity else None
        finally:
            session.close()
