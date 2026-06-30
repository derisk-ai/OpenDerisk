"""Built-in Playbook examples — data ops weekly report + SRE capacity inspection.

These can be seeded into a workspace via POST /playbooks/seed_builtin
(to make adoption easy for design-partner teams).
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
        "skills": ["db_query_skill", "report_skill"],
        "context": {
            "assets_required": [
                {"type": "historical_artifact", "query": "type=weekly_report LIMIT 1"},
            ],
            "resources": [
                {"ref": "resource:prod_core_db"},
            ],
        },
        "deliverables": [
            {
                "type": "report",
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
        "skills": [
            "db_query_skill", "baseline_compare_skill",
            "anomaly_detect_skill", "report_skill",
        ],
        "context": {
            "assets_required": [
                {"type": "historical_artifact", "query": "type=capacity_report LIMIT 1"},
            ],
            "resources": [
                {"ref": "resource:monitor_db"},
                {"ref": "resource:prod_cn1"},
            ],
        },
        "deliverables": [
            {
                "type": "report",
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
