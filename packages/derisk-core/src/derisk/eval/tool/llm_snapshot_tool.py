from typing import Dict, Any, Optional, Tuple

import logging
from derisk.agent.resource import BaseTool
from derisk.core import LLMClient, ModelMessage, ModelRequest
from derisk.eval.tool.eval_tool import EvalToolExecutor, EvalToolOutput
from pydantic import Field

from derisk._private.pydantic import BaseModel
from derisk.util.json_utils import find_json_objects
import requests

logger = logging.getLogger(__name__)

DEFAULT_LLM_PROMPT = """
# 角色定义
你是一个工具执行助手，针对同一个工具，你已经根据不同的工具入参准备了对应的工具结果。你需要从准备好的工具入参列表中挑选出与实际工具入参最匹配的一个参数，如果都不匹配则输出无。 

# 注意
1. 起始时间匹配：工具入参中如果包含起始时间信息，在其他参数相同的情况下，时间重叠度最高的参数是更优的。如果不存在起始时间重叠的参数，则认为无匹配参数
2. 如果工具描述信息中没有入参，则任意匹配一个即可


# 工具描述信息
{tool_prompt}

# 实际工具入参
{tool_args}

# 准备好的工具入参列表
{tool_snapshot_args}


# 输出要求
严格按以下JSON格式输出，确保可直接解析:
{{
  "reason":"简短解释选择原因",
  "index": "整数"，最终挑选的工具入参在入参列表中的序号，范围为1~列表长度。如果都不匹配，则输出-1
}}

"""


class ToolSnapshot(BaseModel):
    tool_type: Optional[str] = Field(default=None, alias="toolType")
    tool_name: str = Field(description="工具名称", alias="toolName")
    tool_args: Optional[Any] = Field(default=None, alias="toolArgs")
    tool_result_type: str = Field("OSS", description="OSS文件地址", alias="toolResultType")
    tool_result: str = Field(description="OSS文件地址", alias="toolResult")
    tool_error_msg: Optional[str] = Field(default=None, alias="toolErrorMsg")


class LLMSnapshotTool(EvalToolExecutor):

    def __init__(self,
                 tool_info: BaseTool,
                 tool_snapshots: list[ToolSnapshot],
                 llm_client: LLMClient,
                 model_name: str = "ss",
                 llm_prompt: str = DEFAULT_LLM_PROMPT,
                 **kwargs):
        self._llm_client = llm_client
        self._tool_snapshots: list[ToolSnapshot] = tool_snapshots
        self._model_name = model_name
        self._llm_prompt = llm_prompt
        super().__init__(tool_info=tool_info, **kwargs)

    async def run_tool(self, args: Dict[str, Any], **kwargs) -> EvalToolOutput:
        try:
            tool_snapshot, reason = await self.select_tool_snapshot(args)
            if not tool_snapshot:
                return EvalToolOutput(
                    is_exe_success=False,
                    reason=reason
                )
            if tool_snapshot.tool_result_type == "OSS":
                response = requests.get(tool_snapshot.tool_result, verify=False, allow_redirects=True)
                if response.status_code == 200:
                    result_content = response.content.decode('utf-8') if response.content else None
                else:
                    raise ValueError("获取oss结果失败,status_code:" + response.status_code)
            else:
                result_content = tool_snapshot.tool_result

            return EvalToolOutput(
                    is_exe_success=True,
                    content=result_content,
                    snapshot_params=tool_snapshot.tool_args,
                    reason=reason
                )
        except Exception as e:
            logger.error(f"Error select tool snapshot: {str(e)}")
            return EvalToolOutput(
                is_exe_success = False,
                error_msg=str(e),
            )


    async def select_tool_snapshot(self, args) -> Tuple[Optional[ToolSnapshot], str]:
        tool_prompt = await self.tool_info.get_prompt(lang="zh")
        tool_snapshot_args = [tool_snapshot.tool_args for tool_snapshot in self._tool_snapshots]
        prompt = self._llm_prompt.format(
            tool_prompt= tool_prompt,
            tool_args = args,
            tool_snapshot_args = tool_snapshot_args
        )
        messages = [ModelMessage.build_human_message(prompt)]
        request = ModelRequest(model=self._model_name, messages=messages)
        response = await self._llm_client.generate(request=request)

        if not response.success:
            code = str(response.error_code)
            error_msg = f"eval tool request llm failed ({code}) {response.text}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        json_parsed = find_json_objects(response.text)
        if isinstance(json_parsed, list) and len(json_parsed) >= 1:
            json_parsed = json_parsed[0]
        else:
            error_msg = f"eval tool request llm format error:  {response.text}"
            raise RuntimeError(error_msg)

        index: int = int(json_parsed["index"])
        reason: str = json_parsed["reason"]
        if index == -1:
            return None, reason
        return self._tool_snapshots[index-1], reason
