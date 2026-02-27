"""
Open RCA Agent Module

故障根因分析 Agent 模块，提供基于 ReActMasterAgent 的主 Agent 和相关资源。

架构说明：
1. OpenRcaReActMasterAgent - 主 Agent，负责规划和推理
2. OpenRcaSkillResource - 技能资源，提供诊断框架
3. IpythonAssistantAgent - Code Agent，负责执行数据分析代码（复用现有实现）
4. DiagRportAssistantAgent - Reporter Agent，负责生成诊断报告（复用现有实现）

使用方式：
- 场景数据（日志文件、指标文件等）作为对话输入资源传入
- 主 Agent 根据任务需求委派 CodeAgent 执行数据分析
- 诊断完成后委派 Reporter 生成报告
"""



__all__ = [
    # 原有 Agent（兼容保留）
]