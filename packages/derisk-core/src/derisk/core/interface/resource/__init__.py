"""Resource protocol contracts (RFC-005).

协议契约子包,按职责拆分:
- bundle: 输入载体(InputBundle/FrozenBundle/Contribution/SystemBlock/缓存语义)
- tool_entry: ToolEntry + BUILTIN_EXECUTOR_ID(input↔executor 共享桥)
- executor: 执行投影(Executor/Registry/topological_prepare)
- dispatcher: 工具派发(ToolDispatcher/ToolDispatchResult)
- data_requirement: 大库降级契约(DataRequirement/InjectionMode)
- protocol: 资源协议本体(ResourceProtocol/ConsumerRegistry/apply_consumption)

旧路径 ``derisk.core.interface.input`` / ``derisk.core.interface.executor``
保留为重导出 shim,向后兼容。
"""