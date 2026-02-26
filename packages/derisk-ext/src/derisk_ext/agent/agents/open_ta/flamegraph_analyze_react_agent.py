# """Plugin Assistant Agent."""
# import logging
#
# from derisk.agent.core.profile import DynConfig, ProfileConfig
# from derisk.agent.expand.react_agent.react_agent import ReActAgent
#
# logger = logging.getLogger(__name__)
# class FlamegraphAnalyzeAgent(ReActAgent):
#     """Reasoning Agent."""
#
#     profile: ProfileConfig = ProfileConfig(
#         name=DynConfig(
#             "FlamegraphExpert",
#             category="agent",
#             key="derisk_agent_expand_flamegraph_analysis_expert_name",
#         ),
#         role=DynConfig(
#             "FlamegraphAnalysisExpert",
#             category="agent",
#             key="derisk_agent_expand_flamegraph_analysis_expert_role",
#         ),
#         goal=DynConfig(
#             "根据绑定的技能(工具, MCP/Local Tool)、子Agent、知识库，"
#             "动态规划执行计划，直至任务完成。关键词: ReAct、PromptEngineering。",
#             category="agent",
#             key="derisk_agent_expand_reasoning_assistant_agent_role",
#         ),
#         system_prompt_template="",
#         user_prompt_template="",
#     )
#
#
#
#     def register_variables(self):
#         logger.info(f"{self.name} register_variables!")
#         super().register_variables()
#         logger.info(f"{self.name} register_variables end!")
#         @self._vm.register('flamegraph_file', '用户上传的火焰图文件资源信息')
#         async def get_excel_file(instance, context):
#             try:
#                 flamegraph_file_resource = context.get("common_file", None)
#                 if not flamegraph_file_resource:
#                     logger.warning("火焰图文件信息没有")
#                     return ""
#                 from derisk._private.config import Config
#                 from derisk.core.interface.file import FileStorageClient
#                 CFG = Config()
#                 fs_client = FileStorageClient.get_instance(CFG.SYSTEM_APP)
#                 _bucket = "derisk_app_file"
#                 from derisk_ext.agent.agents.open_ta.tools.excel_reader import resolve_path_simpale
#                 file_path, file_name = resolve_path_simpale(
#                     flamegraph_file_resource,
#                     instance.agent_context.conv_session_id,
#                     fs_client,
#                     _bucket,
#                 )
#
#                 return file_path
#             except Exception as e:
#                 logger.warning(f"excel_file资源参数加载异常！{str(e)}", e)
#                 return None
#
#
