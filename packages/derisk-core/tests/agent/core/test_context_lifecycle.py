"""
Tests for Context Lifecycle Management
"""

import pytest
import asyncio

from derisk.agent.core.context_lifecycle import (
    SlotType,
    SlotState,
    EvictionPolicy,
    ContextSlot,
    ContextSlotManager,
    ExitTrigger,
    SkillExitResult,
    SkillManifest,
    SkillLifecycleManager,
    ToolCategory,
    ToolManifest,
    ToolLifecycleManager,
    ContextLifecycleOrchestrator,
    create_context_lifecycle,
)


class TestContextSlot:
    """Tests for ContextSlot"""
    
    def test_slot_creation(self):
        slot = ContextSlot(
            slot_id="test_slot_1",
            slot_type=SlotType.SKILL,
        )
        
        assert slot.slot_id == "test_slot_1"
        assert slot.slot_type == SlotType.SKILL
        assert slot.state == SlotState.EMPTY
        assert slot.priority == 5
        assert slot.sticky == False
    
    def test_slot_touch(self):
        slot = ContextSlot(
            slot_id="test_slot_1",
            slot_type=SlotType.SKILL,
        )
        
        initial_count = slot.access_count
        slot.touch()
        
        assert slot.access_count == initial_count + 1
    
    def test_slot_should_evict(self):
        slot = ContextSlot(
            slot_id="test_slot_1",
            slot_type=SlotType.SKILL,
        )
        
        assert slot.should_evict(EvictionPolicy.LRU) == True
        
        slot.sticky = True
        assert slot.should_evict(EvictionPolicy.LRU) == False
        
        slot.sticky = False
        slot.slot_type = SlotType.SYSTEM
        assert slot.should_evict(EvictionPolicy.LRU) == False


class TestContextSlotManager:
    """Tests for ContextSlotManager"""
    
    @pytest.fixture
    def slot_manager(self):
        return ContextSlotManager(
            max_slots=10,
            token_budget=1000,
        )
    
    @pytest.mark.asyncio
    async def test_allocate_slot(self, slot_manager):
        slot = await slot_manager.allocate(
            slot_type=SlotType.SKILL,
            content="Test content for the slot",
            source_name="test_skill",
        )
        
        assert slot.slot_type == SlotType.SKILL
        assert slot.source_name == "test_skill"
        assert slot.state == SlotState.ACTIVE
        assert slot.token_count > 0
    
    @pytest.mark.asyncio
    async def test_get_slot_by_name(self, slot_manager):
        await slot_manager.allocate(
            slot_type=SlotType.SKILL,
            content="Test content",
            source_name="test_skill",
        )
        
        slot = slot_manager.get_slot_by_name("test_skill")
        
        assert slot is not None
        assert slot.source_name == "test_skill"
    
    @pytest.mark.asyncio
    async def test_evict_slot(self, slot_manager):
        await slot_manager.allocate(
            slot_type=SlotType.SKILL,
            content="Test content",
            source_name="test_skill",
        )
        
        evicted = await slot_manager.evict(source_name="test_skill")
        
        assert evicted is not None
        assert evicted.source_name == "test_skill"
        assert evicted.state == SlotState.EVICTED
        
        slot = slot_manager.get_slot_by_name("test_skill")
        assert slot is None
    
    @pytest.mark.asyncio
    async def test_sticky_slot_cannot_evict(self, slot_manager):
        await slot_manager.allocate(
            slot_type=SlotType.SYSTEM,
            content="System content",
            source_name="system_slot",
            sticky=True,
        )
        
        evicted = await slot_manager.evict(source_name="system_slot")
        
        assert evicted is None
        
        slot = slot_manager.get_slot_by_name("system_slot")
        assert slot is not None
    
    @pytest.mark.asyncio
    async def test_token_budget_enforcement(self):
        slot_manager = ContextSlotManager(
            max_slots=100,
            token_budget=100,
        )
        
        for i in range(5):
            await slot_manager.allocate(
                slot_type=SlotType.SKILL,
                content="x" * 500,
                source_name=f"skill_{i}",
            )
        
        stats = slot_manager.get_statistics()
        assert stats["total_tokens"] <= stats["token_budget"]


class TestSkillLifecycleManager:
    """Tests for SkillLifecycleManager"""
    
    @pytest.fixture
    def managers(self):
        slot_manager = ContextSlotManager(token_budget=10000)
        skill_manager = SkillLifecycleManager(
            context_slot_manager=slot_manager,
            max_active_skills=3,
        )
        return slot_manager, skill_manager
    
    @pytest.mark.asyncio
    async def test_load_skill(self, managers):
        slot_manager, skill_manager = managers
        
        slot = await skill_manager.load_skill(
            skill_name="test_skill",
            skill_content="This is a test skill content",
        )
        
        assert slot is not None
        assert "test_skill" in skill_manager.get_active_skills()
    
    @pytest.mark.asyncio
    async def test_exit_skill(self, managers):
        slot_manager, skill_manager = managers
        
        await skill_manager.load_skill(
            skill_name="test_skill",
            skill_content="This is a test skill content",
        )
        
        result = await skill_manager.exit_skill(
            skill_name="test_skill",
            trigger=ExitTrigger.TASK_COMPLETE,
            summary="Task completed successfully",
            key_outputs=["output1", "output2"],
        )
        
        assert result.skill_name == "test_skill"
        assert result.exit_trigger == ExitTrigger.TASK_COMPLETE
        assert result.tokens_freed >= 0
        assert "test_skill" not in skill_manager.get_active_skills()
    
    @pytest.mark.asyncio
    async def test_max_active_skills(self, managers):
        slot_manager, skill_manager = managers
        
        for i in range(5):
            await skill_manager.load_skill(
                skill_name=f"skill_{i}",
                skill_content=f"Content for skill {i}",
            )
        
        active_skills = skill_manager.get_active_skills()
        assert len(active_skills) <= 3
    
    @pytest.mark.asyncio
    async def test_skill_history(self, managers):
        slot_manager, skill_manager = managers
        
        await skill_manager.load_skill(
            skill_name="test_skill",
            skill_content="Content",
        )
        
        await skill_manager.exit_skill(
            skill_name="test_skill",
            summary="Done",
        )
        
        history = skill_manager.get_skill_history()
        assert len(history) == 1
        assert history[0].skill_name == "test_skill"


