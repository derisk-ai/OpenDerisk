from derisk.agent.resource.tool.base import tool

_TERMINATE_DESCRIPTION = """Terminate the interaction when the request is met OR if the
 assistant cannot proceed furture with the task. """


@tool(description=_TERMINATE_DESCRIPTION)
def terminate(status: str) -> str:
    """Finish the current execution"""
    return f"The interaction has been completed with status: {status}"
