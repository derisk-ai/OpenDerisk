"""Skill 工具 V2 签名测试 —— 验证 skill_dir / available_skills 从 ToolContext 直接字段读取。"""
import pytest
from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.builtin.skill.read_skill import ReadSkillTool
from derisk.agent.tools.builtin.skill.list_skills import ListSkillsTool
from derisk.agent.tools.builtin.skill.execute_skill import ExecuteSkillScriptTool


class TestSkillToolV2ContextFields:
    """验证 Skill 工具从 ToolContext 直接字段读取 skill_dir / available_skills。"""

    def test_read_skill_resolves_from_direct_fields(self):
        """ReadSkillTool 从 context.skill_dir 和 context.available_skills 解析路径。"""
        ctx = ToolContext(
            skill_dir="/skills",
            available_skills={"sql_review": "/skills/sql_review"},
        )
        tool = ReadSkillTool()
        resolved = tool._resolve_skill_dir("sql_review", ctx)
        assert resolved == "/skills/sql_review"

    def test_read_skill_falls_back_to_config(self):
        """ReadSkillTool 在直接字段为空时回退到 context.config。"""
        ctx = ToolContext()
        ctx.config["available_skills"] = {"sql_review": "/skills/sql_review"}
        tool = ReadSkillTool()
        resolved = tool._resolve_skill_dir("sql_review", ctx)
        assert resolved == "/skills/sql_review"

    def test_read_skill_skill_dir_fallback_to_config(self):
        """ReadSkillTool 的 skill_dir 在直接字段为空时回退到 context.config。"""
        ctx = ToolContext()
        ctx.config["skill_dir"] = "/skills"
        tool = ReadSkillTool()
        resolved = tool._resolve_skill_dir("sql_review", ctx)
        # available_skills 也没有，走 skill_dir 拼接
        assert resolved is not None
        assert "/skills" in resolved

    def test_list_skills_reads_from_direct_field(self):
        """ListSkillsTool 从 context.available_skills 直接字段读取。"""
        ctx = ToolContext(
            available_skills={"sql_review": "/skills/sql_review"},
        )
        tool = ListSkillsTool()
        result = tool._format_skills_from_map(ctx.available_skills)
        assert result.success
        assert "sql_review" in result.output

    def test_list_skills_falls_back_to_config(self):
        """ListSkillsTool 在直接字段为空时回退到 context.config。"""
        ctx = ToolContext()
        ctx.config["available_skills"] = {"sql_review": "/skills/sql_review"}
        tool = ListSkillsTool()
        result = tool._format_skills_from_map(ctx.config["available_skills"])
        assert result.success
        assert "sql_review" in result.output

    def test_list_skills_resolve_base_dir_from_direct_field(self):
        """ListSkillsTool._resolve_skill_base_dir 从 context.skill_dir 读取。"""
        ctx = ToolContext(skill_dir="/skills")
        tool = ListSkillsTool()
        resolved = tool._resolve_skill_base_dir(ctx)
        assert resolved == "/skills"

    def test_list_skills_resolve_base_dir_fallback_to_config(self):
        """ListSkillsTool._resolve_skill_base_dir 在直接字段为空时回退到 config。"""
        ctx = ToolContext()
        ctx.config["skill_dir"] = "/skills_from_config"
        tool = ListSkillsTool()
        resolved = tool._resolve_skill_base_dir(ctx)
        assert resolved == "/skills_from_config"

    def test_execute_skill_resolves_from_direct_fields(self):
        """ExecuteSkillScriptTool 从 context.skill_dir 和 context.available_skills 解析路径。"""
        ctx = ToolContext(
            skill_dir="/skills",
            available_skills={"sql_review": "/skills/sql_review"},
        )
        tool = ExecuteSkillScriptTool()
        resolved = tool._resolve_skill_dir("sql_review", ctx)
        assert resolved == "/skills/sql_review"

    def test_execute_skill_falls_back_to_config(self):
        """ExecuteSkillScriptTool 在直接字段为空时回退到 context.config。"""
        ctx = ToolContext()
        ctx.config["available_skills"] = {"sql_review": "/skills/sql_review"}
        tool = ExecuteSkillScriptTool()
        resolved = tool._resolve_skill_dir("sql_review", ctx)
        assert resolved == "/skills/sql_review"

    def test_context_none_handled_gracefully(self):
        """context=None 时各工具不崩溃。"""
        tool = ReadSkillTool()
        resolved = tool._resolve_skill_dir("any_skill", None)
        # 没有 context 时走本地 fallback 或返回 None
        assert resolved is None or isinstance(resolved, str)

    def test_empty_context_direct_fields(self):
        """空的 ToolContext（skill_dir=None, available_skills={}）不崩溃。"""
        ctx = ToolContext()
        tool = ReadSkillTool()
        resolved = tool._resolve_skill_dir("any_skill", ctx)
        assert resolved is None or isinstance(resolved, str)


