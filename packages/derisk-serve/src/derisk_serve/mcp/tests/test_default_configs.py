"""Tests for default MCP configuration loader."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ..default_configs import (
    _copy_configs_to_mcp_dir,
    _read_last_commit,
    _resolve_env_vars,
    _resolve_headers,
    _sync_configs_to_db,
    _write_last_commit,
    clone_or_pull_repo,
    load_configs_from_directory,
    load_mcp_config_file,
    parse_mcp_server_entry,
    sync_default_mcps_from_repo,
)


# --------------- _resolve_env_vars ---------------


def test_resolve_env_vars_simple(monkeypatch):
    monkeypatch.setenv("TEST_KEY_123", "hello-world")
    result = _resolve_env_vars("Bearer ${TEST_KEY_123}")
    assert result == "Bearer hello-world"


def test_resolve_env_vars_multiple(monkeypatch):
    monkeypatch.setenv("A", "aaa")
    monkeypatch.setenv("B", "bbb")
    result = _resolve_env_vars("${A}-${B}")
    assert result == "aaa-bbb"


def test_resolve_env_vars_missing_keeps_placeholder(monkeypatch):
    monkeypatch.delenv("MISSING_VAR_XYZ", raising=False)
    result = _resolve_env_vars("Bearer ${MISSING_VAR_XYZ}")
    assert result == "Bearer ${MISSING_VAR_XYZ}"


def test_resolve_env_vars_no_placeholder():
    result = _resolve_env_vars("plain-string")
    assert result == "plain-string"


# --------------- _resolve_headers ---------------


def test_resolve_headers_none():
    assert _resolve_headers(None) is None


def test_resolve_headers_with_env(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "sk-12345")
    headers = {"Authorization": "Bearer ${MY_TOKEN}", "X-Custom": "static"}
    result = _resolve_headers(headers)
    assert result == {
        "Authorization": "Bearer sk-12345",
        "X-Custom": "static",
    }


# --------------- load_mcp_config_file ---------------


def test_load_valid_config_file():
    config = {
        "mcpServers": {
            "test-server": {
                "type": "sse",
                "description": "Test MCP server",
                "name": "Test Server",
                "baseUrl": "https://example.com/mcp/sse",
                "isActive": True,
            }
        }
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(config, f)
        f.flush()
        filepath = Path(f.name)

    try:
        data = load_mcp_config_file(filepath)
        assert "mcpServers" in data
        assert "test-server" in data["mcpServers"]
    finally:
        os.unlink(filepath)


def test_load_invalid_json():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        f.write("{invalid json")
        f.flush()
        filepath = Path(f.name)

    try:
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_mcp_config_file(filepath)
    finally:
        os.unlink(filepath)


def test_load_missing_mcp_servers_key():
    config = {"servers": {}}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(config, f)
        f.flush()
        filepath = Path(f.name)

    try:
        with pytest.raises(ValueError, match="missing required 'mcpServers'"):
            load_mcp_config_file(filepath)
    finally:
        os.unlink(filepath)


# --------------- parse_mcp_server_entry ---------------


def test_parse_sse_server_entry(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-key")
    server_config = {
        "type": "sse",
        "description": "Test SSE server",
        "name": "Test SSE",
        "baseUrl": "https://example.com/mcp/sse",
        "isActive": True,
        "headers": {"Authorization": "Bearer ${DASHSCOPE_API_KEY}"},
        "category": "cloud",
        "version": "1.0.0",
    }

    request = parse_mcp_server_entry("test-sse", server_config)

    assert request.mcp_code == "test-sse"
    assert request.name == "Test SSE"
    assert request.description == "Test SSE server"
    assert request.type == "http"  # "sse" maps to "http"
    assert request.sse_url == "https://example.com/mcp/sse"
    assert request.sse_headers == {"Authorization": "Bearer sk-test-key"}
    assert request.available is True
    assert request.category == "cloud"
    assert request.version == "1.0.0"


def test_parse_stdio_server_entry():
    server_config = {
        "type": "stdio",
        "description": "Local stdio server",
        "name": "Local Server",
        "stdioCmd": "python -m my_mcp_server",
        "isActive": False,
    }

    request = parse_mcp_server_entry("local-mcp", server_config)

    assert request.mcp_code == "local-mcp"
    assert request.type == "stdio"
    assert request.stdio_cmd == "python -m my_mcp_server"
    assert request.sse_url is None
    assert request.available is False


def test_parse_defaults_name_to_mcp_code():
    server_config = {
        "type": "sse",
        "description": "No name specified",
        "baseUrl": "https://example.com/sse",
    }

    request = parse_mcp_server_entry("my-code", server_config)
    assert request.name == "my-code"


def test_parse_defaults_is_active_true():
    server_config = {
        "type": "sse",
        "description": "No isActive specified",
        "baseUrl": "https://example.com/sse",
        "name": "test",
    }

    request = parse_mcp_server_entry("code", server_config)
    assert request.available is True


# --------------- load_configs_from_directory ---------------


def test_load_configs_from_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        config1 = {
            "mcpServers": {
                "server-a": {
                    "type": "sse",
                    "description": "Server A",
                    "name": "Server A",
                    "baseUrl": "https://a.example.com/sse",
                    "isActive": True,
                }
            }
        }
        config2 = {
            "mcpServers": {
                "server-b": {
                    "type": "sse",
                    "description": "Server B",
                    "name": "Server B",
                    "baseUrl": "https://b.example.com/sse",
                    "isActive": True,
                }
            }
        }
        with open(os.path.join(tmpdir, "a.json"), "w") as f:
            json.dump(config1, f)
        with open(os.path.join(tmpdir, "b.json"), "w") as f:
            json.dump(config2, f)

        results = load_configs_from_directory(Path(tmpdir))

        assert len(results) == 2
        codes = {r.mcp_code for r in results}
        assert codes == {"server-a", "server-b"}


def test_load_configs_from_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        results = load_configs_from_directory(Path(tmpdir))
        assert results == []


def test_load_configs_from_nonexistent_dir():
    results = load_configs_from_directory(Path("/nonexistent/dir/xxx"))
    assert results == []


def test_load_configs_skips_bad_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        good = {
            "mcpServers": {
                "good-server": {
                    "type": "sse",
                    "description": "Good",
                    "name": "Good",
                    "baseUrl": "https://good.example.com/sse",
                }
            }
        }
        with open(os.path.join(tmpdir, "good.json"), "w") as f:
            json.dump(good, f)
        with open(os.path.join(tmpdir, "bad.json"), "w") as f:
            f.write("{bad json!!!")

        results = load_configs_from_directory(Path(tmpdir))
        assert len(results) == 1
        assert results[0].mcp_code == "good-server"


def test_load_configs_multiple_servers_in_one_file():
    """Test that a single file can define multiple MCP servers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "mcpServers": {
                "server-1": {
                    "type": "sse",
                    "description": "Server 1",
                    "name": "Server 1",
                    "baseUrl": "https://s1.example.com/sse",
                },
                "server-2": {
                    "type": "sse",
                    "description": "Server 2",
                    "name": "Server 2",
                    "baseUrl": "https://s2.example.com/sse",
                },
            }
        }
        with open(os.path.join(tmpdir, "multi.json"), "w") as f:
            json.dump(config, f)

        results = load_configs_from_directory(Path(tmpdir))
        assert len(results) == 2


