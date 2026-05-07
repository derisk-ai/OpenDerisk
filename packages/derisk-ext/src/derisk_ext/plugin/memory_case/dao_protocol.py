from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from .models import CandidateCase


class MemoryCaseDaoLike(Protocol):
    """Persistence port for MemoryCasePluginService (implemented in derisk-serve)."""

    def upsert(self, case: CandidateCase) -> CandidateCase: ...

    def get_by_case_id(self, case_id: str) -> Optional[CandidateCase]: ...

    def search(
        self,
        scope: Dict[str, Any],
        query_text: Optional[str] = None,
        limit: int = 10,
    ) -> List[CandidateCase]: ...
