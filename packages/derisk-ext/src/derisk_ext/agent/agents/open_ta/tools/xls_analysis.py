import asyncio
import json
import os
from typing import Annotated
from typing_extensions import Doc

from derisk.agent.resource import tool
from derisk.configs.model_config import DATA_DIR
from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.json_utils import EnhancedJSONEncoder
from derisk_ext.agent.agents.open_ta.tools.excel_reader import ExcelReader, resolve_path
from derisk_serve.agent.resource.func_registry import derisk_tool

INTRODUCTION_RROMPT = """给你一份用户的数据介绍，目前数据在 DuckDB 表中，\
一部分采样数据如下:
``````json
{data_example}
``````

表的摘要信息如下:
``````json
{table_summary}
``````

DuckDB 表结构信息如下：
{table_schema}
"""

table_name = "data_analysis_table"

async def _init_excel_reader(file_path: str, clean_db_cache: bool = False)->ExcelReader:
    file_name = os.path.basename(file_path)
    database_root_path = os.path.join(DATA_DIR, "_chat_excel_tmp")
    os.makedirs(database_root_path, exist_ok=True)
    database_file_path = os.path.join(
        database_root_path, f"_chat_excel_{file_name}.duckdb"
    )

    return ExcelReader(
            file_path,
            # read_type="direct",
            read_type="df",
            database_name=database_file_path,
            table_name=table_name,
        )


# @derisk_tool(
#     name="get_data_introduction",
#     description="根据指定excel文件构建对应的数据表，并获取全面数据介绍，包括数据结构,数据示例",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "file_path": {
#                 "type": "string",
#                 "description": "对应的excel文件路径"
#             },
#             "clean_db_cache": {
#                 "type": "boolean",
#                 "description": "是否重建文件对应的db数据"
#             }
#         },
#         "required": ["file_path"]
#     },
#     owner="derisk"
# )



@tool(description="根据指定excel文件构建对应的数据表，并获取全面数据介绍，包括数据结构,数据示例")
async def get_data_introduction(file_path: Annotated[str, Doc("指定的excel文件路径.")], clean_db_cache:  Annotated[bool, Doc("是否重建文件对应的db数据，默认不重建.")] = False):
    excel_reader = await _init_excel_reader(file_path, clean_db_cache)
    from concurrent.futures import ThreadPoolExecutor
    _executor = ThreadPoolExecutor(
        max_workers=5, thread_name_prefix="excel_file_tool"
    )

    columns, datas = await blocking_func_to_async(
        _executor, excel_reader.get_sample_data, table_name
    )
    datas.insert(0, columns)

    table_schema = await blocking_func_to_async(
        _executor, excel_reader.get_create_table_sql, table_name
    )
    table_summary = await blocking_func_to_async(
        _executor, excel_reader.get_summary, table_name
    )

    vars = {
        "table_schema": table_schema,
        "table_summary": table_summary,
        "data_example": json.dumps(
                datas, cls=EnhancedJSONEncoder, ensure_ascii=False
            )
    }
    return INTRODUCTION_RROMPT.format(**vars)


# @derisk_tool(
#     name="run_sql_with_file",
#     description="根据指定excel文件构建对应的数据表，并使用SQL进行数据查询操作",
#     input_schema={
#         "type": "object",
#         "properties": {
#             "file_path": {
#                 "type": "string",
#                 "description": "对应的excel文件路径"
#             },
#             "sql": {
#                 "type": "string",
#                 "description": "针对当前文件数据表进行查询操作的sql语句"
#             },
#             "clean_db_cache": {
#                 "type": "boolean",
#                 "description": "是否重建文件对应的db数据"
#             }
#         },
#         "required": ["file_path", "sql"]
#     },
#     owner="derisk"
# )

@tool(description="根据指定excel文件构建对应的数据表，并使用SQL进行数据查询操作.")
async def run_sql_with_file(file_path: Annotated[str, Doc("指定的excel文件路径.")],sql: Annotated[str, Doc("针对当前文件数据表进行查询操作的sql语句.")], clean_db_cache:  Annotated[bool, Doc("是否重建文件对应的db数据，默认不重建.")] = False ):
    excel_reader = await _init_excel_reader(file_path, clean_db_cache)
    return excel_reader.run(sql, table_name)

if __name__ == "__main__":
    print(asyncio.run(get_data_introduction("/Users/tuyang.yhj/Downloads/Bank/query.csv")))
    # print(asyncio.run(run_sql_with_file("/Users/tuyang.yhj/Downloads/Bank/query.csv", f"SELECT * FROM {table_name} USING SAMPLE 5;")))