"""Run your code assistant agent in a sandbox environment.

This example demonstrates how to create a code assistant agent that can execute code
in a sandbox environment. The agent can execute Python and JavaScript code blocks
and provide the output to the user. The agent can also check the correctness of the
code execution results and provide feedback to the user.


You can limit the memory and file system resources available to the code execution
environment. The code execution environment is isolated from the host system,
preventing access to the internet and other external resources.

Examples:

    Execute the following command in the terminal:
    Set env params.
    .. code-block:: shell
        export SILICONFLOW_API_KEY=sk-xx
        export SILICONFLOW_API_BASE=URL_ADDRESS:80/v1
    run example.
    ..code-black:: shell
        uv run examples/agents/sandbox_code_agent_example.py

"""

import sys
from unittest.mock import MagicMock
sys.modules["oss2"] = MagicMock()
import asyncio
import logging
import os
from typing import Optional, Tuple

from derisk.agent import (
    Action,
    ActionOutput,
    AgentContext,
    AgentMemory,
    AgentMemoryFragment,
    AgentMessage,
    AgentResource,
    ConversableAgent,
    HybridMemory,
    LLMConfig,
    ProfileConfig,
    UserProxyAgent,
)
from derisk.agent.expand.code_assistant_agent import CHECK_RESULT_SYSTEM_MESSAGE
from derisk.core import ModelMessageRoleType
from derisk.util.code_utils import UNKNOWN, extract_code, infer_lang
from derisk.util.string_utils import str_to_bool
from derisk.util.logger import colored
from derisk.vis import Vis
from derisk_ext.vis.common.tags.vis_code import VisCode

logger = logging.getLogger(__name__)