# --------------- clone_or_pull_repo ---------------


@patch("derisk_serve.mcp.default_configs.git")
def test_clone_or_pull_repo_fresh_clone(mock_git_module):
    """Test cloning a new repo when no local cache exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, ".git_cache")
        repo_url = "https://github.com/derisk-ai/derisk-mcps"

        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = "abc123def456"
        mock_git_module.Repo.clone_from.return_value = mock_repo

        repo_path, commit_id = clone_or_pull_repo(
            repo_url, cache_dir, branch="main"
        )

        # Should have called clone_from
        mock_git_module.Repo.clone_from.assert_called_once()
        call_args = mock_git_module.Repo.clone_from.call_args
        assert call_args[0][0] == repo_url
        assert (
            "main" in call_args[1].values()
            or call_args[1].get("branch") == "main"
        )

        # Should return a path under cache_dir using MD5 hash
        expected_name = hashlib.md5(repo_url.encode()).hexdigest()[:16]
        assert repo_path == os.path.join(cache_dir, expected_name)

        # Should return the commit hash
        assert commit_id == "abc123def456"


@patch("derisk_serve.mcp.default_configs.git")
def test_clone_or_pull_repo_existing_pull(mock_git_module):
    """Test pulling updates when .git_cache already has the repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, ".git_cache")
        repo_url = "https://github.com/derisk-ai/derisk-mcps"

        # Create a fake .git directory to simulate existing clone
        repo_name = hashlib.md5(repo_url.encode()).hexdigest()[:16]
        repo_path = os.path.join(cache_dir, repo_name)
        os.makedirs(os.path.join(repo_path, ".git"))

        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = "new_commit_sha"
        mock_git_module.Repo.return_value = mock_repo

        result_path, commit_id = clone_or_pull_repo(
            repo_url, cache_dir, branch="main"
        )

        # Should have called Repo() for existing repo, not clone_from
        mock_git_module.Repo.assert_called_once_with(repo_path)
        mock_repo.git.checkout.assert_called_once_with("main")
        mock_repo.remotes.origin.pull.assert_called_once_with("main")

        # Should return commit hash
        assert commit_id == "new_commit_sha"
        assert result_path == repo_path


