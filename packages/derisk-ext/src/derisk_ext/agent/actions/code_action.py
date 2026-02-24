"""Code Action Module."""
import datetime
import json
import logging
import time
import uuid
from typing import Optional, List

from derisk.agent import AgentResource, ActionOutput, AgentContext
from derisk.agent.core.schema import ActionInferenceMetrics, Status
from derisk.agent.expand.actions.code_action import CodeAction
from derisk.util.code_utils import UNKNOWN, extract_code_v2, execute_code
from derisk_ext.vis.common.tags.derisk_code import CodeSpace, CodeItem, CodeContent
from derisk_ext.vis.vis_protocol_data import UpdateType

logger = logging.getLogger(__name__)


class DeriskCodeAction(CodeAction):
    """Code Action Module."""

    def __init__(self, **kwargs):
        """Code action init."""
        super().__init__(**kwargs)
        self._code_execution_config = {}
        ## this action out view vis tag name
        self.action_view_tag: str = CodeSpace.vis_tag()

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        self.action_uid = uuid.uuid4().hex
        metrics = ActionInferenceMetrics()
        start_time = datetime.datetime.now()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        agent_context: Optional[AgentContext] = kwargs.get('agent_context', None)
        action_id = kwargs.get("action_id", None)
        try:
            code_blocks, text_info = extract_code_v2(ai_message)
            if len(code_blocks) < 1:
                logger.info(
                    f"No executable code found in answer,{ai_message}",
                )
                return ActionOutput(
                    is_exe_success=False, name=self.name, content="No executable code found in answer."
                )
            elif len(code_blocks) > 1 and code_blocks[0][0] == UNKNOWN:
                # found code blocks, execute code and push "last_n_messages" back
                logger.info(
                    f"Missing available code block type, unable to execute code,"
                    f"{ai_message}",
                )
                return ActionOutput(
                    name=self.name,
                    is_exe_success=False,
                    content="Missing available code block type, "
                            "unable to execute code.",
                )
            code_items: List[CodeItem] = []
            is_success: bool = True
            code_results = {}
            err_msg = {}
            codes = []
            langs = []

            for i, code_block in enumerate(code_blocks):
                lang, code = code_block
                if not lang:
                    continue
                codes.append(lang + ":")
                codes.append(code)
                code_start_stamp = time.time()
                code_start = datetime.datetime.now()
                try:
                    if lang in ["python", "Python"]:
                        exitcode, log, image = execute_code(
                            code,
                            lang="python",
                            filename=None,
                        )
                    else:
                        exitcode = 0
                        log = None
                    run_success = exitcode == 0
                    code_items.append(CodeItem(
                        uid=uuid.uuid4().hex,
                        type=UpdateType.ALL.value,
                        exit_success=run_success,
                        name=None,
                        path=None,
                        language=lang,
                        markdown=code,
                        console=log,
                        env=None,
                        start_time=code_start,
                        cost=int((time.time() - code_start_stamp) * 1000)
                    ))
                    code_results[i] = {
                        "success": run_success,
                        "result": log,

                    }

                except Exception as e:
                    logger.warning(f"{str(e)}")
                    is_success = False
                    err_msg = str(e)

            code_content = CodeContent(
                uid=self.action_uid,
                type=UpdateType.ALL.value,
                name="代码助手",
                items=code_items,
                thought=text_info,
                start_time=start_time,
            )

            if not self.render_protocol:
                raise NotImplementedError("The render_protocol should be implemented.")
            view = await self.render_protocol.display(content=code_content.to_dict())

            metrics.end_time_ms = time.time_ns() // 1_000_000
            metrics.result_tokens = len(str(code_results))
            cost_ms = metrics.end_time_ms - metrics.start_time_ms
            metrics.cost_seconds = round(cost_ms / 1000, 2)
            return ActionOutput(
                action_id=action_id or self.action_uid,
                name=self.name,
                action=f"{';'.join(langs) or 'code'}",
                action_name= f"{';'.join(langs) or 'code'}",
                start_time=start_time,
                metrics=metrics,
                action_input="\n".join(codes),
                is_exe_success=is_success,
                content=json.dumps(code_results, ensure_ascii=False) if is_success else err_msg,
                view=view,
                state=Status.COMPLETE.value,
                observations=json.dumps(code_results, ensure_ascii=False) if is_success else err_msg,
                thoughts=text_info,
            )
        except Exception as e:
            logger.exception("Code Action Run Failed！")
            metrics.end_time_ms = time.time_ns() // 1_000_000
            metrics.result_tokens = 0
            cost_ms = metrics.end_time_ms - metrics.start_time_ms
            metrics.cost_seconds = round(cost_ms / 1000, 2)
            return ActionOutput(
                action_id=self.action_uid,
                name=self.name,
                action=f"DeriskCode",
                action_name=f"代码执行(Derisk)",
                metrics=metrics,
                start_time=start_time,
                state=Status.FAILED.value,
                is_exe_success=False, content="Code execution exception，" + str(e)
            )
