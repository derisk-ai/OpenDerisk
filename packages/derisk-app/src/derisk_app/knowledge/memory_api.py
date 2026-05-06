"""Memory management REST API.

Provides endpoints for managing Memory-type knowledge spaces:
- Write / search / delete individual memory entries
- Knowledge graph operations (add / query / invalidate triples)
- Bulk document import
- Wing / room listing and status

These endpoints work with any registered MemoryStoreBase provider
(MemPalace by default, switchable via config).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.i18n_utils import _
from derisk_app.openapi.api_v1.api_v1 import get_executor
from derisk_app.openapi.api_view_model import Result
from derisk_serve.rag.service.service import Service
from derisk_serve.rag.storage_manager import StorageManager
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Memory"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class MemoryWriteRequest(BaseModel):
    """Request to write a single memory entry."""

    content: str = Field(..., description="The text content to memorize.")
    wing: str = Field(..., description="Top-level group (e.g. app_code).")
    room: str = Field("general", description="Topic within the wing.")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Extra metadata."
    )


class MemorySearchRequest(BaseModel):
    """Request to search memories."""

    query: str = Field(..., description="Semantic search query.")
    wing: Optional[str] = Field(None, description="Filter by wing.")
    room: Optional[str] = Field(None, description="Filter by room.")
    top_k: int = Field(5, description="Max results to return.")
    max_distance: float = Field(0.4, description="Max vector distance.")


class MemoryDeleteRequest(BaseModel):
    """Request to delete a memory entry."""

    memory_id: str = Field(..., description="The memory entry id.")


class KGAddRequest(BaseModel):
    """Request to add a knowledge graph triple."""

    subject: str
    predicate: str
    object_: str = Field(..., alias="object")
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None


class KGQueryRequest(BaseModel):
    """Request to query knowledge graph."""

    entity: str
    as_of: Optional[str] = None


class KGInvalidateRequest(BaseModel):
    """Request to invalidate a KG triple."""

    triple_id: str


class MemoryImportRequest(BaseModel):
    """Request to bulk-import documents into memory."""

    source_path: str = Field(..., description="Path to directory or file.")
    wing: Optional[str] = Field(None, description="Override wing name.")


# ---------------------------------------------------------------------------
# Helper: get memory store for a knowledge space
# ---------------------------------------------------------------------------


def _get_memory_store(space_id: str):
    """Get the MemoryStoreBase for a Memory-type knowledge space."""
    from derisk.component import SystemApp

    system_app = SystemApp.get_instance()
    storage_manager: StorageManager = system_app.get_component(
        "storage_manager", StorageManager
    )
    store = storage_manager.create_memory_store(space_id)
    if store is None:
        raise ValueError(
            f"Memory store not available for space {space_id}. "
            "Check that a memory provider (e.g. mempalace) is installed."
        )
    return store


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/memory/{space_id}/write")
async def memory_write(space_id: str, request: MemoryWriteRequest):
    """Write a single memory entry into a Memory-type knowledge space."""
    try:
        store = _get_memory_store(space_id)
        entry = await blocking_func_to_async(
            get_executor(),
            store.write_memory,
            request.content,
            request.wing,
            request.room,
            request.metadata,
        )
        return Result.succ(
            {
                "id": entry.id,
                "wing": entry.wing,
                "room": entry.room,
                "created_at": entry.created_at,
            }
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"memory write error: {e}")


@router.post("/memory/{space_id}/search")
async def memory_search(space_id: str, request: MemorySearchRequest):
    """Search memories by semantic similarity."""
    try:
        store = _get_memory_store(space_id)
        entries = await blocking_func_to_async(
            get_executor(),
            store.search_memory,
            request.query,
            request.top_k,
            request.wing,
            request.room,
            request.max_distance,
        )
        return Result.succ(
            [
                {
                    "id": e.id,
                    "content": e.content,
                    "wing": e.wing,
                    "room": e.room,
                    "score": e.score,
                    "created_at": e.created_at,
                }
                for e in entries
            ]
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"memory search error: {e}")


@router.post("/memory/{space_id}/delete")
async def memory_delete(space_id: str, request: MemoryDeleteRequest):
    """Delete a single memory entry."""
    try:
        store = _get_memory_store(space_id)
        ok = await blocking_func_to_async(
            get_executor(), store.delete_memory, request.memory_id
        )
        return Result.succ({"deleted": ok, "memory_id": request.memory_id})
    except Exception as e:
        return Result.failed(code="E000X", msg=f"memory delete error: {e}")


# --- Knowledge Graph endpoints ---


@router.post("/memory/{space_id}/kg/add")
async def kg_add(space_id: str, request: KGAddRequest):
    """Add a knowledge graph triple."""
    try:
        store = _get_memory_store(space_id)
        triple_id = await blocking_func_to_async(
            get_executor(),
            store.kg_add,
            request.subject,
            request.predicate,
            request.object_,
            request.valid_from,
            request.valid_to,
            request.confidence,
            request.source,
        )
        return Result.succ({"triple_id": triple_id})
    except Exception as e:
        return Result.failed(code="E000X", msg=f"kg add error: {e}")


@router.post("/memory/{space_id}/kg/query")
async def kg_query(space_id: str, request: KGQueryRequest):
    """Query knowledge graph triples for an entity."""
    try:
        store = _get_memory_store(space_id)
        triples = await blocking_func_to_async(
            get_executor(), store.kg_query, request.entity, request.as_of
        )
        return Result.succ(
            [
                {
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object": t.object_,
                    "valid_from": t.valid_from,
                    "valid_to": t.valid_to,
                    "confidence": t.confidence,
                }
                for t in triples
            ]
        )
    except Exception as e:
        return Result.failed(code="E000X", msg=f"kg query error: {e}")


@router.post("/memory/{space_id}/kg/invalidate")
async def kg_invalidate(space_id: str, request: KGInvalidateRequest):
    """Invalidate (soft-delete) a knowledge graph triple."""
    try:
        store = _get_memory_store(space_id)
        ok = await blocking_func_to_async(
            get_executor(), store.kg_invalidate, request.triple_id
        )
        return Result.succ({"invalidated": ok, "triple_id": request.triple_id})
    except Exception as e:
        return Result.failed(code="E000X", msg=f"kg invalidate error: {e}")


# --- Bulk import ---


@router.post("/memory/{space_id}/import")
async def memory_import(space_id: str, request: MemoryImportRequest):
    """Bulk-import documents or files into the memory store."""
    try:
        store = _get_memory_store(space_id)
        stats = await blocking_func_to_async(
            get_executor(),
            store.import_documents,
            request.source_path,
            request.wing,
        )
        return Result.succ(stats)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"memory import error: {e}")


# --- Management ---


@router.get("/memory/{space_id}/wings")
async def list_wings(space_id: str):
    """List all wings in the memory store."""
    try:
        store = _get_memory_store(space_id)
        wings = await blocking_func_to_async(get_executor(), store.list_wings)
        return Result.succ(wings)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"list wings error: {e}")


@router.get("/memory/{space_id}/rooms")
async def list_rooms(space_id: str, wing: str):
    """List rooms within a wing."""
    try:
        store = _get_memory_store(space_id)
        rooms = await blocking_func_to_async(
            get_executor(), store.list_rooms, wing
        )
        return Result.succ(rooms)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"list rooms error: {e}")


@router.get("/memory/{space_id}/status")
async def memory_status(space_id: str):
    """Get overall memory store status."""
    try:
        store = _get_memory_store(space_id)
        status = await blocking_func_to_async(get_executor(), store.get_status)
        return Result.succ(status)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"memory status error: {e}")
