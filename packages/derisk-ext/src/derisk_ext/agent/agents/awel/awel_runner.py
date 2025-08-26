import asyncio
import logging
from typing import Optional

from derisk.core.awel import DAGContext, BaseOperator, DefaultTaskContext, TaskState, DefaultWorkflowRunner, TaskOutput, DefaultInputContext, JoinOperator
from derisk.core.awel.dag.base import DAGVariables
from derisk.core.awel.operators.base import CALL_DATA
from derisk.util.date_utils import current_ms
from derisk.util.logger import LoggingParameters, setup_logging

setup_logging("awel", LoggingParameters(file="awel.log"))
logger: logging.Logger = logging.getLogger("awel")


class AWELRunner(DefaultWorkflowRunner):
    """Execute the workflow """

    async def execute_workflow(
            self,
            node: BaseOperator,
            call_data: Optional[CALL_DATA] = None,
            streaming_call: bool = False,
            exist_dag_ctx: Optional[DAGContext] = None,
            dag_variables: Optional[DAGVariables] = None,
    ) -> DAGContext:
        """Execute the workflow starting from a given operator.

        Args:
            node (RunnableDAGNode): The starting node of the workflow to be executed.
            call_data (CALL_DATA): The data pass to root operator node.
            streaming_call (bool): Whether the call is a streaming call.
            exist_dag_ctx (DAGContext): The context of the DAG when this node is run,
                Defaults to None.
            dag_variables (DAGVariables): The DAG variables.
        Returns:
            DAGContext: The context after executing the workflow, containing the final
                state and data.
        """
        dag_variables = dag_variables or DAGVariables()
        dag_ctx: DAGContext = exist_dag_ctx or DAGContext(
            event_loop_task_id=id(asyncio.current_task()),
            node_to_outputs={},
            share_data={},
            streaming_call=streaming_call,
            dag_variables=dag_variables,
        )

        nodes: list[BaseOperator] = [node]
        max_exe_count = 100
        exe_count = 0
        while (nodes):
            st = current_ms()
            node_id = None
            node_name = None
            node_type = None
            succ = True
            try:
                # 取出一个节点
                current_node: BaseOperator = nodes.pop()
                node_id = current_node.node_id
                node_name = current_node.node_name
                node_type = current_node.__class__.__name__

                # =============================== ↓↓说明↓↓ =============================== #
                # 下面这段处理导致无法支持循环，后续可能有两个优化方向：
                # 1. 参照业界最佳实践，实现一个循环节点
                # 2. 分情况：
                #   -- JOIN时需要等所有上游结束
                #   -- 循环时不能等所有上游
                #   -- 是否要等上游，交给用户配置，或通过判断是否有环来实现
                # ----------------------------------------------------------------------- #
                # # 去重
                # if current_node.node_id in dag_ctx._node_to_outputs:
                #     logger.info(f"node[{current_node.node_name}/{current_node.node_id}] already finished")
                #     continue

                # 上游节点必须都执行完了 否则等下次触发
                if not isinstance(current_node, JoinOperator) and not self._upstream_done(current_node, dag_ctx):
                    logger.info(f"node[{current_node.node_name}/{current_node.node_id}] upstream not ready")
                    continue
                # =============================== ↑↑说明↑↑ =============================== #

                # 退出条件判断
                if exe_count > max_exe_count:
                    logger.warning(f"too much node executed, quit: node[{current_node.node_name}/{current_node.node_id}]")
                    break
                exe_count += 1

                # 节点执行
                await self.execute_node(current_node, dag_ctx=dag_ctx, call_data=self._get_call_data(current_node, dag_ctx) or call_data)

                # 准备执行下游节点
                skip_node_names = dag_ctx.current_task_context.metadata.get("skip_node_names", [])
                downstream: list = [downstream for downstream in current_node.downstream if downstream.node_name not in skip_node_names]
                nodes.extend(downstream)
            except BaseException as e:
                logger.exception("AWELRunner 捕获异常: " + repr(e))
                succ = False
                raise
            finally:
                logger.info(f"[DIGEST][AWEL_EXE],idx=[{exe_count}],succ=[{succ}],cost_ms=[{current_ms() - st}],"
                            f"node_type=[{node_type}],node_id=[{node_id}],node_name=[{node_name}],nodes_left=[{len(nodes)}],")
        return dag_ctx

    async def execute_node(self, node: BaseOperator, dag_ctx: DAGContext, call_data: Optional[CALL_DATA] = None):
        task_ctx = DefaultTaskContext(node.node_id, TaskState.INIT, task_output=None, log_index=await self._log_task(node.node_id))
        dag_ctx.set_current_task_context(task_ctx)
        try:
            logger.info(f"execute_node[{node.node_name}/{node.node_id}] exe.")
            # 任务上下文初始化
            task_ctx.set_task_input(DefaultInputContext([dag_ctx._task_outputs[upstream_node.node_id] for upstream_node in node.upstream]))
            task_ctx.set_call_data(call_data)
            task_ctx.set_current_state(TaskState.RUNNING)

            # 任务执行
            out: TaskOutput = await node._run(dag_ctx, task_ctx.log_id)

            # 任务上下文更新
            task_ctx.set_task_output(out)
            task_ctx.set_current_state(TaskState.SUCCESS)
            dag_ctx._node_to_outputs[node.node_id] = task_ctx
            dag_ctx._finished_node_ids.append(node.node_id)
        except BaseException as e:
            task_ctx.set_current_state(TaskState.FAILED)
            logger.exception(f"execute_node[{node.node_name}/{node.node_id}] except: {repr(e)}")
            raise
        finally:
            logger.info(f"execute_node[{node.node_name}/{node.node_id}] done.")
        pass

    def _upstream_done(self, node: BaseOperator, dag_ctx: DAGContext) -> bool:
        return not node.upstream or all((upstream.node_id in dag_ctx._task_outputs for upstream in node.upstream))

    def _get_call_data(self, node: BaseOperator, dag_context: DAGContext) -> Optional[CALL_DATA]:
        # todo: merge上游结果
        # 现在只取了第一个上游的输出
        first_upstream = node.upstream[0] if node.upstream else None
        first_output = dag_context._node_to_outputs.get(first_upstream.node_id, None) if first_upstream else None
        output = first_output.task_output.output if first_output else None
        # 兼容原有逻辑 必须多包一层
        return {"data": output} if output else None