@patch("derisk_serve.mcp.default_configs.git")
def test_clone_or_pull_repo_pull_fail_reclones(mock_git_module):
    """Test that pull failure triggers a re-clone."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, ".git_cache")
        repo_url = "https://github.com/derisk-ai/derisk-mcps"

        repo_name = hashlib.md5(repo_url.encode()).hexdigest()[:16]
        repo_path = os.path.join(cache_dir, repo_name)
        os.makedirs(os.path.join(repo_path, ".git"))

        # Make Repo() raise on pull to trigger re-clone
        mock_existing = MagicMock()
        mock_existing.remotes.origin.pull.side_effect = Exception("pull fail")
        mock_git_module.Repo.return_value = mock_existing

        mock_new_repo = MagicMock()
        mock_new_repo.head.commit.hexsha = "fresh_clone_sha"
        mock_git_module.Repo.clone_from.return_value = mock_new_repo

        result_path, commit_id = clone_or_pull_repo(
            repo_url, cache_dir, branch="main"
        )

        # Should have re-cloned
        mock_git_module.Repo.clone_from.assert_called_once()
        assert commit_id == "fresh_clone_sha"


# --------------- _copy_configs_to_mcp_dir ---------------


def test_copy_configs_to_mcp_dir():
    """Test copying JSON files from repo servers/ to mcp_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = os.path.join(tmpdir, "repo")
        mcp_dir = os.path.join(tmpdir, "mcp")

        # Create a fake repo with servers/ subdir
        servers_dir = os.path.join(repo_path, "servers")
        os.makedirs(servers_dir)
        config = {
            "mcpServers": {
                "test-server": {
                    "type": "sse",
                    "description": "Test",
                    "baseUrl": "https://test.example.com/sse",
                }
            }
        }
        with open(os.path.join(servers_dir, "test.json"), "w") as f:
            json.dump(config, f)
        # Also create a non-JSON file that should be ignored
        with open(os.path.join(servers_dir, "README.md"), "w") as f:
            f.write("# Readme")

        copied = _copy_configs_to_mcp_dir(repo_path, mcp_dir, "servers")

        assert copied == 1
        assert os.path.isfile(os.path.join(mcp_dir, "test.json"))
        assert not os.path.isfile(os.path.join(mcp_dir, "README.md"))

        with open(os.path.join(mcp_dir, "test.json")) as f:
            data = json.load(f)
        assert "test-server" in data["mcpServers"]


def test_copy_configs_missing_servers_subdir():
    """Test that missing servers/ subdir returns 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = os.path.join(tmpdir, "repo")
        mcp_dir = os.path.join(tmpdir, "mcp")
        os.makedirs(repo_path)

        copied = _copy_configs_to_mcp_dir(repo_path, mcp_dir, "servers")
        assert copied == 0


# --------------- commit hash tracking ---------------


def test_write_and_read_last_commit():
    """Test writing and reading the .last_commit file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_last_commit(tmpdir, "abc123def456")
        result = _read_last_commit(tmpdir)
        assert result == "abc123def456"


def test_read_last_commit_missing():
    """Test reading when no .last_commit file exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _read_last_commit(tmpdir)
        assert result is None


def test_write_last_commit_creates_dir():
    """Test that _write_last_commit creates the directory if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "new_dir")
        _write_last_commit(mcp_dir, "sha123")
        assert _read_last_commit(mcp_dir) == "sha123"


# --------------- sync_default_mcps_from_repo ---------------