class TestToolLifecycleManager:
    """Tests for ToolLifecycleManager"""
    
    @pytest.fixture
    def managers(self):
        slot_manager = ContextSlotManager(token_budget=10000)
        tool_manager = ToolLifecycleManager(
            context_slot_manager=slot_manager,
            max_tool_definitions=10,
        )
        return slot_manager, tool_manager
    
    def test_register_manifest(self, managers):
        slot_manager, tool_manager = managers
        
        manifest = ToolManifest(
            name="test_tool",
            category=ToolCategory.CUSTOM,
            description="A test tool",
        )
        
        tool_manager.register_manifest(manifest)
        
        stats = tool_manager.get_statistics()
        assert stats["total_manifests"] == 1
    
    @pytest.mark.asyncio
    async def test_ensure_tools_loaded(self, managers):
        slot_manager, tool_manager = managers
        
        manifest = ToolManifest(
            name="test_tool",
            category=ToolCategory.CUSTOM,
            description="A test tool",
        )
        tool_manager.register_manifest(manifest)
        
        result = await tool_manager.ensure_tools_loaded(["test_tool"])
        
        assert result["test_tool"] == True
        assert "test_tool" in tool_manager.get_loaded_tools()
    
    @pytest.mark.asyncio
    async def test_unload_tools(self, managers):
        slot_manager, tool_manager = managers
        
        manifest = ToolManifest(
            name="test_tool",
            category=ToolCategory.CUSTOM,
            description="A test tool",
        )
        tool_manager.register_manifest(manifest)
        await tool_manager.ensure_tools_loaded(["test_tool"])
        
        unloaded = await tool_manager.unload_tools(["test_tool"])
        
        assert "test_tool" in unloaded
        assert "test_tool" not in tool_manager.get_loaded_tools()
    
    @pytest.mark.asyncio
    async def test_system_tools_not_unloaded(self, managers):
        slot_manager, tool_manager = managers
        
        manifest = ToolManifest(
            name="system_tool",
            category=ToolCategory.SYSTEM,
            description="A system tool",
            auto_load=True,
        )
        tool_manager.register_manifest(manifest)
        await tool_manager.ensure_tools_loaded(["system_tool"])
        
        unloaded = await tool_manager.unload_tools(["system_tool"])
        
        assert "system_tool" not in unloaded
    
    def test_record_tool_usage(self, managers):
        slot_manager, tool_manager = managers
        
        tool_manager.record_tool_usage("tool_a")
        tool_manager.record_tool_usage("tool_a")
        tool_manager.record_tool_usage("tool_b")
        
        stats = tool_manager.get_tool_usage_stats()
        assert stats["tool_a"] == 2
        assert stats["tool_b"] == 1


class TestContextLifecycleOrchestrator:
    """Tests for ContextLifecycleOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        return ContextLifecycleOrchestrator(
            config=None,
        )
    
    @pytest.mark.asyncio
    async def test_initialize(self, orchestrator):
        await orchestrator.initialize(
            session_id="test_session",
        )
        
        report = orchestrator.get_context_report()
        assert report["session_id"] == "test_session"
        assert report["initialized"] == True
    
    @pytest.mark.asyncio
    async def test_prepare_skill_context(self, orchestrator):
        await orchestrator.initialize(session_id="test_session")
        
        context = await orchestrator.prepare_skill_context(
            skill_name="test_skill",
            skill_content="Skill content here",
            required_tools=["tool1", "tool2"],
        )
        
        assert context.skill_name == "test_skill"
        assert context.skill_slot is not None
        assert "test_skill" in orchestrator.get_active_skills()
    
    @pytest.mark.asyncio
    async def test_complete_skill(self, orchestrator):
        await orchestrator.initialize(session_id="test_session")
        
        await orchestrator.prepare_skill_context(
            skill_name="test_skill",
            skill_content="Skill content",
        )
        
        result = await orchestrator.complete_skill(
            skill_name="test_skill",
            task_summary="Completed task",
            key_outputs=["result1"],
        )
        
        assert result.skill_name == "test_skill"
        assert "test_skill" not in orchestrator.get_active_skills()
    
    @pytest.mark.asyncio
    async def test_handle_context_pressure(self, orchestrator):
        await orchestrator.initialize(session_id="test_session")
        
        for i in range(10):
            await orchestrator.prepare_skill_context(
                skill_name=f"skill_{i}",
                skill_content="x" * 5000,
            )
        
        result = await orchestrator.handle_context_pressure()
        
        assert "pressure_level" in result
        assert "actions_taken" in result


class TestCreateContextLifecycle:
    """Tests for factory function"""
    
    def test_create_context_lifecycle(self):
        orchestrator = create_context_lifecycle(
            token_budget=50000,
            max_active_skills=2,
        )
        
        report = orchestrator.get_context_report()
        assert report["config"]["token_budget"] == 50000
        assert report["config"]["max_active_skills"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])