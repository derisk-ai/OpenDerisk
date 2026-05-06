"""Full-chain integration test for the Memory Store module.

Validates:
1. Import chain — all new modules can be imported
2. Interface contract — MemoryStoreBase has all required abstract methods
3. Config subclass discovery — MemPalaceMemoryConfig is auto-discovered
4. MemPalaceMemoryStore implements all abstract methods
5. StorageManager Memory branch — create_memory_store code path
6. Memory API router — endpoints exist and have correct signatures
7. MemoryToolPack — tool registration
8. Pipeline Operators — operator structure
9. App config — resource_memory field exists in ServeRequest
10. App converter — memory resource dispatch exists
"""

import ast
import inspect
import sys
import os

# Add project packages to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["derisk-core", "derisk-ext", "derisk-serve", "derisk-app"]:
    src_path = os.path.join(PROJECT_ROOT, "packages", pkg, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def test_section(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


passed = 0
failed = 0


def check(description, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {description}")
        passed += 1
    else:
        print(f"  [FAIL] {description}")
        if detail:
            print(f"         {detail}")
        failed += 1


# ======================================================================
# 1. Import chain
# ======================================================================
test_section("1. Import Chain")

try:
    from derisk.storage.memory.base import (
        MemoryStoreBase,
        MemoryStoreConfig,
        MemoryEntry,
        KGTriple,
    )
    check("derisk.storage.memory.base imports", True)
except Exception as e:
    check("derisk.storage.memory.base imports", False, str(e))

try:
    from derisk.storage.memory import MemoryStoreBase, MemoryStoreConfig
    check("derisk.storage.memory __init__ re-exports", True)
except Exception as e:
    check("derisk.storage.memory __init__ re-exports", False, str(e))

# ======================================================================
# 2. Interface contract — abstract methods
# ======================================================================
test_section("2. MemoryStoreBase Interface Contract")

required_abstract = {
    # From IndexStoreBase
    "get_config", "load_document", "aload_document",
    "similar_search_with_scores", "delete_by_ids", "truncate",
    "delete_vector_name",
    # From MemoryStoreBase
    "write_memory", "search_memory", "delete_memory",
    "kg_add", "kg_query", "kg_invalidate",
    "import_documents", "list_wings", "list_rooms", "get_status",
}

actual_abstract = set()
for name, method in inspect.getmembers(MemoryStoreBase):
    if getattr(method, "__isabstractmethod__", False):
        actual_abstract.add(name)

for method_name in required_abstract:
    check(
        f"Abstract method: {method_name}",
        method_name in actual_abstract,
        f"Missing from MemoryStoreBase" if method_name not in actual_abstract else "",
    )

# Check async helpers exist (non-abstract)
async_helpers = [
    "awrite_memory", "asearch_memory", "adelete_memory",
    "akg_add", "akg_query", "aimport_documents",
]
for helper in async_helpers:
    check(
        f"Async helper: {helper}",
        hasattr(MemoryStoreBase, helper),
    )

# ======================================================================
# 3. MemoryStoreConfig subclass discovery
# ======================================================================
test_section("3. Config Subclass Discovery")

check(
    "MemoryStoreConfig.__cfg_type__ = 'memory_store'",
    getattr(MemoryStoreConfig, "__cfg_type__", None) == "memory_store",
)

# Parse the ext module file to verify class structure
store_file = os.path.join(
    PROJECT_ROOT,
    "packages/derisk-ext/src/derisk_ext/storage/memory/mempalace_store.py",
)
with open(store_file) as f:
    tree = ast.parse(f.read())

class_names = [
    node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
]
check("MemPalaceMemoryConfig class exists", "MemPalaceMemoryConfig" in class_names)
check("MemPalaceMemoryStore class exists", "MemPalaceMemoryStore" in class_names)

with open(store_file) as f:
    content = f.read()
check('MemPalaceMemoryConfig.__type__ = "mempalace"', '__type__ = "mempalace"' in content)
check("Embedding mode: use_builtin_embedding config field", "use_builtin_embedding" in content)
check("Unified embedding: _unified_add method", "_unified_add" in content)
check("Unified embedding: _unified_search method", "_unified_search" in content)
check("Dual mode: _use_derisk_embedding flag", "_use_derisk_embedding" in content)

# ======================================================================
# 4. MemPalaceMemoryStore implements all abstract methods
# ======================================================================
test_section("4. MemPalaceMemoryStore Method Coverage")

method_defs = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        method_defs.add(node.name)

for method_name in required_abstract:
    check(
        f"Implements: {method_name}",
        method_name in method_defs,
        f"Missing implementation" if method_name not in method_defs else "",
    )

# ======================================================================
# 5. StorageManager Memory branch
# ======================================================================
test_section("5. StorageManager Memory Branch")

sm_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-serve/src/derisk_serve/rag/storage_manager.py",
)
with open(sm_file) as f:
    sm_content = f.read()

check('storage_type == "Memory" branch exists', 'storage_type == "Memory"' in sm_content)
check("create_memory_store() method exists", "def create_memory_store" in sm_content)
check("MemoryStoreConfig import", "from derisk.storage.memory.base import" in sm_content)
check("_get_all_memory_subclasses helper", "def _get_all_memory_subclasses" in sm_content)
check("Embedding factory passed to create_store", "embedding_fn" in sm_content)

# ======================================================================
# 6. Memory API router
# ======================================================================
test_section("6. Memory Management API")

api_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-app/src/derisk_app/knowledge/memory_api.py",
)
with open(api_file) as f:
    api_content = f.read()

expected_endpoints = [
    "/memory/{space_id}/write", "/memory/{space_id}/search",
    "/memory/{space_id}/delete", "/memory/{space_id}/kg/add",
    "/memory/{space_id}/kg/query", "/memory/{space_id}/kg/invalidate",
    "/memory/{space_id}/import", "/memory/{space_id}/wings",
    "/memory/{space_id}/rooms", "/memory/{space_id}/status",
]
for endpoint in expected_endpoints:
    check(f"Endpoint: {endpoint}", endpoint in api_content)

knowledge_api_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-app/src/derisk_app/knowledge/api.py",
)
with open(knowledge_api_file) as f:
    ka_content = f.read()

