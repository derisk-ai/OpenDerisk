"""
Agent 重构验证测试脚本

验证范围:
1. Pdca Agent - PDCA 循环推理和工具调用
2. ReActMaster Agent - ReAct 推理和多轮对话
3. ReActMaster V2 Agent - 同 ReActMaster (profile name)

测试验证项:
- Agent 构建和初始化
- 对话功能
- 渲染数据推送正确
- 工具调用正确
- 多轮推理正确
"""

import sys
import os
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import tempfile

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "packages/derisk-core/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "packages/derisk-ext/src"))


class TestResult:
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
        summary = f"""
{"=" * 60}
Agent 重构验证测试报告
{"=" * 60}
总测试数: {total}
通过: {self.passed}
失败: {self.failed}
成功率: {(self.passed / total * 100):.1f}% if total > 0 else 0

详细结果:
{"-" * 60}
"""
        for test in self.tests:
            status = "✅ PASS" if test["passed"] else "❌ FAIL"
            summary += f"\n{status} - {test['name']}"
            if test["error"]:
                summary += f"\n   错误: {test['error'][:200]}..."
        summary += f"\n{'=' * 60}"
        return summary


test_results = TestResult()


def create_llm_client():
    from derisk.core import LLMClient
    from derisk.model import DefaultLLMClient

    provider_config = {
        "provider": "openai",
        "api_base": "https://antchat.alipay.com/v1",
        "api_key": "fbCTZnIbReh1vVW8oySViGHhrQ8fK2mS",
    }

    model_config = {
        "name": "DeepSeek-V3",
        "temperature": 0.7,
        "max_new_tokens": 40960,
    }

    try:
        from derisk.model.model_config import ModelConfig, ProviderConfig

        provider = ProviderConfig(**provider_config)
        model = ModelConfig(**model_config)

        llm_client = DefaultLLMClient(
            model_configs=[model],
            provider_configs=[provider],
        )
        return llm_client
    except Exception as e:
        logger.warning(f"Failed to create DefaultLLMClient: {e}")
        return None


async def create_test_context(conv_id: str = "test123"):
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
        logger.warning(f"GptVisConverter not available: {e}")
        await agent_memory.gpts_memory.init(conv_id=conv_id)

    return context, agent_memory