class SandboxCodeAction(Action[None]):
    """Code Action Module."""

    def __init__(self, **kwargs):
        """Code action init."""
        super().__init__(**kwargs)
        self._render_protocol = VisCode()
        self._code_execution_config = {}

    @property
    def render_protocol(self) -> Optional[Vis]:
        """Return the render protocol."""
        return self._render_protocol

    async def run(
        self,
        ai_message: str,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""
        try:
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
            exitcode, logs = await self.execute_code_blocks(code_blocks)
            exit_success = exitcode == 0

            content = (
                logs
                if exit_success
                else f"exitcode: {exitcode} (execution failed)\n {logs}"
            )

            param = {
                "exit_success": exit_success,
                "language": code_blocks[0][0],
                "code": code_blocks,
                "log": logs,
            }
            if not self.render_protocol:
                raise NotImplementedError("The render_protocol should be implemented.")
            view = await self.render_protocol.display(content=param)
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

    async def execute_code_blocks(self, code_blocks):
        """Execute the code blocks and return the result."""
        # 使用 SandboxManager 来获取沙箱实例并执行代码
        # 注意：这里我们通过 SandboxManager 单例来访问全局配置好的沙箱
        # from derisk.agent.core.sandbox_manager import get_sandbox_manager # 假设有这个helper函数或者通过context获取
        # 由于示例代码中可能没有完全初始化的 SandboxManager，我们这里模拟一个初始化过程，或者直接使用 AutoSandbox
        
        # 更好的方式是使用 SDK 中的 AutoSandbox，但这里为了演示配置使用，我们假设从配置加载
        # 在实际 Agent 运行环境中，SandboxManager 应该已经初始化好了
        
        # 这里为了独立运行示例，我们手动创建一个临时的 AutoSandbox
        from derisk.sandbox.sandbox_client import AutoSandbox
        from derisk_app.config import SandboxConfigParameters
        
        # 模拟从配置文件读取配置
        sandbox_config = SandboxConfigParameters(
            type="local", # 或者 "xic"
            work_dir="./workspace_example",
            user_id="test_user"
        )
        
        # 如果你想使用 xic 配置，可以这样（需要确保你的环境有 xic 相关的实现和凭证）
        # sandbox_config = SandboxConfigParameters(
        #     type="xic",
        #     template_id="xxx",
        #     user_id="user1",
        #     agent_name="derisk",
        #     # ... 其他参数
        # )
        
        # 在这里我们使用 AutoSandbox.create 动态创建，或者如果有全局 SandboxManager 就用全局的
        # 为了简单起见，这里直接实例化一个临时的
        sandbox = await AutoSandbox.create(
            user_id=sandbox_config.user_id or "default_user",
            agent=sandbox_config.agent_name or "derisk_agent",
            type=sandbox_config.type,
            work_dir=sandbox_config.work_dir
        )
        
        logs_all = ""
        exitcode = -1
        
        try:
            # 初始化沙箱（如果是 xic，这步很重要）
            # 注意：AutoSandbox.create 返回的是 SandboxBase 实例
            # 对于某些沙箱类型，可能需要额外的 start() 调用，或者在 execute 时自动处理
            
            for i, code_block in enumerate(code_blocks):
                lang, code = code_block
                if not lang:
                    lang = infer_lang(code)
                print(
                    colored(
                        f"\n>>>>>>>> EXECUTING CODE BLOCK {i} "
                        f"(inferred language is {lang})...",
                        "red",
                    ),
                    flush=True,
                )
                
                # 转换语言名称为沙箱支持的格式
                sandbox_lang = lang.lower()
                if sandbox_lang in ["python", "python3"]:
                    sandbox_lang = "python"
                elif sandbox_lang in ["javascript", "js", "node"]:
                    sandbox_lang = "javascript" # 取决于沙箱支持
                elif sandbox_lang in ["bash", "sh", "shell"]:
                    sandbox_lang = "bash"

                # 执行代码
                # run_code 是高层 API，不同沙箱实现可能略有不同，但通常都支持
                # SandboxBase.run_code 并不直接存在，通常是 sandbox.shell.exec_command 或类似
                # 我们假设 LocalSandbox 或特定实现扩展了这个，或者使用通用的 exec 接口
                
                # 对于 LocalSandbox (derisk_ext), run_code 是存在的
                # 对于通用 SandboxBase, 通常通过 sandbox.shell.run 或 sandbox.exec 来执行
                
                # 这里做个适配
                if hasattr(sandbox, "run_code"):
                     output = await sandbox.run_code(code, language=sandbox_lang)
                else:
                    # Fallback for standard SandboxBase (e.g. XicSandbox) which uses shell client
                    if sandbox_lang == "python":
                         # 这是一个简化，实际可能需要写入文件再运行，或者直接 python -c
                         # 这里假设 exec_command 能处理
                         cmd = f"python3 -c {code!r}"
                    elif sandbox_lang == "bash":
                         cmd = code
                    else:
                         cmd = code # 尝试直接执行
                    
                    # 假设 shell client 有 exec_command
                    if sandbox.shell:
                         result = await sandbox.shell.exec_command(cmd)
                         output = result.output if hasattr(result, "output") else str(result)
                    else:
                         output = "Error: Sandbox shell client not available"

                
                # 处理输出和退出码
                # 简单处理：如果没有抛出异常且输出不包含特定错误标识，认为成功
                # 实际沙箱 API 可能返回更详细的 Result 对象
                
                # 假设 output 是字符串
                logs = output
                # 简单判定成功
                if "Error:" in output or "Exception:" in output:
                     exitcode = 1
                else:
                     exitcode = 0

                logs_all += "\n" + logs
                if exitcode != 0:
                    break
                    
        except Exception as e:
            logger.exception("Sandbox execution failed")
            exitcode = 1
            logs_all += f"\nSandbox execution error: {str(e)}"
        
        return exitcode, logs_all


class SandboxCodeAssistantAgent(ConversableAgent):
    """Code Assistant Agent."""

    profile: ProfileConfig = ProfileConfig(
        name="Turing",
        role="CodeEngineer",
        goal=(
            "Solve tasks using your coding and language skills.\n"
            "In the following cases, suggest python code (in a python coding block) or "
            "javascript for the user to execute.\n"
            "    1. When you need to collect info, use the code to output the info you "
            "need, for example, get the current date/time, check the "
            "operating system. After sufficient info is printed and the task is ready "
            "to be solved based on your language skill, you can solve the task by "
            "yourself.\n"
            "    2. When you need to perform some task with code, use the code to "
            "perform the task and output the result. Finish the task smartly."
        ),
        constraints=[
            "The user cannot provide any other feedback or perform any other "
            "action beyond executing the code you suggest. The user can't modify "
            "your code. So do not suggest incomplete code which requires users to "
            "modify. Don't use a code block if it's not intended to be executed "
            "by the user.Don't ask users to copy and paste results. Instead, "
            "the 'Print' function must be used for output when relevant.",
            "When using code, you must indicate the script type in the code block. "
            "Please don't include multiple code blocks in one response.",
            "If you receive user input that indicates an error in the code "
            "execution, fix the error and output the complete code again. It is "
            "recommended to use the complete code rather than partial code or "
            "code changes. If the error cannot be fixed, or the task is not "
            "resolved even after the code executes successfully, analyze the "
            "problem, revisit your assumptions, gather additional information you "
            "need from historical conversation records, and consider trying a "
            "different approach.",
            "Unless necessary, give priority to solving problems with python code.",
            "The output content of the 'print' function will be passed to other "
            "LLM agents as dependent data. Please control the length of the "
            "output content of the 'print' function. The 'print' function only "
            "outputs part of the key data information that is relied on, "
            "and is as concise as possible.",
            "Your code will by run in a sandbox environment(supporting python and "
            "javascript), which means you can't access the internet or use any "
            "libraries that are not in standard library.",
            "It is prohibited to fabricate non-existent data to achieve goals.",
        ],
        desc=(
            "Can independently write and execute python/shell code to solve various"
            " problems"
        ),
    )

    def __init__(self, **kwargs):
        """Create a new CodeAssistantAgent instance."""
        super().__init__(**kwargs)
        self._init_actions([SandboxCodeAction])

    async def correctness_check(
        self, message: AgentMessage
    ) -> Tuple[bool, Optional[str]]:
        """Verify whether the current execution results meet the target expectations."""
        task_goal = message.current_goal
        action_report = message.action_report
        if not action_report:
            return False, "No execution solution results were checked"
        llm_thinking, check_result, model = await self.thinking(
            messages=[
                AgentMessage(
                    role=ModelMessageRoleType.HUMAN,
                    content="Please understand the following task objectives and "
                    f"results and give your judgment:\n"
                    f"Task goal: {task_goal}\n"
                    f"Execution Result: {action_report.content}",
                )
            ],
            prompt=CHECK_RESULT_SYSTEM_MESSAGE,
        )
        success = str_to_bool(check_result)
        fail_reason = None
        if not success:
            fail_reason = (
                f"Your answer was successfully executed by the agent, but "
                f"the goal cannot be completed yet. Please regenerate based on the "
                f"failure reason:{check_result}"
            )
        return success, fail_reason


async def main():
    from derisk.model.proxy.llms.siliconflow import SiliconFlowLLMClient

    llm_client = SiliconFlowLLMClient(
        model_alias=os.getenv(
            "SILICONFLOW_MODEL_VERSION", "Qwen/Qwen2.5-Coder-32B-Instruct"
        ),
    )
    context: AgentContext = AgentContext(conv_id="test123")

    # TODO Embedding and Rerank model refactor
    from derisk.rag.embedding import OpenAPIEmbeddings

    silicon_embeddings = OpenAPIEmbeddings(
        api_url=os.getenv("SILICONFLOW_API_BASE") + "/embeddings",
        api_key=os.getenv("SILICONFLOW_API_KEY"),
        model_name="BAAI/bge-large-zh-v1.5",
    )
    agent_memory = AgentMemory(
        HybridMemory[AgentMemoryFragment].from_chroma(
            embeddings=silicon_embeddings,
        )
    )
    agent_memory.gpts_memory.init("test123")

    coder = (
        await SandboxCodeAssistantAgent()
        .bind(context)
        .bind(LLMConfig(llm_client=llm_client))
        .bind(agent_memory)
        .build()
    )

    user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()

    # First case: The user asks the agent to calculate 321 * 123
    await user_proxy.initiate_chat(
        recipient=coder,
        reviewer=user_proxy,
        message="计算下321 * 123等于多少",
    )

    await user_proxy.initiate_chat(
        recipient=coder,
        reviewer=user_proxy,
        message="Calculate 100 * 99, must use javascript code block",
    )


if __name__ == "__main__":
    asyncio.run(main())