def test_sync_from_repo_empty_url():
    """Test that an empty repo URL skips syncing."""
    mock_dao = MagicMock()
    result = sync_default_mcps_from_repo(
        dao=mock_dao,
        repo_url="",
        mcp_dir="/tmp/test",
        git_cache_dir="/tmp/test/.git_cache",
    )
    assert result == 0


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_with_configs(mock_clone):
    """Test end-to-end sync from a mocked repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")

        # Simulate a cloned repo with servers/ subdir
        repo_path = os.path.join(git_cache_dir, "fakerepo")
        servers_dir = os.path.join(repo_path, "servers")
        os.makedirs(servers_dir)
        config = {
            "mcpServers": {
                "test-server": {
                    "type": "sse",
                    "description": "Test",
                    "name": "Test Server",
                    "baseUrl": "https://test.example.com/sse",
                    "isActive": True,
                }
            }
        }
        with open(os.path.join(servers_dir, "test.json"), "w") as f:
            json.dump(config, f)

        mock_clone.return_value = (repo_path, "commit_abc123")

        # Mock DAO
        mock_dao = MagicMock()
        mock_dao.get_one.return_value = None  # No existing record
        mock_entity = MagicMock()
        mock_dao.from_request.return_value = mock_entity
        mock_session = MagicMock()
        mock_dao.get_raw_session.return_value = mock_session

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
        )

        assert result == 1
        mock_dao.from_request.assert_called_once()
        mock_session.add.assert_called_once_with(mock_entity)
        mock_session.commit.assert_called_once()

        # Verify JSON was copied to mcp_dir
        assert os.path.isfile(os.path.join(mcp_dir, "test.json"))

        # Verify commit hash was recorded
        assert _read_last_commit(mcp_dir) == "commit_abc123"


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_skips_unchanged_commit(mock_clone):
    """Test that unchanged commit hash skips re-syncing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")

        # Write a .last_commit to simulate a previous sync
        _write_last_commit(mcp_dir, "same_commit_sha")

        mock_clone.return_value = ("/some/path", "same_commit_sha")

        mock_dao = MagicMock()

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
        )

        # Should skip since commit hash matches
        assert result == 0
        mock_dao.get_one.assert_not_called()


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_resync_on_new_commit(mock_clone):
    """Test that a new commit hash triggers re-syncing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")

        # Write old commit hash
        _write_last_commit(mcp_dir, "old_commit_sha")

        # Simulate repo with new commit
        repo_path = os.path.join(git_cache_dir, "fakerepo")
        servers_dir = os.path.join(repo_path, "servers")
        os.makedirs(servers_dir)
        config = {
            "mcpServers": {
                "server-x": {
                    "type": "sse",
                    "description": "X",
                    "name": "Server X",
                    "baseUrl": "https://x.example.com/sse",
                }
            }
        }
        with open(os.path.join(servers_dir, "x.json"), "w") as f:
            json.dump(config, f)

        mock_clone.return_value = (repo_path, "new_commit_sha")

        mock_dao = MagicMock()
        mock_dao.get_one.return_value = None
        mock_entity = MagicMock()
        mock_dao.from_request.return_value = mock_entity
        mock_session = MagicMock()
        mock_dao.get_raw_session.return_value = mock_session

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
        )

        assert result == 1
        # Verify commit hash was updated
        assert _read_last_commit(mcp_dir) == "new_commit_sha"


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_overwrite_ignores_commit_check(mock_clone):
    """Test that overwrite=True re-syncs even with same commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")

        _write_last_commit(mcp_dir, "same_sha")

        repo_path = os.path.join(git_cache_dir, "fakerepo")
        servers_dir = os.path.join(repo_path, "servers")
        os.makedirs(servers_dir)
        config = {
            "mcpServers": {
                "srv": {
                    "type": "sse",
                    "description": "S",
                    "name": "S",
                    "baseUrl": "https://s.example.com/sse",
                }
            }
        }
        with open(os.path.join(servers_dir, "s.json"), "w") as f:
            json.dump(config, f)

        mock_clone.return_value = (repo_path, "same_sha")

        mock_dao = MagicMock()
        mock_dao.get_one.return_value = MagicMock()  # existing record
        mock_dao.update = MagicMock()

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
            overwrite=True,
        )

        # Should sync even with same commit because overwrite=True
        assert result == 1
        mock_dao.update.assert_called_once()


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_skips_existing(mock_clone):
    """Test that existing MCP records are not overwritten by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")

        repo_path = os.path.join(git_cache_dir, "fakerepo")
        servers_dir = os.path.join(repo_path, "servers")
        os.makedirs(servers_dir)
        config = {
            "mcpServers": {
                "existing-server": {
                    "type": "sse",
                    "description": "Existing",
                    "name": "Existing Server",
                    "baseUrl": "https://existing.example.com/sse",
                }
            }
        }
        with open(os.path.join(servers_dir, "existing.json"), "w") as f:
            json.dump(config, f)

        mock_clone.return_value = (repo_path, "some_commit")

        # Mock DAO with existing record
        mock_dao = MagicMock()
        mock_dao.get_one.return_value = MagicMock()  # Existing record found

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
            overwrite=False,
        )

        assert result == 0  # Nothing synced
        mock_dao.from_request.assert_not_called()


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_clone_failure_falls_back_to_local(mock_clone):
    """Test that clone failure falls back to existing local files."""
    mock_clone.side_effect = Exception("Network error")

    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")
        os.makedirs(mcp_dir)

        # Pre-existing local config (from a previous successful sync)
        config = {
            "mcpServers": {
                "cached-server": {
                    "type": "sse",
                    "description": "Cached",
                    "name": "Cached Server",
                    "baseUrl": "https://cached.example.com/sse",
                }
            }
        }
        with open(os.path.join(mcp_dir, "cached.json"), "w") as f:
            json.dump(config, f)

        mock_dao = MagicMock()
        mock_dao.get_one.return_value = None
        mock_entity = MagicMock()
        mock_dao.from_request.return_value = mock_entity
        mock_session = MagicMock()
        mock_dao.get_raw_session.return_value = mock_session

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
        )

        # Should fall back to loading from local mcp_dir
        assert result == 1
        mock_dao.from_request.assert_called_once()


@patch("derisk_serve.mcp.default_configs.clone_or_pull_repo")
def test_sync_from_repo_clone_failure_no_local_files(mock_clone):
    """Test that clone failure with no local files returns 0."""
    mock_clone.side_effect = Exception("Network error")

    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_dir = os.path.join(tmpdir, "mcp")
        git_cache_dir = os.path.join(tmpdir, "mcp", ".git_cache")
        os.makedirs(mcp_dir)

        mock_dao = MagicMock()

        result = sync_default_mcps_from_repo(
            dao=mock_dao,
            repo_url="https://github.com/derisk-ai/derisk-mcps",
            mcp_dir=mcp_dir,
            git_cache_dir=git_cache_dir,
        )

        assert result == 0


# --------------- _sync_configs_to_db ---------------


def test_sync_configs_to_db_insert():
    """Test inserting new configs to DB."""
    from ..api.schemas import ServeRequest

    configs = [
        ServeRequest(
            mcp_code="new-server",
            name="New Server",
            description="A new server",
            type="http",
            sse_url="https://new.example.com/sse",
            available=True,
        )
    ]

    mock_dao = MagicMock()
    mock_dao.get_one.return_value = None
    mock_entity = MagicMock()
    mock_dao.from_request.return_value = mock_entity
    mock_session = MagicMock()
    mock_dao.get_raw_session.return_value = mock_session

    result = _sync_configs_to_db(mock_dao, configs, overwrite=False)

    assert result == 1
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_sync_configs_to_db_skip_existing():
    """Test that existing configs are skipped when overwrite=False."""
    from ..api.schemas import ServeRequest

    configs = [
        ServeRequest(
            mcp_code="existing",
            name="Existing",
            description="Already there",
            type="http",
        )
    ]

    mock_dao = MagicMock()
    mock_dao.get_one.return_value = MagicMock()  # Already exists

    result = _sync_configs_to_db(mock_dao, configs, overwrite=False)
    assert result == 0


def test_sync_configs_to_db_overwrite():
    """Test that existing configs are updated when overwrite=True."""
    from ..api.schemas import ServeRequest

    configs = [
        ServeRequest(
            mcp_code="existing",
            name="Updated Name",
            description="Updated description",
            type="http",
            sse_url="https://updated.example.com/sse",
        )
    ]

    mock_dao = MagicMock()
    mock_dao.get_one.return_value = MagicMock()  # Already exists

    result = _sync_configs_to_db(mock_dao, configs, overwrite=True)

    assert result == 1
    mock_dao.update.assert_called_once()
