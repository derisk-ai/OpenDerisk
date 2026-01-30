"""Utility functions for reasoning agents."""


def identify_action_info(action_output) -> dict:
    """Extract action information from action output.

    Args:
        action_output: The action output to extract info from

    Returns:
        Dictionary containing action information
    """
    if not action_output:
        return {}
    # Stub implementation - extract basic info from action output
    result = {}
    for key in ["action", "action_name", "name", "content", "state"]:
        if hasattr(action_output, key):
            result[key] = getattr(action_output, key)
    return result