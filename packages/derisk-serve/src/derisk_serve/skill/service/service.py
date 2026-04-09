import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from typing import List, Optional, Any, Dict
from pathlib import Path

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao, db
from derisk.util.pagination_utils import PaginationResult
from derisk_serve.core import BaseService
from fastapi import UploadFile

from ..api.schemas import (
    SkillRequest,
    SkillResponse,
    SkillQueryFilter,
    SkillSyncTaskRequest,
    SkillSyncTaskResponse,
)
from ..config import ServeConfig
from ..models.models import SkillDao, SkillEntity

# Use a new constant for the service component name
SKILL_SERVICE_COMPONENT_NAME = "serve_skill_service"

logger = logging.getLogger(__name__)

# Store background tasks by task_id
_background_tasks: Dict[str, threading.Thread] = {}


class Service(BaseService[SkillEntity, SkillRequest, SkillResponse]):
    """The service class for Skill"""

    name = SKILL_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig, dao: Optional[SkillDao] = None
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: SkillDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or SkillDao(self._serve_config)
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao[SkillEntity, SkillRequest, SkillResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    def create(self, request: SkillRequest) -> SkillResponse:
        """Create a new Skill entity

        Args:
            request (SkillRequest): The request

        Returns:
            SkillResponse: The response
        """
        if not request.skill_code:
            import uuid

            request.skill_code = str(uuid.uuid4())

        # Set default path to skill_dir/skill_code if not provided
        if not request.path:
            project_skill_dir = self._serve_config.get_project_skill_dir()
            request.path = os.path.join(project_skill_dir, request.skill_code)

            logger.info(
                f"Skill '{request.name}' path is empty, "
                f"using default path '{request.path}'"
            )

        existing_skill = self.dao.get_one({"skill_code": request.skill_code})
        if existing_skill:
            logger.info(f"Skill {request.skill_code} already exists, updating instead")
            return self.update(request)

        return self.dao.create(request)

    def update(self, request: SkillRequest) -> SkillResponse:
        """Update a Skill entity

        Args:
            request (SkillRequest): The request

        Returns:
            SkillResponse: The response
        """
        # Build the query request from the request
        query_request = {"skill_code": request.skill_code}

        # Set default path if not provided
        if not request.path:
            existing = self.dao.get_one({"skill_code": request.skill_code})
            if existing and existing.path:
                request.path = existing.path
            else:
                project_skill_dir = self._serve_config.get_project_skill_dir()
                request.path = os.path.join(project_skill_dir, request.skill_code)
                logger.info(
                    f"Skill '{request.skill_code}' update path is empty, "
                    f"using default path '{request.path}'"
                )

        logger.info(
            f"Updating skill {request.skill_code} with auto_sync={request.auto_sync}"
        )

        # Pass the Pydantic model directly to dao.update, which will use model_to_dict
        return self.dao.update(query_request, update_request=request)

    def get(self, request: SkillRequest) -> Optional[SkillResponse]:
        """Get a Skill entity

        Args:
            request (SkillRequest): The request

        Returns:
            SkillResponse: The response
        """
        # Build the query request from the request
        query_request = request
        return self.dao.get_one(query_request)

    def get_by_skill_code(self, skill_code: str) -> Optional[SkillResponse]:
        """Get a Skill entity by skill_code only

        Args:
            skill_code (str): The skill code

        Returns:
            SkillResponse: The response or None if not found
        """
        # Use dict query to avoid including default values from SkillRequest
        return self.dao.get_one({"skill_code": skill_code})

    def delete(self, request: SkillRequest) -> None:
        """Delete a Skill entity

        Args:
            request (SkillRequest): The request
        """

        # Build the query request from the request
        query_request = request
        self.dao.delete(query_request)

    def get_list(self, request: SkillRequest) -> List[SkillResponse]:
        """Get a list of Skill entities

        Args:
            request (SkillRequest): The request

        Returns:
            List[SkillResponse]: The response
        """
        # Build the query request from the request
        query_request = request
        return self.dao.get_list(query_request)

    def get_list_by_page(
        self, request: SkillRequest, page: int, page_size: int
    ) -> PaginationResult[SkillResponse]:
        """Get a list of Skill entities by page

        Args:
            request (SkillRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            PaginationResult: The response
        """
        query_request = request
        return self.dao.get_list_page(query_request, page, page_size)

    def filter_list_page(
        self,
        query_request: SkillQueryFilter,
        page: int,
        page_size: int,
        desc_order_column: Optional[str] = None,
    ) -> PaginationResult[SkillResponse]:
        """Get a page of entity objects.

        Args:
            query_request (SkillQueryFilter): The request schema object or dict for query.
            page (int): The page number.
            page_size (int): The page size.

        Returns:
            PaginationResult: The pagination result.
        """
        return self.dao.filter_list_page(
            query_request, page, page_size, desc_order_column
        )

    async def sync_from_git(
        self, repo_url: str, branch: str = "main", force_update: bool = False
    ) -> List[SkillResponse]:
        """Sync skills from a git repository

        Args:
            repo_url (str): The git repository URL
            branch (str): The git branch
            force_update (bool): Whether to force update existing skills

        Returns:
            List[SkillResponse]: List of synced skills
        """
        logger.info(
            f"Syncing skills from {repo_url} branch {branch}, force_update={force_update}"
        )

        import git

        synced_skills: List[SkillResponse] = []

        try:
            # Use the existing serve_config
            project_skill_dir = self._serve_config.get_project_skill_dir()
            temp_git_dir = self._serve_config.get_temp_git_dir()
            sandbox_skill_dir = self._serve_config.get_sandbox_skill_dir()

            # Ensure directories exist
            os.makedirs(project_skill_dir, exist_ok=True)
            os.makedirs(temp_git_dir, exist_ok=True)

            # Generate a unique repo name from URL
            repo_name = hashlib.md5(repo_url.encode()).hexdigest()[:16]
            repo_path = os.path.join(temp_git_dir, repo_name)

            # Clone or pull the repository
            if os.path.exists(repo_path) and os.path.exists(
                os.path.join(repo_path, ".git")
            ):
                logger.info(f"Pulling updates from existing repo at {repo_path}")
                repo = git.Repo(repo_path)
                repo.git.checkout(branch)
                repo.remotes.origin.pull(branch)
            else:
                logger.info(f"Cloning repository to {repo_path}")
                if os.path.exists(repo_path):
                    shutil.rmtree(repo_path)
                repo = git.Repo.clone_from(repo_url, repo_path, branch=branch)

            # Get current commit ID
            commit_id = repo.head.commit.hexsha

            # Scan for skill directories (typically /skills subdirectory or root)
            skill_dirs = self._find_skill_directories(repo_path)

            logger.info(f"Found {len(skill_dirs)} skill directories")

            for skill_path in skill_dirs:
                try:
                    # Parse SKILL.md
                    skill_md_path = os.path.join(skill_path, "SKILL.md")
                    if not os.path.exists(skill_md_path):
                        logger.warning(f"SKILL.md not found in {skill_path}, skipping")
                        continue

                    skill_meta = self._parse_skill_md(skill_md_path)
                    if not skill_meta or "name" not in skill_meta:
                        logger.warning(
                            f"Failed to parse skill metadata from {skill_md_path}"
                        )
                        continue

                    skill_name = skill_meta["name"]

                    # Generate skill code (use name as code, clean and lowercase)
                    skill_code = self._generate_skill_code(skill_meta, repo_url)

                    # Check if skill already exists
                    existing_skill_request = SkillRequest(skill_code=skill_code)
                    existing_skill = self.get(existing_skill_request)

                    # Check auto_sync setting - skip if auto_sync is disabled
                    # unless force_update is explicitly set
                    if (
                        existing_skill
                        and existing_skill.auto_sync is False
                        and not force_update
                    ):
                        logger.info(
                            f"Skill {skill_name} has auto_sync disabled, skipping"
                        )
                        synced_skills.append(existing_skill)
                        continue

                    # Determine if we should update
                    should_update = force_update or (
                        existing_skill and existing_skill.commit_id != commit_id
                    )

                    if existing_skill and not should_update:
                        logger.info(
                            f"Skill {skill_name} already exists and up to date, skipping"
                        )
                        synced_skills.append(existing_skill)
                        continue

                    # Read skill content
                    with open(skill_md_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Get relative path for storage
                    rel_path = os.path.relpath(skill_path, repo_path)

                    # Build skill request
                    # Preserve existing auto_sync setting if skill already exists
                    auto_sync = existing_skill.auto_sync if existing_skill else True

                    skill_request = SkillRequest(
                        skill_code=skill_code,
                        name=skill_name,
                        description=skill_meta.get("description", ""),
                        type=skill_meta.get("type", "python"),
                        author=skill_meta.get("author"),
                        email=skill_meta.get("email"),
                        version=skill_meta.get("version"),
                        path=rel_path,
                        content=content,
                        icon=skill_meta.get("icon"),
                        category=skill_meta.get("category"),
                        installed=0,
                        available=True,
                        repo_url=repo_url,
                        branch=branch,
                        commit_id=commit_id,
                        auto_sync=auto_sync,
                    )

                    # Create or update skill
                    if existing_skill:
                        logger.info(f"Updating skill: {skill_name}")
                        skill_response = self.update(skill_request)
                    else:
                        logger.info(f"Creating new skill: {skill_name}")
                        skill_response = self.create(skill_request)
                        # Also increment installed count
                        if skill_response.installed is None:
                            skill_response.installed = 0

                    synced_skills.append(skill_response)

                    # Copy skill files to project skill directory
                    self._copy_skill_to_project(
                        skill_path, skill_name, project_skill_dir, skill_code
                    )

                    # Copy skill files to sandbox if available
                    if sandbox_skill_dir:
                        self._copy_skill_to_sandbox(
                            skill_path, skill_name, sandbox_skill_dir, skill_code
                        )

                except Exception as e:
                    logger.exception(
                        f"Error processing skill directory {skill_path}: {e}"
                    )
                    continue

            logger.info(
                f"Successfully synced {len(synced_skills)} skills from {repo_url}"
            )
            return synced_skills

        except Exception as e:
            logger.exception(f"Failed to sync skills from git: {e}")
            raise

    def _find_skill_directories(self, repo_path: str) -> List[str]:
        """Find skill directories in the repository.

        Args:
            repo_path (str): Path to the cloned repository

        Returns:
            List[str]: List of skill directory paths containing SKILL.md
        """
        skill_dirs = []

        # Common skill directory patterns
        patterns = [
            "skills",  # Common pattern: repo/skills/
            "",  # Root directory: repo/
            "skill",  # Singular: repo/skill/
            "agent-skills",  # Another common pattern
        ]

        for pattern in patterns:
            search_path = os.path.join(repo_path, pattern) if pattern else repo_path
            if not os.path.isdir(search_path):
                continue

            for entry in os.scandir(search_path):
                if entry.is_dir():
                    skill_md_path = os.path.join(entry.path, "SKILL.md")
                    if os.path.exists(skill_md_path):
                        skill_dirs.append(entry.path)

        return skill_dirs

    def _parse_skill_md(self, file_path: str) -> Optional[Dict[str, str]]:
        """Parse SKILL.md file to extract metadata.

        Args:
            file_path (str): Path to SKILL.md file

        Returns:
            Optional[Dict[str, str]]: Parsed metadata dictionary
        """
        try:
            if not os.path.exists(file_path):
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract frontmatter between --- markers
            # Use strip() to handle any leading/trailing whitespace
            content_stripped = content.strip()
            match = re.search(
                r"^---\s*\n(.*?)\n---\s*$", content_stripped, re.DOTALL | re.MULTILINE
            )
            if not match:
                return None

            frontmatter = match.group(1)
            data = {}

            # Parse the frontmatter line by line to handle nested structures
            lines = frontmatter.split("\n")
            metadata_start_line = -1
            metadata_indent = 0
            in_metadata_section = False
            # Track multi-line string values (YAML | or > syntax)
            multiline_key = None
            multiline_indent = None
            multiline_lines = []

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Check if we're collecting multi-line string content
                if multiline_key is not None:
                    current_indent = len(line) - len(line.lstrip())
                    if stripped and current_indent >= multiline_indent:
                        multiline_lines.append(stripped)
                        continue
                    else:
                        # End of multi-line value
                        data[multiline_key] = " ".join(multiline_lines)
                        multiline_key = None
                        multiline_indent = None
                        multiline_lines = []
                        if not stripped:
                            continue

                # Skip empty lines and comments
                if not stripped or stripped.startswith("#"):
                    continue

                # Check for metadata: section start (nested structure)
                if stripped.startswith("metadata:") or stripped == "metadata:":
                    in_metadata_section = True
                    metadata_start_line = i
                    # Calculate the indent level of the metadata: line
                    indent_match = re.match(r"^(\s*)", line)
                    metadata_indent = len(indent_match.group(1)) if indent_match else 0
                    continue

                # Calculate current line's indent
                current_indent = len(line) - len(line.lstrip())

                # Check if we've exited the metadata section
                # We exit when we encounter a line with same or less indent as 'metadata:'
                if in_metadata_section:
                    if current_indent > metadata_indent:
                        # Still inside metadata section (indented more than metadata:)
                        pass
                    else:
                        # Exited metadata section
                        in_metadata_section = False

                # Parse key-value pairs
                # Pattern matches: key: value
                # Value can be quoted or unquoted
                key_match = re.match(r"^\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$", line)
                if key_match:
                    key = key_match.group(1)
                    value = key_match.group(2).strip()

                    # Skip empty values (they indicate nested structures we don't parse deeply)
                    if not value:
                        continue

                    # Handle YAML multi-line string indicators (| or >)
                    if value in ("|", ">", "|-", ">-", "|+", ">+"):
                        multiline_key = key
                        key_indent = len(line) - len(line.lstrip())
                        multiline_indent = key_indent + 2
                        multiline_lines = []
                        continue

                    # Clean up quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    # Store the value - this flattens the nested metadata structure
                    data[key] = value

            # Flush any remaining multi-line value
            if multiline_key is not None and multiline_lines:
                data[multiline_key] = " ".join(multiline_lines)

            return data if data else None

        except Exception as e:
            logger.warning(f"Failed to parse skill metadata from {file_path}: {e}")
            return None

    def _generate_skill_code(self, skill_meta: Dict[str, str], repo_url: str) -> str:
        """Generate a unique skill code from metadata and repo URL.

        The skill code is based on skill name and repo URL, NOT version.
        This ensures the same skill gets updated instead of creating new records
        when the version changes.

        Args:
            skill_meta (Dict[str, str]): Parsed skill metadata
            repo_url (str): Git repository URL

        Returns:
            str: Unique skill code
        """
        # Use name as base, convert to lowercase and replace special chars
        name = skill_meta.get("name", "unnamed").lower()
        name = re.sub(r"[^a-z0-9-]", "-", name).strip("-")

        # Add repo hash for uniqueness (same repo = same hash)
        repo_hash = hashlib.md5(repo_url.encode()).hexdigest()[:8]

        skill_code = f"{name}-{repo_hash}"
        return skill_code

    def _copy_skill_to_project(
        self, skill_path: str, skill_name: str, project_dir: str, skill_code: str
    ) -> None:
        """Copy skill files to project skill directory.

        Args:
            skill_path (str): Source skill directory path
            skill_name (str): Name of the skill
            project_dir (str): Project skill directory
            skill_code (str): Unique skill code
        """
        try:
            target_dir = os.path.join(project_dir, skill_code)

            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
                logger.info(f"Removed existing skill directory: {target_dir}")

            os.makedirs(target_dir, exist_ok=True)

            if os.path.exists(skill_path):
                for item in os.listdir(skill_path):
                    src = os.path.join(skill_path, item)
                    dst = os.path.join(target_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)

            logger.info(f"Copied skill files to project directory: {target_dir}")

        except Exception as e:
            logger.warning(f"Failed to copy skill to project directory: {e}")

    def _copy_skill_to_sandbox(
        self, skill_path: str, skill_name: str, sandbox_dir: str, skill_code: str = None
    ) -> None:
        """Copy skill files to sandbox skill directory.

        Args:
            skill_path (str): Source skill directory path
            skill_name (str): Name of the skill
            sandbox_dir (str): Sandbox skill directory
            skill_code (str): Unique skill code (preferred for directory name)
        """
        try:
            if not os.path.exists(sandbox_dir):
                logger.warning(f"Sandbox skill directory does not exist: {sandbox_dir}")
                return

            # Use skill_code as directory name for consistency and uniqueness
            if skill_code:
                skill_dir_name = skill_code
            else:
                # Fallback to normalized skill name for backward compatibility
                skill_dir_name = re.sub(r"[^a-zA-Z0-9_-]", "-", skill_name)
            target_dir = os.path.join(sandbox_dir, skill_dir_name)

            # Remove existing directory to ensure clean update
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
                logger.info(f"Removed existing skill directory: {target_dir}")

            os.makedirs(target_dir, exist_ok=True)

            # Copy all files from skill directory
            if os.path.exists(skill_path):
                for item in os.listdir(skill_path):
                    src = os.path.join(skill_path, item)
                    dst = os.path.join(target_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)

            logger.info(f"Copied skill files to sandbox directory: {target_dir}")

        except Exception as e:
            logger.warning(f"Failed to copy skill to sandbox directory: {e}")

    async def upload_from_zip(self, file: UploadFile) -> SkillResponse:
        """Upload a skill from a zip file.

        Args:
            file (UploadFile): The uploaded zip file

        Returns:
            SkillResponse: The created skill response
        """
        project_skill_dir = self._serve_config.get_project_skill_dir()
        sandbox_skill_dir = self._serve_config.get_sandbox_skill_dir()

        # Create temp directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            zip_path = os.path.join(temp_dir, f"{uuid.uuid4()}.zip")
            with open(zip_path, "wb") as f:
                content = await file.read()
                f.write(content)

            # Extract zip file
            extract_dir = os.path.join(temp_dir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find skill directory (look for SKILL.md)
            skill_path = self._find_skill_directory(extract_dir)
            if not skill_path:
                raise ValueError("No SKILL.md found in the uploaded file")

            # Parse skill metadata
            skill_md_path = os.path.join(skill_path, "SKILL.md")
            skill_meta = self._parse_skill_md(skill_md_path)
            if not skill_meta or "name" not in skill_meta:
                raise ValueError("Failed to parse skill metadata")

            skill_name = skill_meta["name"]

            # Generate skill code for local upload (use name + UUID for uniqueness)
            skill_code = self._generate_upload_skill_code(skill_meta)

            # Check if skill already exists
            existing_skill_request = SkillRequest(skill_code=skill_code)
            existing_skill = self.get(existing_skill_request)

            # Read skill content
            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Build skill request
            skill_request = SkillRequest(
                skill_code=skill_code,
                name=skill_name,
                description=skill_meta.get("description", ""),
                type=skill_meta.get("type", "python"),
                author=skill_meta.get("author"),
                email=skill_meta.get("email"),
                version=skill_meta.get("version"),
                path=skill_name,
                content=content,
                icon=skill_meta.get("icon"),
                category=skill_meta.get("category"),
                installed=0,
                available=True,
                repo_url=None,  # Local upload has no repo
                branch=None,
                commit_id=None,
            )

            # Create or update skill
            if existing_skill:
                logger.info(f"Updating skill from upload: {skill_name}")
                skill_response = self.update(skill_request)
            else:
                logger.info(f"Creating new skill from upload: {skill_name}")
                skill_response = self.create(skill_request)

            # Copy skill files to project skill directory
            self._copy_skill_to_project(
                skill_path, skill_name, project_skill_dir, skill_code
            )

            # Copy skill files to sandbox if available
            if sandbox_skill_dir:
                self._copy_skill_to_sandbox(
                    skill_path, skill_name, sandbox_skill_dir, skill_code
                )

            return skill_response

    async def upload_from_folder(
        self, skill_name: str, skill_path: str
    ) -> SkillResponse:
        """Upload a skill from a local folder.

        Args:
            skill_name (str): The skill name
            skill_path (str): The local skill folder path

        Returns:
            SkillResponse: The created skill response
        """
        project_skill_dir = self._serve_config.get_project_skill_dir()
        sandbox_skill_dir = self._serve_config.get_sandbox_skill_dir()

        # Validate skill path
        if not os.path.isdir(skill_path):
            raise ValueError(f"Invalid skill path: {skill_path}")

        # Check for SKILL.md
        skill_md_path = os.path.join(skill_path, "SKILL.md")
        if not os.path.exists(skill_md_path):
            raise ValueError(f"SKILL.md not found in {skill_path}")

        # Parse skill metadata
        skill_meta = self._parse_skill_md(skill_md_path)
        if not skill_meta:
            # Use provided name if metadata parsing fails
            skill_meta = {"name": skill_name}

        skill_name = skill_meta["name"]

        # Generate skill code
        skill_code = self._generate_upload_skill_code(skill_meta)

        # Check if skill already exists
        existing_skill_request = SkillRequest(skill_code=skill_code)
        existing_skill = self.get(existing_skill_request)

        # Read skill content
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Build skill request
        skill_request = SkillRequest(
            skill_code=skill_code,
            name=skill_name,
            description=skill_meta.get("description", ""),
            type=skill_meta.get("type", "python"),
            author=skill_meta.get("author"),
            email=skill_meta.get("email"),
            version=skill_meta.get("version"),
            path=skill_name,
            content=content,
            icon=skill_meta.get("icon"),
            category=skill_meta.get("category"),
            installed=0,
            available=True,
            repo_url=None,
            branch=None,
            commit_id=None,
        )

        # Create or update skill
        if existing_skill:
            logger.info(f"Updating skill from folder: {skill_name}")
            skill_response = self.update(skill_request)
        else:
            logger.info(f"Creating new skill from folder: {skill_name}")
            skill_response = self.create(skill_request)

        # Copy skill files to project skill directory
        self._copy_skill_to_project(
            skill_path, skill_name, project_skill_dir, skill_code
        )

        # Copy skill files to sandbox if available
        if sandbox_skill_dir:
            self._copy_skill_to_sandbox(
                skill_path, skill_name, sandbox_skill_dir, skill_code
            )

        return skill_response

    def _find_skill_directory(self, base_dir: str) -> Optional[str]:
        """Find the skill directory containing SKILL.md.

        Args:
            base_dir (str): Base directory to search

        Returns:
            Optional[str]: Path to skill directory, or None if not found
        """
        # Check if base_dir itself contains SKILL.md
        if os.path.exists(os.path.join(base_dir, "SKILL.md")):
            return base_dir

        # Search subdirectories
        for entry in os.scandir(base_dir):
            if entry.is_dir():
                skill_md_path = os.path.join(entry.path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    return entry.path

        return None

    def _generate_upload_skill_code(self, skill_meta: Dict[str, str]) -> str:
        """Generate a skill code for uploaded skills.

        The skill code is based on skill name only, NOT version.
        This ensures the same skill gets updated instead of creating new records
        when the version changes.

        Args:
            skill_meta (Dict[str, str]): Parsed skill metadata

        Returns:
            str: Skill code (same skill name will have the same code)
        """
        name = skill_meta.get("name", "unnamed").lower()
        name = re.sub(r"[^a-z0-9-]", "-", name).strip("-")

        return name

    def get_skill_directory(self, skill_code: str) -> str:
        """Get the physical directory path for a skill.

        Args:
            skill_code (str): The skill code

        Returns:
            str: The directory path
        """
        project_skill_dir = self._serve_config.get_project_skill_dir()

        skill_dir = os.path.join(project_skill_dir, skill_code)

        # If skill directory doesn't exist, check database for path info
        if not os.path.exists(skill_dir):
            skill_request = SkillRequest(skill_code=skill_code)
            skill = self.get(skill_request)
            if skill and skill.path:
                # Try to use the stored path
                skill_dir = os.path.join(
                    project_skill_dir, skill.path.replace("/", os.sep)
                )
                if not os.path.exists(skill_dir):
                    # Try direct path from skill.path
                    skill_dir = skill.path

        return skill_dir

    def list_skill_files(self, skill_code: str) -> Dict[str, Any]:
        """List all files in the skill directory.

        Args:
            skill_code (str): The skill code

        Returns:
            Dict with skill_code, skill_path, and list of files
        """
        skill_dir = self.get_skill_directory(skill_code)

        if not os.path.exists(skill_dir):
            logger.warning(
                f"Skill directory not found: {skill_dir}. Returning empty file list."
            )
            return {"skill_code": skill_code, "skill_path": skill_dir, "files": []}

        files = []

        for root, dirs, filenames in os.walk(skill_dir):
            # Skip hidden directories and common temp directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and d not in ["__pycache__", "node_modules"]
            ]

            for filename in filenames:
                # Skip hidden files
                if filename.startswith("."):
                    continue

                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, skill_dir)

                # Get file info
                file_stat = os.stat(full_path)
                file_info = {
                    "name": filename,
                    "path": rel_path.replace("\\", "/"),
                    "size": file_stat.st_size,
                    "is_directory": False,
                    "extension": os.path.splitext(filename)[1][1:].lower(),
                }
                files.append(file_info)

        return {"skill_code": skill_code, "skill_path": skill_dir, "files": files}

    def read_skill_file(self, skill_code: str, file_path: str) -> Dict[str, Any]:
        """Read a skill file's content.

        Args:
            skill_code (str): The skill code
            file_path (str): Relative file path within skill directory

        Returns:
            Dict with file content and metadata
        """
        skill_dir = self.get_skill_directory(skill_code)

        # Normalize file path
        file_path = file_path.replace("\\", "/")
        full_path = os.path.join(skill_dir, *file_path.split("/"))

        if not os.path.exists(full_path):
            raise ValueError(f"File not found: {file_path}")

        if os.path.isdir(full_path):
            raise ValueError(f"Path is a directory, not a file: {file_path}")

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        _, extension = os.path.splitext(file_path)
        file_type = extension[1:].lower() if extension else "text"

        return {
            "skill_code": skill_code,
            "file_path": file_path,
            "content": content,
            "file_type": file_type,
        }

    def write_skill_file(
        self, skill_code: str, file_path: str, content: str
    ) -> Dict[str, Any]:
        """Write content to a skill file.

        Args:
            skill_code (str): The skill code
            file_path (str): Relative file path within skill directory
            content (str): Content to write

        Returns:
            Dict with write result
        """
        skill_dir = self.get_skill_directory(skill_code)

        # Normalize file path
        file_path = file_path.replace("\\", "/")
        full_path = os.path.join(skill_dir, *file_path.split("/"))

        # Ensure directory exists
        dir_path = os.path.dirname(full_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "skill_code": skill_code,
            "file_path": file_path,
            "success": True,
            "message": "File saved successfully",
        }

    def create_skill_file(
        self, skill_code: str, file_path: str, content: str = ""
    ) -> Dict[str, Any]:
        """Create a new file in the skill directory.

        Args:
            skill_code (str): The skill code
            file_path (str): Relative file path within skill directory
            content (str): Initial content for the file

        Returns:
            Dict with create result
        """
        skill_dir = self.get_skill_directory(skill_code)

        # Normalize file path
        file_path = file_path.replace("\\", "/")
        full_path = os.path.join(skill_dir, *file_path.split("/"))

        if os.path.exists(full_path):
            raise ValueError(f"File already exists: {file_path}")

        # Ensure directory exists
        dir_path = os.path.dirname(full_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        # Create file with initial content
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "skill_code": skill_code,
            "file_path": file_path,
            "success": True,
            "message": "File created successfully",
        }

    def delete_skill_file(self, skill_code: str, file_path: str) -> Dict[str, Any]:
        """Delete a file from the skill directory.

        Args:
            skill_code (str): The skill code
            file_path (str): Relative file path within skill directory

        Returns:
            Dict with delete result
        """
        skill_dir = self.get_skill_directory(skill_code)

        # Normalize file path
        file_path = file_path.replace("\\", "/")
        full_path = os.path.join(skill_dir, *file_path.split("/"))

        if not os.path.exists(full_path):
            raise ValueError(f"File not found: {file_path}")

        if os.path.isdir(full_path):
            # Delete directory
            shutil.rmtree(full_path)
        else:
            # Delete file
            os.remove(full_path)

        return {
            "skill_code": skill_code,
            "file_path": file_path,
            "success": True,
            "message": "Deleted successfully",
        }

    def rename_skill_file(
        self, skill_code: str, old_path: str, new_path: str
    ) -> Dict[str, Any]:
        """Rename a file in the skill directory.

        Args:
            skill_code (str): The skill code
            old_path (str): Current relative file path within skill directory
            new_path (str): New relative file path within skill directory

        Returns:
            Dict with rename result
        """
        skill_dir = self.get_skill_directory(skill_code)

        # Normalize file paths
        old_path = old_path.replace("\\", "/")
        new_path = new_path.replace("\\", "/")

        old_full_path = os.path.join(skill_dir, *old_path.split("/"))
        new_full_path = os.path.join(skill_dir, *new_path.split("/"))

        if not os.path.exists(old_full_path):
            raise ValueError(f"File not found: {old_path}")

        if os.path.exists(new_full_path):
            raise ValueError(f"File already exists: {new_path}")

        # Ensure target directory exists
        new_dir_path = os.path.dirname(new_full_path)
        if new_dir_path and not os.path.exists(new_dir_path):
            os.makedirs(new_dir_path, exist_ok=True)

        # Perform rename
        os.rename(old_full_path, new_full_path)

        return {
            "skill_code": skill_code,
            "old_path": old_path,
            "new_path": new_path,
            "success": True,
            "message": "Renamed successfully",
        }

    def batch_upload_files(
        self, skill_code: str, files: List[Dict[str, Any]], overwrite: bool = False
    ) -> Dict[str, Any]:
        """Upload multiple files to a skill directory.

        Args:
            skill_code (str): The skill code
            files (List[Dict]): List of file dicts with 'file_path', 'content', and optional 'is_base64'
            overwrite (bool): Whether to overwrite existing files

        Returns:
            Dict with batch upload result
        """
        import base64

        skill_dir = self.get_skill_directory(skill_code)

        success_files = []
        failed_files = []

        for file_item in files:
            file_path = file_item.get("file_path", "")
            content = file_item.get("content", "")
            is_base64 = file_item.get("is_base64", False)

            if not file_path:
                continue

            try:
                # Normalize file path
                file_path = file_path.replace("\\", "/")
                full_path = os.path.join(skill_dir, *file_path.split("/"))

                # Check if file exists and we're not overwriting
                if os.path.exists(full_path) and not overwrite:
                    failed_files.append(
                        {
                            "file_path": file_path,
                            "error": "File already exists (use overwrite=true to replace)",
                        }
                    )
                    continue

                # Ensure directory exists
                dir_path = os.path.dirname(full_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)

                # Decode content if base64
                if is_base64:
                    try:
                        file_content = base64.b64decode(content)
                        with open(full_path, "wb") as f:
                            f.write(file_content)
                    except Exception:
                        # If base64 decode fails, treat as plain text
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(content)
                else:
                    # Write as text
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)

                success_files.append(file_path)
            except Exception as e:
                failed_files.append({"file_path": file_path, "error": str(e)})

        return {
            "skill_code": skill_code,
            "total_count": len(files),
            "success_count": len(success_files),
            "failed_count": len(failed_files),
            "success_files": success_files,
            "failed_files": failed_files,
        }

    # -------------------- Async Git Sync Methods --------------------

    def _get_sync_task_dao(self):
        """Get the sync task DAO"""
        from ..models.skill_sync_task_db import SkillSyncTaskDao
        from derisk.storage.metadata import db

        return SkillSyncTaskDao(db)

    def create_sync_task(
        self, repo_url: str, branch: str = "main", force_update: bool = False
    ) -> SkillSyncTaskResponse:
        """Create a new sync task and start it in background

        Args:
            repo_url: Git repository URL
            branch: Git branch
            force_update: Whether to force update existing skills

        Returns:
            SkillSyncTaskResponse: The created task
        """
        task_id = str(uuid.uuid4())
        dao = self._get_sync_task_dao()
        entity = dao.create_task(task_id, repo_url, branch, force_update)

        # Start background task
        def _run_sync_task():
            self._run_background_sync_task(entity)

        task_thread = threading.Thread(target=_run_sync_task, daemon=True)
        _background_tasks[task_id] = task_thread
        task_thread.start()

        return SkillSyncTaskResponse.from_entity(entity)

    def get_sync_task_status(self, task_id: str) -> Optional[SkillSyncTaskResponse]:
        """Get sync task status

        Args:
            task_id: Task ID

        Returns:
            SkillSyncTaskResponse or None
        """
        dao = self._get_sync_task_dao()
        entity = dao.get_task_by_id(task_id)
        if entity:
            return SkillSyncTaskResponse.from_entity(entity)
        return None

    def _run_background_sync_task(self, entity) -> None:
        """Run the git sync in background and update status

        Args:
            entity: The sync task entity
        """
        task_id = entity.task_id
        repo_url = entity.repo_url
        branch = entity.branch
        force_update = entity.force_update
        dao = self._get_sync_task_dao()

        try:
            # Update to running
            dao.update_task_status(
                task_id,
                status="running",
                current_step="Initializing...",
            )

            import git

            synced_skills: List[SkillResponse] = []
            project_skill_dir = self._serve_config.get_project_skill_dir()
            temp_git_dir = self._serve_config.get_temp_git_dir()
            sandbox_skill_dir = self._serve_config.get_sandbox_skill_dir()

            # Ensure directories exist
            os.makedirs(project_skill_dir, exist_ok=True)
            os.makedirs(temp_git_dir, exist_ok=True)

            dao.update_task_status(
                task_id, status="running", current_step="Cloning repository..."
            )

            # Generate a unique repo name from URL
            repo_name = hashlib.md5(repo_url.encode()).hexdigest()[:16]
            repo_path = os.path.join(temp_git_dir, repo_name)

            # Clone or pull the repository
            if os.path.exists(repo_path) and os.path.exists(
                os.path.join(repo_path, ".git")
            ):
                dao.update_task_status(
                    task_id, status="running", current_step="Pulling updates..."
                )
                repo = git.Repo(repo_path)
                repo.git.checkout(branch)
                repo.remotes.origin.pull(branch)
            else:
                if os.path.exists(repo_path):
                    shutil.rmtree(repo_path)
                repo = git.Repo.clone_from(repo_url, repo_path, branch=branch)

            # Get current commit ID
            commit_id = repo.head.commit.hexsha

            dao.update_task_status(
                task_id, status="running", current_step="Scanning for skills..."
            )

            # Scan for skill directories
            skill_dirs = self._find_skill_directories(repo_path)

            dao.update_task_init_steps(
                task_id,
                total_steps=len(skill_dirs),
                current_step=f"Found {len(skill_dirs)} skills to sync...",
            )

            logger.info(f"Found {len(skill_dirs)} skill directories")

            synced_skill_codes: List[str] = []

            for idx, skill_path in enumerate(skill_dirs):
                try:
                    # Extract directory name as initial skill name (fallback)
                    skill_dir_name = os.path.basename(skill_path)

                    # Parse SKILL.md first to get the real skill name
                    skill_md_path = os.path.join(skill_path, "SKILL.md")
                    if not os.path.exists(skill_md_path):
                        logger.warning(f"SKILL.md not found in {skill_path}, skipping")
                        dao.increment_progress(
                            task_id, f"SKILL.md not found: {skill_dir_name}"
                        )
                        continue

                    skill_meta = self._parse_skill_md(skill_md_path)
                    if not skill_meta or "name" not in skill_meta:
                        logger.warning(
                            f"Failed to parse skill metadata from {skill_md_path}"
                        )
                        dao.increment_progress(
                            task_id, f"Parse failed: {skill_dir_name}"
                        )
                        continue

                    # Use the actual skill name from metadata
                    skill_name = skill_meta.get("name")

                    dao.update_task_status(
                        task_id,
                        status="running",
                        current_step=f"Processing {idx + 1}/{len(skill_dirs)}: {skill_name}",
                    )

                    # Generate skill code
                    skill_code = self._generate_skill_code(skill_meta, repo_url)

                    # Check if skill already exists
                    existing_skill_request = SkillRequest(skill_code=skill_code)
                    existing_skill = self.get(existing_skill_request)

                    # Determine if we should update
                    should_update = force_update or (
                        existing_skill and existing_skill.commit_id != commit_id
                    )

                    if existing_skill and not should_update:
                        synced_skill_codes.append(skill_code)
                        dao.increment_progress(task_id, f"{skill_name} (up to date)")
                        continue

                    # Read skill content
                    with open(skill_md_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Get relative path for storage
                    rel_path = os.path.relpath(skill_path, repo_path)

                    # Build skill request
                    skill_request = SkillRequest(
                        skill_code=skill_code,
                        name=skill_name,
                        description=skill_meta.get("description", ""),
                        type=skill_meta.get("type", "python"),
                        author=skill_meta.get("author"),
                        email=skill_meta.get("email"),
                        version=skill_meta.get("version"),
                        path=rel_path,
                        content=content,
                        icon=skill_meta.get("icon"),
                        category=skill_meta.get("category"),
                        installed=0 if not existing_skill else existing_skill.installed,
                        available=True,
                        repo_url=repo_url,
                        branch=branch,
                        commit_id=commit_id,
                    )

                    # Create or update skill
                    if existing_skill:
                        skill_response = self.update(skill_request)
                    else:
                        skill_response = self.create(skill_request)

                    synced_skills.append(skill_response)
                    synced_skill_codes.append(skill_code)

                    # Copy skill files to project skill directory
                    self._copy_skill_to_project(
                        skill_path, skill_name, project_skill_dir, skill_code
                    )

                    # Copy skill files to sandbox if available
                    if sandbox_skill_dir:
                        self._copy_skill_to_sandbox(
                            skill_path, skill_name, sandbox_skill_dir, skill_code
                        )

                    dao.increment_progress(task_id, f"Synced {skill_name}")

                except Exception as e:
                    logger.exception(f"Error processing skill {skill_path}: {e}")
                    dao.increment_progress(task_id, f"Error processing {skill_name}")
                    continue

            # Update task with results
            dao.update_synced_skills(task_id, synced_skill_codes)
            dao.update_task_status(
                task_id,
                status="completed",
                progress=100,
                current_step=f"Sync completed! {len(synced_skill_codes)} skills synced.",
            )

            # Clean up background task reference
            if task_id in _background_tasks:
                del _background_tasks[task_id]

            logger.info(
                f"Successfully synced {len(synced_skill_codes)} skills from {repo_url}"
            )

        except Exception as e:
            logger.exception(f"Failed to sync skills from git: {e}")
            dao.update_task_status(
                task_id,
                status="failed",
                error_msg=str(e),
                error_details=str(e.__class__.__name__),
                current_step="Sync failed",
            )

            # Clean up background task reference
            if task_id in _background_tasks:
                del _background_tasks[task_id]
