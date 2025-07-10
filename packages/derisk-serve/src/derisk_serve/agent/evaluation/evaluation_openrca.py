import logging
from abc import ABC
from typing import Any, Optional

from derisk.core.interface.evaluation import (
    BaseEvaluationResult,
    EvaluationMetric,
    metric_manage
)

logger = logging.getLogger(__name__)
