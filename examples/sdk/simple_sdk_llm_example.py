import asyncio

from derisk.core import BaseOutputParser
from derisk.core.awel import DAG
from derisk.core.operators import (
    BaseLLMOperator,
    PromptBuilderOperator,
    RequestBuilderOperator,
)
from derisk.model.proxy import OpenAILLMClient

with DAG("simple_sdk_llm_example_dag") as dag:
    prompt_task = PromptBuilderOperator(
        "Write a SQL of {dialect} to query all data of {table_name}."
    )
    model_pre_handle_task = RequestBuilderOperator(model="gpt-3.5-turbo")
    llm_task = BaseLLMOperator(OpenAILLMClient())
    out_parse_task = BaseOutputParser()
    prompt_task >> model_pre_handle_task >> llm_task >> out_parse_task

if __name__ == "__main__":
    output = asyncio.run(
        out_parse_task.call(call_data={"dialect": "mysql", "table_name": "user"})
    )
    print(f"output: \n\n{output}")