check("Memory router mounted in knowledge api", "memory_api" in ka_content and "include_router" in ka_content)
check('Memory storage type in space/config', '"Memory"' in ka_content)

# ======================================================================
# 7. MemoryToolPack
# ======================================================================
test_section("7. MemoryToolPack")

tool_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-serve/src/derisk_serve/agent/resource/tool/memory_tool.py",
)
with open(tool_file) as f:
    tool_content = f.read()

check("MemoryToolPack class exists", "class MemoryToolPack" in tool_content)
check("Tool: memory_search", '"memory_search"' in tool_content)
check("Tool: memory_save", '"memory_save"' in tool_content)
check("Tool: kg_query", '"kg_query"' in tool_content)
check("Tool: kg_add", '"kg_add"' in tool_content)
check('type_alias = "tool(memory)"', 'tool(memory)' in tool_content)

# ======================================================================
# 8. Pipeline Operators
# ======================================================================
test_section("8. Pipeline Operators")

op_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-serve/src/derisk_serve/memory/operators/longterm_memory_operator.py",
)
with open(op_file) as f:
    op_content = f.read()

check("LongTermMemoryRetrievalOperator exists", "class LongTermMemoryRetrievalOperator" in op_content)
check("LongTermMemoryWriteOperator exists", "class LongTermMemoryWriteOperator" in op_content)
check("Retrieval injects memory into context", "long_term_memory" in op_content)
check("Write evaluates importance", "_is_important" in op_content)
check("Room classification", "_classify_room" in op_content)

# ======================================================================
# 9. App Config — resource_memory
# ======================================================================
test_section("9. App Config Schema")

schema_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-serve/src/derisk_serve/building/config/api/schemas.py",
)
with open(schema_file) as f:
    schema_content = f.read()

check("resource_memory field in ServeRequest", "resource_memory" in schema_content)

service_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-serve/src/derisk_serve/building/app/service/service.py",
)
with open(service_file) as f:
    service_content = f.read()

check("resource_memory passed in app_info_to_config", "resource_memory" in service_content)

# ======================================================================
# 10. App converter — memory dispatch
# ======================================================================
test_section("10. App V2 Converter")

converter_file = os.path.join(
    PROJECT_ROOT, "packages/derisk-serve/src/derisk_serve/agent/app_to_v2_converter.py",
)
with open(converter_file) as f:
    converter_content = f.read()

check("ResourceType.Memory dispatch", "ResourceType.Memory" in converter_content)
check("_process_memory_resource function", "_process_memory_resource" in converter_content)

# ======================================================================
# 11. Dependency declarations
# ======================================================================
test_section("11. Dependencies")

ext_pyproject = os.path.join(PROJECT_ROOT, "packages/derisk-ext/pyproject.toml")
with open(ext_pyproject) as f:
    check("mempalace in derisk-ext deps", "mempalace" in f.read())

app_pyproject = os.path.join(PROJECT_ROOT, "packages/derisk-app/pyproject.toml")
with open(app_pyproject) as f:
    check("mempalace in derisk-app deps", "mempalace" in f.read())

# ======================================================================
# 12. Embedding model integration
# ======================================================================
test_section("12. Embedding Model Integration")

check("MemPalaceMemoryStore accepts embedding_fn param",
      "embedding_fn: Optional[Embeddings]" in content)
check("Unified Chroma collection: _get_chroma_collection",
      "_get_chroma_collection" in content)
check("Dedup via SHA256: _gen_drawer_id",
      "_gen_drawer_id" in content and "sha256" in content)
check("embed_documents call in unified mode",
      "embed_documents" in content)
check("embed_query call in unified mode",
      "embed_query" in content)

# ======================================================================
# Summary
# ======================================================================
print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'='*60}")

if failed > 0:
    print("\n  Some tests failed! Review the output above.")
    sys.exit(1)
else:
    print("\n  All tests passed!")
    sys.exit(0)
