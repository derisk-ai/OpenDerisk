from typing_extensions import Annotated, Doc

from ...resource.tool.base import tool


@tool(description="Calculate the sum of two numbers")
def add_two_numbers(
    a: Annotated[int, Doc("number to which another is added.")],
    b: Annotated[int, Doc("number to be added.")]
) -> int:
    return a + b
