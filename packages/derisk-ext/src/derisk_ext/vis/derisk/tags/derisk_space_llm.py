import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union

from pydantic_core._pydantic_core import ValidationError
from derisk._private.pydantic import (
    Field,
    BaseModel,
    model_to_json,
    model_validator,
    model_to_dict,
)
from typing import Optional

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase


logger = logging.getLogger(__name__)


class LLMSpaceContent(DrskVisBase):
    markdown: Optional[str] = Field(None, description="llm space content")
    token_use: Optional[int] = Field(0, description="token use count")
    total_tokens: Optional[int] = Field(0, description="total token count")
    token_speed: Optional[float] = Field(0, description="token output speed")
    llm_model: Optional[str] = Field(None, description="llm model name")
    llm_avatar: Optional[str] = Field(None, description="llm avatar")
    start_time: Optional[Any] = Field(None, description="模型推理开始时间")
    firt_out_time: Optional[datetime] = Field(None, description="模型首token时间")
    cost: Optional[int] = Field(None, description="模型推理耗时")
    link_url: Optional[str] = Field(None, description="输入输出弹出框连接")

    say_to_user: Optional[str] = Field(None, description="输出给用户的展示消息")
    status: Optional[str] = Field(None, description="模型消息输出状态")


class LLMSpace(Vis):
    """WorkSpace."""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the vis protocol.

        Display corresponding content using vis protocol

        Args:
            **kwargs:

        Returns:
        vis protocol text
        """
        content = kwargs["content"]
        try:
            LLMSpaceContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"LLMSpace可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-llm"
