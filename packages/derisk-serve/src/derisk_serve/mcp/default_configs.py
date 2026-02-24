"""Default MCP server configuration loader.

Loads MCP server configurations from a remote git repository
(https://github.com/derisk-ai/derisk-mcps) following the same pattern
as the skill module:

1. Clone (or pull) the repo into ``pilot/data/mcp/.git_cache/<md5-hash>/``
2. Compare the HEAD commit hash to detect changes
3. Copy JSON config files from the ``servers/`` subdirectory into
   ``pilot/data/mcp/``
4. Sync configs into the database (idempotent by mcp_code)

The final layout is::

    pilot/data/mcp/
        .git_cache/
            <md5(repo_url)[:16]>/      # persistent git clone
                .git/
                servers/
                    alibaba-cloud-ops.json
                    ...
        alibaba-cloud-ops.json         # copied from servers/
        alibaba-cloud-monitoring.json
        ...
"""

import hashlib
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .api.schemas import ServeRequest

logger = logging.getLogger(__name__)

# Environment variable pattern: ${ENV_VAR_NAME}
_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with actual environment variable values.

    Args:
        value: String potentially containing ${ENV_VAR} placeholders.

    Returns:
        String with placeholders replaced by environment variable values.
        If an env var is not set, the placeholder is left unchanged.
    """

    def _replace(match: re.Match) -> str:
        env_name = match.group(1)
        env_value = os.environ.get(env_name)
        if env_value is None:
            logger.warning(
                "Environment variable '%s' is not set, "
                "placeholder '${%s}' will be kept as-is",
                env_name,
                env_name,
            )
            return match.group(0)
        return env_value

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_headers(headers: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Resolve environment variable placeholders in header values."""
    if not headers:
        return headers
    return {key: _resolve_env_vars(val) for key, val in headers.items()}


# ---------------------------------------------------------------------------
# Git repository operations (following skill service pattern)
# ---------------------------------------------------------------------------


def clone_or_pull_repo(
    repo_url: str,
    git_cache_dir: str,
    branch: str = "main",
) -> Tuple[str, str]:
    """Clone or update a git repository to a local cache directory.

    Uses the same pattern as the skill service: MD5 hash the repo URL to
    generate a unique directory name under ``git_cache_dir``.

    Args:
        repo_url: The remote git repository URL.
        git_cache_dir: The local directory for git cache
                       (e.g. pilot/data/mcp/.git_cache).
        branch: The git branch to checkout.

    Returns:
        A tuple of (repo_path, commit_id):
        - repo_path: The absolute path to the cloned repository.
        - commit_id: The HEAD commit SHA hex string.
    """
    import git

    os.makedirs(git_cache_dir, exist_ok=True)

    # Generate unique directory name from URL (same approach as skill service)
    repo_name = hashlib.md5(repo_url.encode()).hexdigest()[:16]
    repo_path = os.path.join(git_cache_dir, repo_name)

    if os.path.exists(repo_path) and os.path.exists(
        os.path.join(repo_path, ".git")
    ):
        logger.info("Pulling updates from existing MCP config repo at %s", repo_path)
        try:
            repo = git.Repo(repo_path)
            repo.git.checkout(branch)
            repo.remotes.origin.pull(branch)
        except Exception as e:
            logger.warning(
                "Failed to pull MCP config repo, re-cloning: %s", e
            )
            shutil.rmtree(repo_path, ignore_errors=True)
            repo = git.Repo.clone_from(repo_url, repo_path, branch=branch)
    else:
        logger.info("Cloning MCP config repo %s to %s", repo_url, repo_path)
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        repo = git.Repo.clone_from(repo_url, repo_path, branch=branch)

    # Get current commit hash for staleness checking
    commit_id = repo.head.commit.hexsha
    logger.info("MCP config repo at commit %s", commit_id)

    return repo_path, commit_id


def _copy_configs_to_mcp_dir(
    repo_path: str,
    mcp_dir: str,
    servers_subdir: str = "servers",
) -> int:
    """Copy JSON config files from the cloned repo to the MCP directory.

    Copies ``<repo_path>/<servers_subdir>/*.json`` directly into ``mcp_dir``.

    Args:
        repo_path: Path to the cloned repository.
        mcp_dir: Target directory (e.g. pilot/data/mcp).
        servers_subdir: Subdirectory inside the repo containing JSON configs.

    Returns:
        Number of JSON files copied.
    """
    os.makedirs(mcp_dir, exist_ok=True)

    src_dir = os.path.join(repo_path, servers_subdir)
    if not os.path.isdir(src_dir):
        logger.warning(
            "Subdirectory '%s' not found in cloned repo at %s, "
            "no config files to copy",
            servers_subdir,
            repo_path,
        )
        return 0

    copied = 0
    for filename in os.listdir(src_dir):
        if filename.endswith(".json"):
            src_path = os.path.join(src_dir, filename)
            dst_path = os.path.join(mcp_dir, filename)
            shutil.copy2(src_path, dst_path)
            copied += 1
            logger.debug("Copied %s -> %s", src_path, dst_path)

    logger.info(
        "Copied %d JSON config file(s) from %s/%s to %s",
        copied,
        repo_path,
        servers_subdir,
        mcp_dir,
    )
    return copied


