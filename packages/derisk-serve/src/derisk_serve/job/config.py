"""Persistent job engine serve configuration.

Generic persistent-job + claim-consume worker engine. job_type-keyed handlers
reused across scenarios (knowledge ingest, memory index, ...). See
docs/knowledge/rfc-005-cross-doc-relation-and-dual-space.md and the plan at
.claude/plans/zazzy-percolating-valiant.md.
"""

from dataclasses import dataclass, field
from typing import Optional

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "job"
SERVE_APP_NAME = "derisk_serve_job"
SERVE_APP_NAME_HUMP = "derisk_serve_Job"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.job."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"
# Database table name
SERVER_APP_TABLE_NAME = "derisk_serve_job"


@auto_register_resource(
    label=_("Job Serve Configurations"),
    category=ResourceCategory.COMMON,
    tags={"order": TAGS_ORDER_HIGH},
    description=_("This configuration is for the persistent job engine serve module."),
    show_in_ui=False,
)
@dataclass
class ServeConfig(BaseServeConfig):
    """Configuration for the persistent job engine."""

    __type__ = APP_NAME

    enabled: bool = field(
        default=True,
        metadata={"help": _("Enable the job worker loop")},
    )
    poll_interval_seconds: float = field(
        default=2.0,
        metadata={"help": _("Worker poll interval in seconds")},
    )
    lease_seconds: int = field(
        default=300,
        metadata={"help": _("Claim lease in seconds; stalled jobs reclaimed after expiry")},
    )
    concurrency: int = field(
        default=4,
        metadata={"help": _("Max concurrent job executions per instance")},
    )
    max_attempts_default: int = field(
        default=3,
        metadata={"help": _("Default max attempts for jobs without explicit override")},
    )
    worker_tags: str = field(
        default="default",
        metadata={"help": _("Comma-separated tags this worker advertises; "
                            "jobs whose required_worker is a subset of these are claimable")},
    )
    subscribe_types: str = field(
        default="",
        metadata={"help": _("Comma-separated job_types to consume; empty = all registered handler types")},
    )