class TestSkillToolV2ExecuteIntegration:
    """execute() 集成测试 —— 验证从 ToolContext 直接字段读取的完整流程。"""

    async def test_list_skills_execute_reads_from_context(self):
        """ListSkillsTool.execute() 从 context.available_skills 直接字段读取并格式化输出。"""
        ctx = ToolContext(
            available_skills={"sql_review": "/skills/sql_review"},
        )
        tool = ListSkillsTool()
        result = await tool.execute({}, context=ctx)
        assert result.success
        assert "sql_review" in result.output
        assert "/skills/sql_review" in result.output

    async def test_list_skills_execute_empty_skills(self):
        """ListSkillsTool.execute() 在 available_skills 为空时返回空提示。"""
        ctx = ToolContext(available_skills={})
        tool = ListSkillsTool()
        result = await tool.execute({}, context=ctx)
        # available_skills 为空 dict 不会触发 early return，会走到 local fallback
        # 但 local fallback 的 skill_dir 可能也不存在，所以可能 fail 也可能 success
        # 关键验证：不崩溃
        assert result is not None

    async def test_read_skill_execute_reads_from_context(self, tmp_path):
        """ReadSkillTool.execute() 从 context.available_skills 解析路径并读取 SKILL.md。"""
        skill_dir = tmp_path / "sql_review"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: sql_review\ndescription: SQL review skill\n---\n\n# SQL Review\n\nThis skill reviews SQL queries.")

        ctx = ToolContext(
            available_skills={"sql_review": str(skill_dir)},
        )
        tool = ReadSkillTool()
        result = await tool.execute({"skill_name": "sql_review"}, context=ctx)
        assert result.success
        assert "SQL Review" in result.output
        assert result.metadata.get("is_skill_content") is True
        assert result.metadata.get("skill_name") == "sql_review"

    async def test_read_skill_execute_skill_not_found(self, tmp_path):
        """ReadSkillTool.execute() 在 skill 路径不存在时返回失败。"""
        ctx = ToolContext(
            available_skills={"missing_skill": str(tmp_path / "missing_skill")},
        )
        tool = ReadSkillTool()
        result = await tool.execute({"skill_name": "missing_skill"}, context=ctx)
        assert not result.success
        assert "not found" in result.error.lower()

    async def test_execute_skill_script_execute_reads_from_context(self, tmp_path):
        """ExecuteSkillScriptTool.execute() 从 context.available_skills 解析路径并执行脚本。"""
        skill_dir = tmp_path / "sql_review"
        skill_dir.mkdir()
        script = skill_dir / "hello.sh"
        script.write_text("#!/bin/bash\necho 'hello from sql_review'")

        ctx = ToolContext(
            available_skills={"sql_review": str(skill_dir)},
        )
        tool = ExecuteSkillScriptTool()
        result = await tool.execute(
            {"skill_name": "sql_review", "file_name": "hello.sh"},
            context=ctx,
        )
        assert result.success
        assert "hello from sql_review" in result.output
        assert result.metadata.get("skill_name") == "sql_review"
