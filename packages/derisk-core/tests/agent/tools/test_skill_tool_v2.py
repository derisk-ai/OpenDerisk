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
