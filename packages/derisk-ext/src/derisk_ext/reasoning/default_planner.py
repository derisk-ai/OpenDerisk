import asyncio
import logging
import traceback
from typing import Optional, Dict, List, Type, Tuple, get_origin, get_args, cast

from derisk.agent import LLMStrategyType, LLMConfig
from derisk.core import (
    SystemPromptTemplate,
    HumanPromptTemplate,
    BaseMessage,
    ModelMessage,
)
from derisk.core.interface.reasoning import (
    BasePlanner,
    DeriskPlannerResult,
    DeriskPlannerRequest,
)
from derisk.core import LLMClient, ModelOutput, ModelRequest, ModelRequestContext
from derisk.core.interface.output_parser import BaseOutputParser
from derisk.storage.metadata import BaseModel
from derisk.util.error_types import LLMChatError
from derisk.util.json_utils import find_json_objects
from derisk.util.tracer import root_tracer

logger = logging.getLogger(__name__)


def _build_model_request(input_value: Dict) -> ModelRequest:
    """Build model request from input value.

    Args:
        input_value(str or dict): input value

    Returns:
        ModelRequest: model request, pass to llm client
    """
    parm = {
        "model": input_value.get("model"),
        "messages": input_value.get("messages"),
        "temperature": input_value.get("temperature", None),
        "max_new_tokens": input_value.get("max_new_tokens", None),
        "stop": input_value.get("stop", None),
        "stop_token_ids": input_value.get("stop_token_ids", None),
        "context_len": input_value.get("context_len", None),
        "echo": input_value.get("echo", None),
        "span_id": input_value.get("span_id", None),
    }

    return ModelRequest(**parm)


@BasePlanner.register(name="DefaultPlanner")
class DefaultPlanner(BasePlanner):
    def __init__(
        self, llm_client: LLMClient, output_parser: Optional[BaseOutputParser] = None
    ):
        super().__init__()
        self._llm_client = llm_client
        self._output_parser = output_parser or BaseOutputParser(is_stream_out=False)

    async def _a_select_llm_model(
        self, excluded_models: Optional[List[str]] = None
    ) -> str:
        logger.info(f"_a_select_llm_model:{excluded_models}")
        try:
            all_models = await self.not_null_llm_client.models()
            all_model_names = [item.model for item in all_models]
            # TODO Currently only two strategies, priority and default, are implemented.
            if self.not_null_llm_config.llm_strategy == LLMStrategyType.Priority:
                priority: List[str] = []
                strategy_context = self.not_null_llm_config.strategy_context
                if strategy_context is not None:
                    priority = json.loads(strategy_context)  # type: ignore
                can_uses = self._excluded_models(
                    all_model_names, priority, excluded_models
                )
            else:
                can_uses = self._excluded_models(all_model_names, None, excluded_models)
            if can_uses and len(can_uses) > 0:
                return can_uses[0]
            else:
                raise ValueError("No model service available!")
        except Exception as e:
            logger.error(f"{self.role} get next llm failed!{str(e)}")
            raise ValueError(f"Failed to allocate model service,{str(e)}!")

    async def plan(self, request: DeriskPlannerRequest) -> DeriskPlannerResult:
        # 根据输入参数 生成Planner结果
        if not request or not request.prompt_template or not request.prompt_args:
            raise ValueError("Planner请求参数为空")

        messages: List[BaseMessage] = []
        # 渲染加载Prompt消息
        if "system_prompt_template" in request.prompt_args:
            messages.extend(
                SystemPromptTemplate.from_template(
                    template=request.prompt_args["system_prompt_template"],
                    template_format="jinja2",
                ).format_message(**request.prompt_args)
            )

        # 加载记忆数据(是组织为当前输入还是历史对话消息自行选择)

        # 加载用户消息
        messages.append(
            HumanPromptTemplate.from_template(
                template=request.prompt_template, template_format="jinja2"
            ).format_message(**request.prompt_args)
        )

        ModelMessage.from_base_messages(messages)

        # 调用模型
        return await self.derisk_chat(
            llm_config=request.llm_config,
            messages=messages,
            stream_out=request.stream_out,
        )

    async def derisk_chat(
        self,
        llm_config: LLMConfig,
        messages: list,
        stream_out: bool = False,
        out_cs: Optional[Type] = None,
    ) -> Tuple[DeriskPlannerResult, str]:
        logger.info(f"llm_chat:{llm_config},{stream_out},{messages}")
        last_model = None
        last_err = None
        retry_count = 0
        llm_messages = [message.to_llm_message() for message in messages]
        # LLM inference automatically retries 3 times to reduce interruption
        # probability caused by speed limit and network stability
        while retry_count < 3:
            llm_model = await self._a_select_llm_model(last_model)
            try:
                if not self.llm_client:
                    raise ValueError("LLM client is not initialized!")
                ai_response = self.llm_chat(
                    llm_model=llm_model, params={}, stream_out=stream_out
                )
                out_json_objects = find_json_objects(ai_response)
                json_count = len(out_json_objects)
                if json_count < 1:
                    raise ValueError("Unable to obtain valid output.")
                try:
                    llm_out_plan = DeriskPlannerResult.model_validate(
                        out_json_objects[0]
                    )
                except Exception as e:
                    logger.warning("非预期的返回结构，可能导致规划无法正确执行！")
                    ## TODO 自行优化解决结构问题
                    raise ValueError("请检查你的答案，没有返回要求格式答案.")
                return llm_out_plan, llm_model
            except LLMChatError as e:
                logger.error(f"model:{llm_model} generate Failed!{str(e)}")
                retry_count += 1
                last_model = llm_model
                last_err = str(e)
                await asyncio.sleep(0.5)

        if last_err:
            raise ValueError(last_err)
        else:
            raise ValueError("LLM model inference failed!")

    def _get_span_metadata(self, payload: Dict) -> Dict:
        metadata = {k: v for k, v in payload.items()}

        metadata["messages"] = list(
            map(lambda m: m if isinstance(m, dict) else m.dict(), metadata["messages"])
        )
        return metadata

    async def llm_chat(self, llm_model: str, params, stream_out: bool = False):
        logger.info(f"llm_chat:{llm_model},{params},{stream_out}")
        payload = {
            "model": llm_model,
            "prompt": params.get("prompt"),
            "messages": params.get("messages"),
            "temperature": float(params.get("temperature")),
            "max_new_tokens": int(params.get("max_new_tokens")),
            "echo": False,
        }
        logger.info(f"Request: \n{payload}")
        span = root_tracer.start_span(
            "Agent.llm_client.no_streaming_call",
            metadata=self._get_span_metadata(payload),
        )
        payload["span_id"] = span.span_id
        payload["model_cache_enable"] = False
        if params.get("context") is not None:
            payload["context"] = ModelRequestContext(extra=params["context"])
        try:
            model_request = _build_model_request(payload)
            model_output: Optional[ModelOutput] = None
            async for output in self._llm_client.generate_stream(model_request.copy()):  # type: ignore # noqa
                model_output = output
            if not model_output:
                raise ValueError("LLM generate stream is null!")
            parsed_output = model_output.gen_text_with_thinking()
            parsed_output = parsed_output.strip().replace("\\n", "\n")

            return parsed_output
        except Exception as e:
            logger.error(
                f"Call LLMClient error, {str(e)}, detail: {traceback.format_exc()}"
            )
            raise LLMChatError(original_exception=e) from e
        finally:
            span.end()
