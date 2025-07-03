from typing import List, Optional

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk_serve.core import BaseService

from ..api.schemas import ServeRequest, ServerResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import ServeDao, ServeEntity

from derisk.core.interface.evaluation import (
    EVALUATE_FILE_COL_ANSWER,
    EvaluationResult,
    metric_manage
) 

class Service(BaseService[ServeEntity, ServeRequest, ServerResponse]):
    """The service class for Evaluate"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig, dao: Optional[ServeDao] = None
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ServeDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao[ServeEntity, ServeRequest, ServerResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    async def evalueate(
        self,
        scene_key,
        scene_value,
        datasets: List[dict] = None,
        context: Optional[dict] = None,
        evaluate_metrics: Optional[List[str]] = None,
        parallel_num: Optional[int] = 1
    ) -> List[List[EvaluationResult]]:
        """ Evaluate the given scene with the provided datasets and metrics.
        Args:
            scene_key (str): The key for the scene to evaluate.
            scene_value (str): The value for the scene to evaluate.
            datasets (List[dict], optional): List of datasets to evaluate against.
            context (Optional[dict], optional): Additional context for evaluation.
            evaluate_metrics (Optional[List[str]], optional): Metrics to use for evaluation.
            parallel_num (Optional[int], optional): Number of parallel evaluations.
        Returns:
            List[List[EvaluationResult]]: The evaluation results.
        """ 
        entity = self._dao.from_request()
        # TODO implement your own logic here, process the entity
        response = ServerResponse(message="Evaluation completed successfully.")
        return response