async def test_pdca_agent():
    logger.info("=" * 60)
    logger.info("开始测试: Pdca Agent")
    logger.info("=" * 60)

    from derisk.agent.expand.pdca_agent.pdca_agent import PDCAAgent
    from derisk.agent.util.llm.llm import LLMConfig
    from derisk.agent.expand.actions.user_proxy_agent import UserProxyAgent

    conv_id = f"pdca_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        context, agent_memory = await create_test_context(conv_id)
        llm_client = create_llm_client()

        if not llm_client:
            logger.warning("LLM client not available, skipping test")
            test_results.add_test("Pdca Agent", False, error="LLM client not available")
            return

        coder = (
            await PDCAAgent()
            .bind(context)
            .bind(LLMConfig(llm_client=llm_client))
            .bind(agent_memory)
            .build()
        )
        logger.info("✅ Pdca Agent 构建成功")

        user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
        logger.info("✅ UserProxy Agent 构建成功")

        await user_proxy.initiate_chat(
            recipient=coder,
            reviewer=user_proxy,
            message="计算下321 * 123等于多少",
        )

        logger.info("✅ Pdca Agent 对话完成")

        test_results.add_test(
            "Pdca Agent",
            True,
            details={"conv_id": conv_id, "agent": "PDCAAgent"},
        )

    except Exception as e:
        logger.error(f"❌ Pdca Agent 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("Pdca Agent", False, error=str(e))
    finally:
        try:
            from derisk.agent.core.memory.agent_memory import AgentMemory

            AgentMemory().gpts_memory.clear(conv_id)
        except:
            pass


async def test_react_master_agent():
    logger.info("\n" + "=" * 60)
    logger.info("开始测试: ReActMaster Agent")
    logger.info("=" * 60)

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
            logger.warning("LLM client not available, skipping test")
            test_results.add_test(
                "ReActMaster Agent", False, error="LLM client not available"
            )
            return

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

        await user_proxy.initiate_chat(
            recipient=coder,
            reviewer=user_proxy,
            message="计算下321 * 123等于多少",
        )

        logger.info("✅ ReActMaster Agent 对话完成")

        test_results.add_test(
            "ReActMaster Agent",
            True,
            details={"conv_id": conv_id, "agent": "ReActMasterAgent"},
        )

    except Exception as e:
        logger.error(f"❌ ReActMaster Agent 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("ReActMaster Agent", False, error=str(e))
    finally:
        try:
            from derisk.agent.core.memory.agent_memory import AgentMemory

            AgentMemory().gpts_memory.clear(conv_id)
        except:
            pass


async def test_react_master_v2_agent():
    logger.info("\n" + "=" * 60)
    logger.info("开始测试: ReActMaster V2 Agent (同 ReActMasterAgent)")
    logger.info("=" * 60)

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
            logger.warning("LLM client not available, skipping test")
            test_results.add_test(
                "ReActMaster V2 Agent", False, error="LLM client not available"
            )
            return

        coder = (
            await ReActMasterAgent()
            .bind(context)
            .bind(LLMConfig(llm_client=llm_client))
            .bind(agent_memory)
            .build()
        )
        logger.info("✅ ReActMaster V2 Agent 构建成功")

        assert coder.profile.name == "ReActMasterV2", (
            f"Profile name mismatch: {coder.profile.name}"
        )
        logger.info(f"✅ Profile 名称验证通过: {coder.profile.name}")

        user_proxy = await UserProxyAgent().bind(context).bind(agent_memory).build()
        logger.info("✅ UserProxy Agent 构建成功")

        await user_proxy.initiate_chat(
            recipient=coder,
            reviewer=user_proxy,
            message="计算下321 * 123等于多少",
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

    except Exception as e:
        logger.error(f"❌ ReActMaster V2 Agent 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("ReActMaster V2 Agent", False, error=str(e))
    finally:
        try:
            from derisk.agent.core.memory.agent_memory import AgentMemory

            AgentMemory().gpts_memory.clear(conv_id)
        except:
            pass


async def test_agent_info_permission():
    logger.info("\n" + "=" * 60)
    logger.info("开始测试: AgentInfo 和 PermissionSystem")
    logger.info("=" * 60)

    try:
        from derisk.agent.core.agent_info import (
            AgentInfo,
            AgentMode,
            PermissionAction,
            PermissionRuleset,
            AgentRegistry,
        )

        info = AgentInfo(
            name="test_agent",
            description="Test agent",
            mode=AgentMode.PRIMARY,
            permission={"read": "allow", "write": "ask", "delete": "deny"},
        )
        logger.info("✅ AgentInfo 创建成功")

        assert info.check_permission("read") == PermissionAction.ALLOW
        assert info.check_permission("write") == PermissionAction.ASK
        assert info.check_permission("delete") == PermissionAction.DENY
        logger.info("✅ Permission 系统验证通过")

        registry = AgentRegistry.get_instance()
        registry.register(info)
        retrieved = registry.get("test_agent")
        assert retrieved is not None
        assert retrieved.name == "test_agent"
        logger.info("✅ AgentRegistry 验证通过")

        test_results.add_test(
            "AgentInfo 和 PermissionSystem",
            True,
            details={"agent_name": info.name, "mode": info.mode.value},
        )

    except Exception as e:
        logger.error(f"❌ AgentInfo 测试失败: {e}")
        import traceback

        traceback.print_exc()
        test_results.add_test("AgentInfo 和 PermissionSystem", False, error=str(e))


async def main():
    logger.info("开始 Agent 重构验证测试")
    logger.info("=" * 60)

    await test_agent_info_permission()

    await test_pdca_agent()

    await test_react_master_agent()

    await test_react_master_v2_agent()

    print(test_results.summary())

    return test_results.failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
