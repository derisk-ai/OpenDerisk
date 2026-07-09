"""Built-in Playbook examples — data ops weekly report + SRE capacity inspection.

These can be seeded into a workspace via POST /playbooks/seed_builtin
(to make adoption easy for design-partner teams).

v2 schema adds text_content block for independent playbook text (RFC-005).
"""
from typing import Any, Dict


DATA_OPS_WEEKLY_REPORT: Dict[str, Any] = {
    "name": "Data Operations Weekly Report",
    "scenario_type": "data_ops",
    "task_type": "routine",
    "trigger": {
        "type": "timer",
        "cron": "0 9 * * 1",  # every Monday 9am
    },
    "declaration": {
        # NEW: RFC-005 独立文本部分
        "text_content": {
            "role_definition": "你是数据运营周报生成专家，负责分析数据库关键指标并产出结构化报告。",
            "goal": "生成一份包含本周关键数据指标的运营周报，帮助团队了解数据健康状况。",
            "workflow": "1. 连接目标数据库\n2. 执行预设的关键指标查询\n3. 对比上周数据进行趋势分析\n4. 汇总成结构化报告\n5. 提取关键洞察和建议",
            "behavior_constraints": "使用中文输出；报告需包含数据摘要、趋势分析和改进建议三个部分；避免使用过于专业的技术术语。",
            "background": "每周一早上9点自动执行，报告发送至 ops-team@company.com。",
        },
        "skills": ["db_query_skill", "report_skill"],
        "context": {
            "assets_required": [
                {"type": "historical_artifact", "query": "type=weekly_report LIMIT 1"},
            ],
            "resources": [
                {"type": "datasource", "ref": "prod_core_db"},
            ],
        },
        "deliverables": [
            {
                "type": "report",
                "title": "数据运营周报",
                "delivery": [
                    {"category": "notify", "channel": "email", "target": "ops-team@company.com"},
                ],
            },
        ],
        "distill": {
            "forced": True,
            "produce": [
                {"type": "historical_artifact", "from": "deliverable.0"},
            ],
        },
    },
}


SRE_CAPACITY_INSPECTION: Dict[str, Any] = {
    "name": "SRE Capacity Inspection",
    "scenario_type": "sre",
    "task_type": "routine",
    "trigger": {
        "type": "timer",
        "cron": "0 2 * * *",  # daily 2am
    },
    "declaration": {
        # NEW: RFC-005 独立文本部分
        "text_content": {
            "role_definition": "你是 SRE 容量巡检专家，负责监控系统资源使用情况并发现潜在风险。",
            "goal": "检测系统容量瓶颈，生成容量巡检报告，在发现异常时触发告警。",
            "workflow": "1. 收集各核心集群的资源使用指标\n2. 与历史基线进行对比分析\n3. 使用异常检测算法识别风险点\n4. 生成容量巡检报告\n5. 如有异常，创建 Case 并通知 oncall 团队",
            "behavior_constraints": "使用中文输出；报告需包含容量概览、异常分析和行动建议；发现严重异常时必须明确标注风险等级。",
            "background": "每日凌晨2点自动执行，报告发送至 oncall_group 飞书群。",
        },
        "skills": [
            "db_query_skill", "baseline_compare_skill",
            "anomaly_detect_skill", "report_skill",
        ],
        "context": {
            "assets_required": [
                {"type": "historical_artifact", "query": "type=capacity_report LIMIT 1"},
            ],
            "resources": [
                {"type": "datasource", "ref": "monitor_db"},
                {"type": "datasource", "ref": "prod_cn1"},
            ],
        },
        "deliverables": [
            {
                "type": "report",
                "title": "SRE 容量巡检报告",
                "delivery": [
                    {"category": "notify", "channel": "feishu", "target": "oncall_group"},
                ],
            },
        ],
        "distill": {
            "forced": True,
            "produce": [
                {"type": "historical_artifact", "from": "deliverable.0"},
                {"type": "case", "from": "deliverable.0", "when": "anomalies_detected == true"},
            ],
        },
    },
}


BUILTIN_PLAYBOOKS = [DATA_OPS_WEEKLY_REPORT, SRE_CAPACITY_INSPECTION]
