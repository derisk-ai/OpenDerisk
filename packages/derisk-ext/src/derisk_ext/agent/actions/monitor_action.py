import datetime
import json
import logging
import time
from typing import Optional, Any, Dict, Tuple, List

from mcp.types import CallToolResult, ImageContent, TextContent, Resource
from orjson import orjson

from derisk.agent.core.schema import Status
from derisk.agent.expand.actions.tool_action import ToolInput, ToolAction, EVAL_MODE_KEY, TOOL_RUN_MODE_KEY
from derisk.agent.resource import BaseTool, ToolPack
from derisk_ext.vis.common.tags.derisk_monitor import MonitorSpace, MonitorSpaceContent
from derisk_serve.agent.resource.tool.mcp import MCPToolPack

logger = logging.getLogger(__name__)


class FileInfo:
    """
    文件信息描述类。

    字段说明：
    - file_full_name: str
        OSS上文件的完整路径。例如："derisk/2816ebhcsd21csacc/db.xlsx"
    - file_type: str
        文件类型（扩展名），如"csv"、"xlsx"、"txt"、"jpg"等
    - structure: str
        文件结构信息。例如csv的列名、excel的sheet结构、图片为"image"等
    - sample_data: str
        文件的示例数据。例如csv的首行数据、excel的首行数据、图片格式等
    - file_desc: str
        文件的描述信息，选填
    - file_path: str
        文件的路径述信息,文件oss地址或者文件下载地址，选填
    - meta: dict
        文件的扩展元数据，选填，可以存储任意键值对信息

    示例：
        # Excel 文件
        FileInfo(
            file_full_name="derisk/2816ebhcsd21csacc/db.xlsx",
            file_type="xlsx",
            structure="[{\"sheet\": \"Sheet1\", \"columns\": [\"A\", \"B\"]}]",
            sample_data="{'Sheet1': {'A': 1, 'B': 2}}",
            file_desc="示例Excel文件",
            meta={"creator": "张三", "create_time": "2024-03-20"}
        )
        # CSV 文件
        FileInfo(
            file_full_name="derisk/2816ebhcsd21csacc/data.csv",
            file_type="csv",
            structure="{'columns': ['name', 'age', 'score']}",
            sample_data="{'name': '张三', 'age': 18, 'score': 99}",
            file_desc="示例CSV文件",
            meta={"department": "技术部", "tags": ["示例", "测试"]}
        )
        # TXT 文件
        FileInfo(
            file_full_name="derisk/2816ebhcsd21csacc/readme.txt",
            file_type="txt",
            structure="text",
            sample_data="这是第一行内容...内容长度超过限制，已截止",
            file_desc="示例TXT文件",
            meta={"version": "1.0", "status": "draft"}
        )
        # PNG 图片
        FileInfo(
            file_full_name="derisk/2816ebhcsd21csacc/image.png",
            file_type="png",
            structure="image",
            sample_data="PNG",
            file_desc="示例PNG图片",
            meta={"width": 800, "height": 600, "format": "PNG"}
        )
    """

    def __init__(self, file_full_name: str, file_type, structure: str = "", sample_data: str = "", file_desc: str = "",
                 meta: dict = None, file_path: Optional[str] = None):
        """
        :param file_full_name: oss上文件完整路径，必填，例如"derisk/2816ebhcsd21csacc/db.xlsx"
        :param file_type: 文件类型，必填，默认"unknown"
        :param structure: 文件结构信息，选填
        :param sample_data: 文件示例数据，txt、表格要填上，超出1000字符自动截断
        :param file_desc: 文件描述，选填
        :param meta: 文件扩展元数据，选填，可以存储任意键值对信息
        """
        self.file_full_name = file_full_name
        self.file_full_name = file_full_name
        self.file_type = file_type
        self.structure = structure
        self.sample_data = sample_data if sample_data else ""
        self.file_desc = file_desc
        self.file_path = file_path
        self.meta = meta or {}

    def to_dict(self):
        result = {}
        if self.file_full_name:
            result["file_full_name"] = self.file_full_name
        if self.file_type:
            result["file_type"] = self.file_type
        if self.structure:
            result["structure"] = self.structure
        if self.sample_data:
            result["sample_data"] = self.sample_data
        if self.file_desc:
            result["file_desc"] = self.file_desc
        if self.file_path:
            result["file_path"] = self.file_path
        if self.meta:
            result["meta"] = self.meta
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileInfo':
        """从字典创建 FileInfo 对象"""
        return cls(
            file_full_name=data.get("file_full_name", ""),
            file_type=data.get("file_type", ""),
            structure=data.get("structure", ""),
            sample_data=data.get("sample_data", ""),
            file_desc=data.get("file_desc", ""),
            file_path=data.get("file_path", ""),
            meta=data.get("meta", {})
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'FileInfo':
        """从 JSON 字符串创建 FileInfo 对象"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def __repr__(self):
        return f"FileInfo({self.to_dict()})"

    def __str__(self):
        return self.__repr__()


class MonitorAction(ToolAction):
    """Tool action class."""
    name = "Monitor"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_view_tag: str = MonitorSpace.vis_tag()
        self.web_url = kwargs.get("derisk_url", "")

    @staticmethod
    def get_file(mcp_result: CallToolResult) -> Optional[FileInfo]:

        for item in mcp_result.content:
            if isinstance(item, ImageContent) and item.mimeType == "oss_file":
                return FileInfo.from_json(item.data)
        return None

    async def gen_view(self, message_id, tool_call_id, tool_info: BaseTool, status,
                       tool_pack: Optional[ToolPack] = None,
                       args: Optional[Any] = None,
                       out_type: Optional[str] = "json",
                       tool_result: Optional[Any] = None, err_msg: Optional[str] = None, tool_cost: float = 0,
                       start_time: Optional[Any] = None, **kwargs):
        try:
            # 安全地提取工具信息
            tool_attrs = {
                'name': getattr(tool_info, 'name', 'Unknown'),
                'description': getattr(tool_info, 'description', ''),
                'version': getattr(tool_info, 'version', 'v0.1'),
                'author': getattr(tool_info, 'author', 'Unknown'),
            }

            data_content = tool_result
            if status == Status.FAILED.value:
                logger.info("监控Action执行失败，处理失败信息")
                try:
                    data_content = orjson.loads(tool_result)
                except Exception as e:
                    logger.warning("返回内容不支持json转换，默认makrdown展示")
                    out_type = "markdown"
            else:
                mcp_result = None
                if tool_result:
                    try:
                        if isinstance(tool_result, CallToolResult):
                            mcp_result = tool_result
                        else:
                            data_content = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                            mcp_result = CallToolResult.validate(data_content)
                    except Exception as e:
                        logger.warning("非MCP返回对象!")
                out_type = "json"
                if mcp_result:
                    file = self.get_file(mcp_result)
                    if file:
                        out_type = "file"
                        file_path = file.file_path
                        if not file_path:
                            file_path = f"{self.web_url}/api/oss/getFileByFileName?fileName={file.file_full_name}"
                            data_content = file_path
                    else:
                        try:
                            data_content = orjson.loads(mcp_result.content[0].text)
                        except Exception as e:
                            logger.warning(f"Monitor Tool return is not json!tool={tool_info.name}, {str(e)}")
                            data_content = mcp_result.content[0].text

            data_source = {
                "tool_args": args or {},
                "status": status,
                "tool_name": tool_attrs['name'],
                "tool_desc": tool_attrs['description'],
                "tool_version": tool_attrs['version'],
                "tool_author": tool_attrs['author'],
                "run_env": None,
                "tool_cost": tool_cost,
                "start_time": start_time,
                "out_type": out_type,
                "data": data_content,
                "group_colums": [],
                "time_colum": "period",
            }
            # 创建监控内容
            drsk_content = MonitorSpaceContent(
                uid=tool_call_id,
                type="all",
                **data_source
            )
            if self.render_protocol:
                return self.render_protocol.sync_display(
                    content=drsk_content.to_dict()
                )
            else:
                logger.info("监控工具结果渲染,降级到工具渲染！")
                # 降级到工具渲染
                return await ToolAction.gen_view(self, message_id=message_id, tool_call_id=tool_call_id,
                                              tool_pack=tool_pack, tool_info=tool_info, status=status, args=args,
                                              out_type=out_type, tool_result=tool_result, err_msg=err_msg,
                                              tool_cost=tool_cost, start_time=start_time, **kwargs)
        except Exception as e:
            logger.exception("Monitor Tool Result View Failed!")
            # 错误处理
            error_content = MonitorSpaceContent(
                type="all",
                uid=tool_call_id,
                title=tool_info.name,
                status="error",
                err_msg=f"Failed to generate monitor view: {str(e)}"
            )
            if self.render_protocol:
                return self.render_protocol.sync_display(
                    content=error_content.to_dict()
                )
            else:
                logger.warning("Monitor Action View异常，也降级到Tool展示！")
                return await ToolAction.gen_view(self, message_id=message_id,
                                        tool_call_id=tool_call_id,
                                              tool_pack=tool_pack, tool_info=tool_info, status=status, args=args,
                                              out_type=out_type, tool_result=tool_result, err_msg=err_msg,
                                              tool_cost=tool_cost, start_time=start_time, **kwargs)
