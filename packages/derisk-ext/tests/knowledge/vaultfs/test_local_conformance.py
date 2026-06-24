"""Pytest entry for LocalVaultFS conformance (RFC 002 §6).

Runs the full conformance suite against LocalVaultFS in a tmp dir.
This is the baseline every other backend (DistributedVaultFS, future
third-party) must also pass.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import pytest_asyncio

from derisk_ext.knowledge.vaultfs import LocalVaultFS
from derisk_ext.knowledge.vaultfs.conformance import run_conformance


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    from derisk.knowledge.types import new_space_id

    root = tmp_path / "test_space"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


@pytest.mark.asyncio
async def test_local_vaultfs_conformance(vault):
    """LocalVaultFS must pass the full conformance suite."""
    await run_conformance(vault)


@pytest.mark.asyncio
async def test_local_vaultfs_backend_type(vault):
    assert vault.backend_type == "local"


@pytest.mark.asyncio
async def test_local_vaultfs_creates_directory_structure(vault):
    """initialize() must create raw/, wiki/, .ks/ dirs."""
    root = vault.root
    assert (root / "raw" / "sources").is_dir()
    assert (root / "raw" / "convos").is_dir()
    assert (root / "raw" / "clips").is_dir()
    assert (root / "wiki").is_dir()
    assert (root / ".ks").is_dir()
    assert (root / ".ks" / "index.db").is_file()
