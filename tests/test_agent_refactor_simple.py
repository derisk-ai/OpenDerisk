"""
简化版 Agent 重构验证测试脚本

验证内容：
1. AgentInfo 和 Permission 系统功能
2. Execution Loop 基础功能
3. LLM Executor 基础功能
4. 三大 Agent (PDCA, ReActMaster, ReActMaster V2) 的基本构建

使用指定的 DeepSeek-V3 模型配置
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 添加项目路径
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-core/src"))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-ext/src"))
sys.path.insert(0, os.path.join(_project_root, "packages/derisk-app/src"))


class TestResults:
    """测试结果收集器"""

    def __init__(self):
        self.tests: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0

    def add_test(
        self,
        name: str,
        passed: bool,
        error: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        self.tests.append(
            {
                "name": name,
                "passed": passed,
                "error": error,
                "details": details,
                "timestamp": datetime.now().isoformat(),
            }
        )
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def summary(self) -> str:
        total = len(self.tests)
        rate = (self.passed / total * 100) if total > 0 else 0

        lines = [
            "=" * 70,
            "Agent 重构验证测试报告",
            "=" * 70,
            f"总测试数: {total}",
            f"通过: {self.passed}",
            f"失败: {self.failed}",
            f"成功率: {rate:.1f}%",
            "",
            "详细结果:",
            "-" * 70,
        ]

        for test in self.tests:
            status = "✅ PASS" if test["passed"] else "❌ FAIL"
            lines.append(f"{status} - {test['name']}")
            if test["error"]:
                error_preview = (
                    test["error"][:200] + "..."
                    if len(test["error"]) > 200
                    else test["error"]
                )
                lines.append(f"   错误: {error_preview}")

        lines.append("=" * 70)
        return "\n".join(lines)


test_results = TestResults()


def create_llm_client():
    """创建 LLM 客户端，使用 DeepSeek-V3 配置"""
    try:
        from derisk.model.model_config import ModelConfig, ProviderConfig
        from derisk.core import LLMClient

        provider = ProviderConfig(
            provider="openai",
            api_base="https://antchat.alipay.com/v1",
            api_key="fbCTZnIbReh1vVW8oySViGHhrQ8fK2mS",
        )

        model = ModelConfig(name="DeepSeek-V3", temperature=0.7, max_new_tokens=40960)

        from derisk.model import DefaultLLMClient

        llm_client = DefaultLLMClient(
            model_configs=[model], provider_configs=[provider]
        )
        logger.info("✅ LLM 客户端创建成功 (DeepSeek-V3)")
        return llm_client
    except Exception as e:
        logger.warning(f"创建 LLM 客户端失败: {e}")
        return None


async def test_agent_info_and_permission():
    """测试 AgentInfo 和 Permission 系统"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 1: AgentInfo 和 Permission 系统")
    logger.info("=" * 70)

    try:
        from derisk.agent.core.agent_info import (
            AgentInfo,
            AgentMode,
            PermissionAction,
            PermissionRuleset,
            PermissionRule,
            AgentRegistry,
        )

        # 测试 1.1: 创建 PermissionRuleset
        rules = [
            PermissionRule(
                action=PermissionAction.ALLOW, pattern="read", permission="read"
            ),
            PermissionRule(
                action=PermissionAction.ASK, pattern="write", permission="write"
            ),
            PermissionRule(
                action=PermissionAction.DENY, pattern="delete", permission="delete"
            ),
        ]
        ruleset = PermissionRuleset(rules)
        logger.info("✅ PermissionRuleset 创建成功")

        assert ruleset.check("read") == PermissionAction.ALLOW
        assert ruleset.check("write") == PermissionAction.ASK
        assert ruleset.check("delete") == PermissionAction.DENY
        logger.info("✅ Permission 检查验证通过")

        # 测试 1.2: 创建 AgentInfo
        agent_info = AgentInfo(
            name="test_agent",
            description="Test agent for validation",
            mode=AgentMode.PRIMARY,
            permission={"read": "allow", "write": "ask", "delete": "deny"},
            tools={"read": True, "write": True, "delete": False},
        )
        logger.info(f"✅ AgentInfo 创建成功: {agent_info.name}")

        # 测试 1.3: AgentInfo 权限检查
        assert agent_info.check_permission("read") == PermissionAction.ALLOW
        assert agent_info.check_permission("write") == PermissionAction.ASK
        assert agent_info.check_permission("delete") == PermissionAction.DENY
        logger.info("✅ AgentInfo Permission 检查验证通过")

        # 测试 1.4: AgentRegistry
        registry = AgentRegistry.get_instance()
        registry.register(agent_info)
        retrieved = registry.get("test_agent")
        assert retrieved is not None
        assert retrieved.name == "test_agent"
        logger.info("✅ AgentRegistry 验证通过")

        test_results.add_test(
            "AgentInfo 和 Permission 系统",
            True,
            details={"agent_name": agent_info.name, "mode": agent_info.mode.value},
        )
        return True

    except Exception as e:
        logger.error(f"❌ AgentInfo 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("AgentInfo 和 Permission 系统", False, error=str(e))
        return False


async def test_execution_loop():
    """测试执行循环模块"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 2: Execution Loop 模块")
    logger.info("=" * 70)

    try:
        from derisk.agent.core.execution import (
            ExecutionState,
            LoopContext,
            ExecutionMetrics,
            ExecutionContext,
            SimpleExecutionLoop,
            create_execution_context,
            create_execution_loop,
        )

        # 测试 2.1: LoopContext
        ctx = LoopContext(max_iterations=10)
        assert ctx.state == ExecutionState.PENDING
        assert ctx.can_continue() == False  # 还未启动

        ctx.state = ExecutionState.RUNNING
        assert ctx.can_continue() == True
        logger.info("✅ LoopContext 状态转换验证通过")

        # 测试 2.2: ExecutionContext
        exec_ctx = create_execution_context(max_iterations=5)
        loop_ctx = exec_ctx.start()
        assert loop_ctx.state == ExecutionState.RUNNING
        assert loop_ctx.max_iterations == 5
        logger.info("✅ ExecutionContext 启动验证通过")

        # 测试 2.3: SimpleExecutionLoop
        execution_count = [0]

        async def think_func(ctx):
            execution_count[0] += 1
            return {"thought": f"iteration {ctx.iteration}"}

        async def act_func(thought, ctx):
            return {"action": "test", "result": thought}

        async def verify_func(result, ctx):
            if ctx.iteration >= 3:
                ctx.terminate("reached max test iterations")
            return True

        loop = create_execution_loop(max_iterations=5)
        success, metrics = await loop.run(think_func, act_func, verify_func)

        assert execution_count[0] == 3
        logger.info(
            f"✅ SimpleExecutionLoop 执行验证通过 (iterations: {execution_count[0]})"
        )

        test_results.add_test(
            "Execution Loop 模块", True, details={"iterations": execution_count[0]}
        )
        return True

    except Exception as e:
        logger.error(f"❌ Execution Loop 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("Execution Loop 模块", False, error=str(e))
        return False


async def test_llm_executor():
    """测试 LLM 执行器模块"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 3: LLM Executor 模块")
    logger.info("=" * 70)

    try:
        from derisk.agent.core.execution import (
            LLMConfig,
            LLMOutput,
            StreamChunk,
            LLMExecutor,
            create_llm_config,
            create_llm_executor,
        )

        # 测试 3.1: LLMConfig
        config = create_llm_config(
            model="DeepSeek-V3", temperature=0.7, max_tokens=2048
        )
        assert config.model == "DeepSeek-V3"
        assert config.temperature == 0.7
        logger.info("✅ LLMConfig 创建验证通过")

        # 测试 3.2: LLMOutput
        output = LLMOutput(
            content="Test output",
            thinking_content="Test thinking",
            model_name="DeepSeek-V3",
        )
        assert output.content == "Test output"
        assert output.thinking_content == "Test thinking"
        logger.info("✅ LLMOutput 创建验证通过")

        # 测试 3.3: StreamChunk
        chunk = StreamChunk(content_delta="test", is_first=True)
        assert chunk.content_delta == "test"
        assert chunk.is_first == True
        logger.info("✅ StreamChunk 创建验证通过")

        test_results.add_test(
            "LLM Executor 模块", True, details={"model": config.model}
        )
        return True

    except Exception as e:
        logger.error(f"❌ LLM Executor 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("LLM Executor 模块", False, error=str(e))
        return False


async def create_test_context(conv_id: str = "test123"):
    """创建测试上下文"""
    from derisk.agent.core.agent import AgentContext
    from derisk.agent.core.memory.agent_memory import AgentMemory

    context = AgentContext(
        conv_id=conv_id,
        gpts_app_name="代码助手",
        max_new_tokens=2048,
        conv_session_id="123321",
        temperature=0.01,
    )

    agent_memory = AgentMemory()
    try:
        from derisk_ext.vis.gptvis.gpt_vis_converter import GptVisConverter

        await agent_memory.gpts_memory.init(
            conv_id=conv_id, vis_converter=GptVisConverter()
        )
    except Exception as e:
        logger.warning(f"GptVisConverter 不可用，使用默认初始化: {e}")
        await agent_memory.gpts_memory.init(conv_id=conv_id)

    return context, agent_memory


async def test_pdca_agent():
    """测试 PDCA Agent"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 4: PDCA Agent")
    logger.info("=" * 70)

    from derisk.agent.expand.pdca_agent.pdca_agent import PDCAAgent
    from derisk.agent.util.llm.llm import LLMConfig
    from derisk.agent.expand.actions.user_proxy_agent import UserProxyAgent

    conv_id = f"pdca_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        context, agent_memory = await create_test_context(conv_id)
        llm_client = create_llm_client()

        if not llm_client:
            logger.warning("LLM 客户端不可用，跳过测试")
            test_results.add_test("PDCA Agent", False, error="LLM client not available")
            return False

        # 构建 Agent
        coder = (
            await PDCAAgent()
            .bind(context)
            .bind(LLMConfig(llm_client=llm_client))
            .bind(agent_memory)
            .build()
        )
        logger.info("✅ PDCA Agent 构建成功")

        user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
        logger.info("✅ UserProxy Agent 构建成功")

        # 执行对话
        await user_proxy.initiate_chat(
            recipient=coder, reviewer=user_proxy, message="计算下321 * 123等于多少"
        )

        logger.info("✅ PDCA Agent 对话完成")

        test_results.add_test(
            "PDCA Agent", True, details={"conv_id": conv_id, "agent": "PDCAAgent"}
        )
        return True

    except Exception as e:
        logger.error(f"❌ PDCA Agent 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("PDCA Agent", False, error=str(e))
        return False
    finally:
        try:
            from derisk.agent.core.memory.agent_memory import AgentMemory

            AgentMemory().gpts_memory.clear(conv_id)
        except:
            pass


async def test_react_master_agent():
    """测试 ReActMaster Agent"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 5: ReActMaster Agent")
    logger.info("=" * 70)

    from derisk.agent.expand.react_master_agent.react_master_agent import (
        ReActMasterAgent,
    )
    from derisk.agent.util.llm.llm import LLMConfig
    from derisk.agent.expand.actions.user_proxy_agent import UserProxyAgent

    conv_id = f"react_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        context, agent_memory = await create_test_context(conv_id)
        llm_client = create_llm_client()

        if not llm_client:
            logger.warning("LLM 客户端不可用，跳过测试")
            test_results.add_test(
                "ReActMaster Agent", False, error="LLM client not available"
            )
            return False

        # 构建 Agent
        coder = (
            await ReActMasterAgent()
            .bind(context)
            .bind(LLMConfig(llm_client=llm_client))
            .bind(agent_memory)
            .build()
        )
        logger.info("✅ ReActMaster Agent 构建成功")

        user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
        logger.info("✅ UserProxy Agent 构建成功")

        # 执行对话
        await user_proxy.initiate_chat(
            recipient=coder, reviewer=user_proxy, message="计算下321 * 123等于多少"
        )

        logger.info("✅ ReActMaster Agent 对话完成")

        test_results.add_test(
            "ReActMaster Agent",
            True,
            details={"conv_id": conv_id, "agent": "ReActMasterAgent"},
        )
        return True

    except Exception as e:
        logger.error(f"❌ ReActMaster Agent 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("ReActMaster Agent", False, error=str(e))
        return False
    finally:
        try:
            from derisk.agent.core.memory.agent_memory import AgentMemory

            AgentMemory().gpts_memory.clear(conv_id)
        except:
            pass


async def test_react_master_v2_agent():
    """测试 ReActMaster V2 Agent"""
    logger.info("\n" + "=" * 70)
    logger.info("测试 6: ReActMaster V2 Agent")
    logger.info("=" * 70)

    from derisk.agent.expand.react_master_agent.react_master_agent import (
        ReActMasterAgent,
    )
    from derisk.agent.util.llm.llm import LLMConfig
    from derisk.agent.expand.actions.user_proxy_agent import UserProxyAgent

    conv_id = f"react_v2_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        context, agent_memory = await create_test_context(conv_id)
        llm_client = create_llm_client()

        if not llm_client:
            logger.warning("LLM 客户端不可用，跳过测试")
            test_results.add_test(
                "ReActMaster V2 Agent", False, error="LLM client not available"
            )
            return False

        # 构建 Agent
        coder = (
            await ReActMasterAgent()
            .bind(context)
            .bind(LLMConfig(llm_client=llm_client))
            .bind(agent_memory)
            .build()
        )
        logger.info("✅ ReActMaster V2 Agent 构建成功")

        # 验证 Profile 名称
        assert coder.profile.name == "ReActMasterV2", (
            f"Profile name 不匹配: {coder.profile.name}"
        )
        logger.info(f"✅ Profile 名称验证通过: {coder.profile.name}")

        user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
        logger.info("✅ UserProxy Agent 构建成功")

        # 执行对话
        await user_proxy.initiate_chat(
            recipient=coder, reviewer=user_proxy, message="计算下321 * 123等于多少"
        )

        logger.info("✅ ReActMaster V2 Agent 对话完成")

        test_results.add_test(
            "ReActMaster V2 Agent",
            True,
            details={
                "conv_id": conv_id,
                "agent": "ReActMasterAgent",
                "profile_name": coder.profile.name,
            },
        )
        return True

    except Exception as e:
        logger.error(f"❌ ReActMaster V2 Agent 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("ReActMaster V2 Agent", False, error=str(e))
        return False
    finally:
        try:
            from derisk.agent.core.memory.agent_memory import AgentMemory

            AgentMemory().gpts_memory.clear(conv_id)
        except:
            pass


async def main():
    """主测试入口"""
    logger.info("\n" + "=" * 70)
    logger.info("开始 Agent 重构验证测试")
    logger.info("模型配置: DeepSeek-V3 @ https://antchat.alipay.com/v1")
    logger.info("=" * 70)

    # 测试基础设施模块
    await test_agent_info_and_permission()
    await test_execution_loop()
    await test_llm_executor()

    # 测试三大 Agent
    await test_pdca_agent()
    await test_react_master_agent()
    await test_react_master_v2_agent()

    # 打印结果
    print("\n" + test_results.summary())

    return test_results.failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
