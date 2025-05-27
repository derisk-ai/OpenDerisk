from typing_extensions import Annotated, Doc

from derisk.agent.resource import tool


@tool(description="store information into history")
def store_information(info: str = Annotated[str, Doc("information to store.")]):
    return "OK"
