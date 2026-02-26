"""Cron scheduler interface.

This module defines the abstract interface for cron schedulers,
allowing for different implementations (APScheduler, etc.).
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .types import CronJob, CronJobCreate, CronJobPatch, CronStatusSummary


class CronScheduler(ABC):
    """Abstract interface for cron job scheduling.

    This interface defines the contract for cron scheduler implementations.
    Implementations should handle job persistence, scheduling, and execution.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the scheduler.

        This method should initialize the scheduler and begin processing jobs.
        It should recover any persisted jobs and schedule them for execution.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the scheduler.

        This method should gracefully shut down the scheduler,
        stopping any running jobs and persisting state if necessary.
        """
        ...

    @abstractmethod
    async def status(self) -> CronStatusSummary:
        """Get the current scheduler status.

        Returns:
            CronStatusSummary: Summary of scheduler state and job counts.
        """
        ...

    @abstractmethod
    async def list_jobs(self, include_disabled: bool = False) -> List[CronJob]:
        """List all scheduled jobs.

        Args:
            include_disabled: Whether to include disabled jobs in the result.

        Returns:
            List of cron jobs.
        """
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[CronJob]:
        """Get a specific job by ID.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            The cron job if found, None otherwise.
        """
        ...

    @abstractmethod
    async def add_job(self, job: CronJobCreate) -> CronJob:
        """Add a new cron job.

        Args:
            job: The job creation request.

        Returns:
            The created cron job.
        """
        ...

    @abstractmethod
    async def update_job(self, job_id: str, patch: CronJobPatch) -> CronJob:
        """Update an existing cron job.

        Args:
            job_id: The unique identifier of the job to update.
            patch: The patch request with fields to update.

        Returns:
            The updated cron job.

        Raises:
            NotFoundError: If the job does not exist.
        """
        ...

    @abstractmethod
    async def remove_job(self, job_id: str) -> bool:
        """Remove a cron job.

        Args:
            job_id: The unique identifier of the job to remove.

        Returns:
            True if the job was removed, False if it did not exist.
        """
        ...

    @abstractmethod
    async def run_job(self, job_id: str, force: bool = False) -> bool:
        """Manually trigger a job execution.

        Args:
            job_id: The unique identifier of the job to run.
            force: If True, run even if the job is disabled or already running.

        Returns:
            True if the job was triggered, False otherwise.
        """
        ...