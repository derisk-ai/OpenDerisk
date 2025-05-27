"""Code Action Module."""

import logging
import re
import traceback
from datetime import datetime
from typing import Optional, Union, List

import tiktoken

from derisk.agent import Action, AgentResource, ActionOutput, AgentMessage, AgentContext
from derisk.agent.util.llm.llm_client import AIWrapper
from derisk.util.code_utils import UNKNOWN, execute_code, extract_code, infer_lang
from derisk.util.utils import colored
from derisk.vis import SystemVisTag

logger = logging.getLogger(__name__)

conclusion = """{answer}

The original code execution output of IPython Kernel is also provided below for reference:

{result}"""


class IpythonAction(Action[None]):
    """Code Action Module."""

    def __init__(self, **kwargs):
        """Code action init."""
        super().__init__(**kwargs)
        self._code_execution_config = {}
        ## this action out view vis tag name
        self.action_view_tag: str = SystemVisTag.VisCode.value
        self.kernel = kwargs.get("kernel")

    async def summary_action(self, llm_client: AIWrapper, model, history: List[AgentMessage], llm_out, action_out: str,
                             agent_context: Optional[AgentContext] = None):
        summary_prompt = """代码执行成功，执行结果如下: 

        {result}

        请根据执行结果，通俗易懂的，概括出一个直截了当的答案。."""

        llm_messages = [message.to_llm_message() for message in history]
        llm_messages.extend([
            {
                "content": llm_out,
                "role": "assistant",
            },
            {
                "content": summary_prompt.format(result=action_out),
                "role": "user",
            }
        ])
        prev_thinking = ""
        prev_content = ""
        try:
            async for output in llm_client.create(
                    context=None,
                    messages=llm_messages,
                    llm_model=model,
                    max_new_tokens=agent_context.max_new_tokens,
                    temperature=agent_context.temperature,
            ):
                prev_thinking, prev_content = output
            return prev_thinking, prev_content
        except Exception as e:
            logger.warning("python result summary exception!", e)
            return action_out, action_out

    async def run(
            self,
            ai_message: str = None,
            resource: Optional[AgentResource] = None,
            rely_action_out: Optional[ActionOutput] = None,
            need_vis_render: bool = True,
            **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        try:
            llm_client = kwargs.get("llm_client")
            agent_context = kwargs.get("agent_context")
            llm_model = kwargs.get("llm_model")
            agent_history = kwargs.get("history")
            t1 = datetime.now()
            tokenizer = tiktoken.encoding_for_model(kwargs.get("model", "gpt-4"))
            code_blocks = extract_code(ai_message)
            if len(code_blocks) < 1:
                logger.info(
                    f"No executable code found in answer,{ai_message}",
                )
                return ActionOutput(
                    is_exe_success=False, content="No executable code found in answer."
                )
            elif len(code_blocks) > 1 and code_blocks[0][0] == UNKNOWN:
                # found code blocks, execute code and push "last_n_messages" back
                logger.info(
                    f"Missing available code block type, unable to execute code,"
                    f"{ai_message}",
                )
                return ActionOutput(
                    is_exe_success=False,
                    content="Missing available code block type, "
                            "unable to execute code.",
                )
            if "import matplotlib" in code_blocks[0][1] or "import seaborn" in code_blocks[0][1]:
                logger.warning("The generated visualization code detected.")
                return ActionOutput(
                    is_exe_success=False,
                    content="You are not permitted to generate visualizations. If the instruction requires visualization, please provide the text-based results.",
                )

            exec = self.kernel.run_cell(code_blocks[0][1])
            status = exec.success
            if status:
                result = str(exec.result).strip()
                tokens_len = len(tokenizer.encode(result))
                if tokens_len > 16384:
                    logger.warning(f"Token length exceeds the limit: {tokens_len}")
                t2 = datetime.now()
                row_pattern = r"\[(\d+)\s+rows\s+x\s+\d+\s+columns\]"
                match = re.search(row_pattern, result)
                if match:
                    rows = int(match.group(1))
                    if rows > 10:
                        result += f"\n\n**Note**: The printed pandas DataFrame is truncated due to its size. Only **10 rows** are displayed, which may introduce observation bias due to the incomplete table. If you want to comprehensively understand the details without bias, please ask Executor using `df.head(X)` to display more rows."
                logger.debug(f"Execution Result:\n{result}")
                logger.debug(f"Execution finished. Time cost: {t2 - t1}")

                # answer = self.summary_action(llm_client, llm_model, agent_history, code_blocks[0][1], result,
                #                                    agent_context=agent_context)
                # logger.debug(f"Brief Answer:\n{answer}")
                content = conclusion.format(answer="", result=result)
                exit_success = True

            else:
                if exec.error_in_exec:
                    result = ''.join(traceback.format_exception(type(exec.error_in_exec), exec.error_in_exec,
                                                            exec.error_in_exec.__traceback__ ))
                elif exec.error_before_exec:
                    result = ''.join(traceback.format_exception(type(exec.error_before_exec), exec.error_before_exec,
                                                                exec.error_before_exec.__traceback__))
                else:
                    result = "代码执行失败，未知异常！"

                t2 = datetime.now()
                logger.warning(f"Execution failed. Error message: {result}")
                logger.debug(f"Execution finished. Time cost: {t2 - t1}")
                exit_success = False
                content = f"Execution failed:\n{result}\nPlease revise your code and retry."
            view = await self.render_protocol.display(content={
                "exit_success": True,
                "language": code_blocks[0][0],
                "code": code_blocks,
                "log": result,
            })
            return ActionOutput(
                is_exe_success=exit_success,
                content=content,
                view=view,
                thoughts=ai_message,
                observations=content,
            )
        except Exception as e:
            logger.exception("Code Action Run Failed！")
            return ActionOutput(
                is_exe_success=False, content="Code execution exception，" + str(e)
            )
