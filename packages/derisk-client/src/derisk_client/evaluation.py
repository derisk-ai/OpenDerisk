"""Evaluation."""

from typing import List

from derisk.core.interface.evaluation import EvaluationResult
from derisk.core.schema.api import Result
from derisk_serve.evaluate.api.schemas import ServeRequest 

from .client import Client, ClientException


async def run_evaluation(
    client: Client, request: ServeRequest
) -> List[EvaluationResult]:
    """Run evaluation.

    Args:
        client (Client): The derisk client.
        request (EvaluateServeRequest): The Evaluate Request.
    """
    try:
        res = await client.post("/evaluate/evaluation", request.dict())
        result: Result = res.json()
        if result["success"]:
            return list(result["data"])
        else:
            raise ClientException(status=result["err_code"], reason=result)
    except Exception as e:
        raise ClientException(f"Failed to run evaluation: {e}")