# ---------------------------------------------------------------------------
# Commit hash tracking (for staleness checking)
# ---------------------------------------------------------------------------

_COMMIT_HASH_FILE = ".last_commit"


def _read_last_commit(mcp_dir: str) -> Optional[str]:
    """Read the last synced commit hash from the tracking file."""
    path = os.path.join(mcp_dir, _COMMIT_HASH_FILE)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None


def _write_last_commit(mcp_dir: str, commit_id: str) -> None:
    """Write the current commit hash to the tracking file."""
    os.makedirs(mcp_dir, exist_ok=True)
    path = os.path.join(mcp_dir, _COMMIT_HASH_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(commit_id)


# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------


def load_mcp_config_file(filepath: Path) -> Dict[str, Any]:
    """Load and validate a single MCP server JSON config file.

    Args:
        filepath: Path to the JSON configuration file.

    Returns:
        Parsed JSON dict with the config.

    Raises:
        ValueError: If the file is not valid JSON or is missing required fields.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}") from e

    if "mcpServers" not in data:
        raise ValueError(
            f"Config file {filepath} is missing required 'mcpServers' key"
        )

    if not isinstance(data["mcpServers"], dict):
        raise ValueError(f"'mcpServers' in {filepath} must be a JSON object")

    return data


def parse_mcp_server_entry(
    mcp_code: str, server_config: Dict[str, Any]
) -> ServeRequest:
    """Parse a single MCP server config entry into a ServeRequest.

    Args:
        mcp_code: The server identifier key (used as mcp_code).
        server_config: The server configuration dict.

    Returns:
        A ServeRequest populated from the config.
    """
    server_type = server_config.get("type", "sse")

    # Resolve environment variables in headers
    raw_headers = server_config.get("headers")
    resolved_headers = _resolve_headers(raw_headers)

    # Resolve environment variables in token
    raw_token = server_config.get("token")
    resolved_token = _resolve_env_vars(raw_token) if raw_token else None

    return ServeRequest(
        mcp_code=mcp_code,
        name=server_config.get("name", mcp_code),
        description=server_config.get("description", ""),
        type="http" if server_type == "sse" else server_type,
        sse_url=server_config.get("baseUrl"),
        sse_headers=resolved_headers,
        token=resolved_token,
        stdio_cmd=server_config.get("stdioCmd"),
        author=server_config.get("author"),
        email=server_config.get("email"),
        version=server_config.get("version"),
        icon=server_config.get("icon"),
        category=server_config.get("category"),
        available=server_config.get("isActive", True),
    )


def load_configs_from_directory(config_dir: Path) -> List[ServeRequest]:
    """Load all MCP server configurations from a local directory.

    Args:
        config_dir: Path to the directory containing JSON config files.

    Returns:
        List of ServeRequest objects representing MCP servers.
    """
    if not config_dir.is_dir():
        logger.warning("MCP config directory does not exist: %s", config_dir)
        return []

    results: List[ServeRequest] = []
    json_files = sorted(config_dir.glob("*.json"))

    if not json_files:
        logger.info("No JSON config files found in %s", config_dir)
        return []

    for filepath in json_files:
        try:
            data = load_mcp_config_file(filepath)
            for mcp_code, server_config in data["mcpServers"].items():
                try:
                    request = parse_mcp_server_entry(mcp_code, server_config)
                    results.append(request)
                    logger.info(
                        "Loaded MCP config: %s (%s) from %s",
                        mcp_code,
                        request.name,
                        filepath.name,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to parse MCP server '%s' from %s: %s",
                        mcp_code,
                        filepath,
                        e,
                    )
        except Exception as e:
            logger.error("Failed to load MCP config file %s: %s", filepath, e)

    logger.info("Loaded %d MCP server configuration(s)", len(results))
    return results


# ---------------------------------------------------------------------------
# Public API: sync from remote git repo
# ---------------------------------------------------------------------------


def sync_default_mcps_from_repo(
    dao,
    repo_url: str,
    branch: str = "main",
    mcp_dir: str = "",
    git_cache_dir: str = "",
    servers_subdir: str = "servers",
    overwrite: bool = False,
) -> int:
    """Clone the MCP config repo from GitHub and sync configs into the database.

    This is the main entry point called during application startup.  It follows
    the same pattern as the skill module:

    1. Clone (or pull) the remote repo into ``.git_cache/<md5-hash>/``.
    2. Compare the HEAD commit hash against the last synced value.  If they
       match and ``overwrite`` is False, skip re-syncing.
    3. Copy JSON config files from ``servers/`` into ``mcp_dir``.
    4. Load configs from ``mcp_dir`` and insert/update in the database.
    5. Record the commit hash for next-time staleness checking.

    Args:
        dao: The ServeDao instance for database operations.
        repo_url: Remote git repository URL
                  (default: https://github.com/derisk-ai/derisk-mcps).
        branch: Git branch to use.
        mcp_dir: Local directory for MCP config files
                 (default: pilot/data/mcp).
        git_cache_dir: Local directory for git cache
                       (default: pilot/data/mcp/.git_cache).
        servers_subdir: Subdirectory inside the repo containing JSON configs.
        overwrite: Whether to overwrite existing DB records.

    Returns:
        Number of MCP servers inserted or updated.
    """
    if not repo_url:
        logger.info("MCP config repo URL is empty, skipping sync")
        return 0

    # Step 1: Clone or pull the remote repository
    commit_id = None
    try:
        repo_path, commit_id = clone_or_pull_repo(
            repo_url, git_cache_dir, branch
        )
    except Exception as e:
        logger.error(
            "Failed to clone/pull MCP config repo '%s': %s", repo_url, e
        )
        # Fall back to loading from existing local files in mcp_dir
        configs = load_configs_from_directory(Path(mcp_dir))
        if not configs:
            return 0
        return _sync_configs_to_db(dao, configs, overwrite)

    # Step 2: Check commit hash for staleness
    last_commit = _read_last_commit(mcp_dir)
    if last_commit == commit_id and not overwrite:
        logger.info(
            "MCP config repo unchanged (commit %s), skipping sync",
            commit_id[:12],
        )
        return 0

    # Step 3: Copy servers/*.json into mcp_dir
    _copy_configs_to_mcp_dir(repo_path, mcp_dir, servers_subdir)

    # Step 4: Load configs from mcp_dir and sync to database
    configs = load_configs_from_directory(Path(mcp_dir))
    if not configs:
        logger.info("No MCP configs found in %s", mcp_dir)
        return 0

    synced = _sync_configs_to_db(dao, configs, overwrite)

    # Step 5: Record the commit hash
    if commit_id:
        _write_last_commit(mcp_dir, commit_id)

    return synced


def sync_default_mcps_from_local(
    dao,
    config_dir: str,
    overwrite: bool = False,
) -> int:
    """Load MCP configs from a local directory and sync to database.

    Fallback for environments where git is not available or when
    configs are pre-deployed locally.

    Args:
        dao: The ServeDao instance for database operations.
        config_dir: Local directory containing JSON config files.
        overwrite: Whether to overwrite existing DB records.

    Returns:
        Number of MCP servers inserted or updated.
    """
    configs = load_configs_from_directory(Path(config_dir))
    if not configs:
        return 0
    return _sync_configs_to_db(dao, configs, overwrite)


def _sync_configs_to_db(
    dao,
    configs: List[ServeRequest],
    overwrite: bool = False,
) -> int:
    """Sync a list of MCP server configs into the database.

    This function is idempotent. By default it only inserts MCP servers that
    do not already exist in the database (matched by mcp_code). Set
    ``overwrite=True`` to update existing records as well.

    Args:
        dao: The ServeDao instance for database operations.
        configs: List of ServeRequest objects to sync.
        overwrite: Whether to overwrite existing DB records.

    Returns:
        Number of MCP servers inserted or updated.
    """
    synced = 0
    for request in configs:
        try:
            # Check if this MCP already exists
            existing = dao.get_one({"mcp_code": request.mcp_code})
            if existing and not overwrite:
                logger.debug(
                    "MCP '%s' already exists in DB, skipping "
                    "(set overwrite=True to update)",
                    request.mcp_code,
                )
                continue

            if existing and overwrite:
                # Update existing record
                update_dict = request.to_dict(exclude_none=True)
                update_dict.pop("mcp_code", None)
                update_dict.pop("gmt_created", None)
                update_dict.pop("gmt_modified", None)
                if "sse_headers" in update_dict and isinstance(
                    update_dict["sse_headers"], dict
                ):
                    update_dict["sse_headers"] = json.dumps(
                        update_dict["sse_headers"]
                    )
                dao.update({"mcp_code": request.mcp_code}, update_dict)
                logger.info("Updated default MCP '%s' in DB", request.mcp_code)
            else:
                # Create new record
                entity = dao.from_request(request)
                session = dao.get_raw_session()
                try:
                    session.add(entity)
                    session.commit()
                    logger.info(
                        "Inserted default MCP '%s' (%s) into DB",
                        request.mcp_code,
                        request.name,
                    )
                except Exception:
                    session.rollback()
                    raise
                finally:
                    session.close()

            synced += 1
        except Exception as e:
            logger.error(
                "Failed to sync default MCP '%s' to DB: %s",
                request.mcp_code,
                e,
            )

    logger.info(
        "Default MCP sync complete: %d/%d server(s) synced",
        synced,
        len(configs),
    )
    return synced
