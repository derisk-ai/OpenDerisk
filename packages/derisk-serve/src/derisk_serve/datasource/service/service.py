import json
import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException

from derisk._private.config import Config
from derisk._private.pydantic import model_to_dict
from derisk.component import ComponentType, SystemApp
from derisk.core.awel.dag.dag_manager import DAGManager
from derisk.datasource.parameter import BaseDatasourceParameters
from derisk.storage.metadata import BaseDao
from derisk.util.executor_utils import ExecutorFactory
from derisk_ext.datasource.schema import DBType
from derisk_serve.core import BaseService, ResourceTypes
from derisk_serve.datasource.manages import ConnectorManager
from derisk_serve.datasource.manages.connect_config_db import (
    ConnectConfigDao,
    ConnectConfigEntity,
)

from ...rag.storage_manager import StorageManager
from ..api.schemas import (
    DatasourceCreateRequest,
    DatasourceQueryResponse,
    DatasourceServeRequest,
    DatasourceServeResponse,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from .learning_service import SchemaLearningService
from .spec_service import DbSpecService

logger = logging.getLogger(__name__)
CFG = Config()


class Service(
    BaseService[ConnectConfigEntity, DatasourceServeRequest, DatasourceServeResponse]
):
    """The service class for Datasource management."""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: ServeConfig,
        dao: Optional[ConnectConfigDao] = None,
    ):
        self._system_app = system_app
        self._dao: ConnectConfigDao = dao
        self._dag_manager: Optional[DAGManager] = None
        self._db_summary_client = None
        self._serve_config = config
        self._learning_service: Optional[SchemaLearningService] = None
        self._spec_service: Optional[DbSpecService] = None
        self._file_learning: Optional[Any] = None

        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service"""
        super().init_app(system_app)

        self._dao = self._dao or ConnectConfigDao()
        self._system_app = system_app

    def before_start(self):
        """Execute before the application starts"""
        super().before_start()

    def after_start(self):
        """Execute after the application starts"""
        try:
            self._recover_stale_tasks()
        except Exception as e:
            logger.error(f"[RECOVERY] Failed to recover stale tasks: {e}")

    def _recover_stale_tasks(self):
        """Auto-recover learning tasks that were interrupted by a crash/restart."""
        from derisk_serve.datasource.manages.learning_task_db import DbLearningTaskDao

        task_dao = DbLearningTaskDao()
        timeout = self.learning_service._subtask_stale_timeout
        stale_tasks = task_dao.get_stale_active_tasks(stale_seconds=timeout)
        if not stale_tasks:
            return

        logger.info(f"[RECOVERY] Found {len(stale_tasks)} stale learning tasks")

        executor = self._system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()  # type: ignore

        for task in stale_tasks:
            ds_id = task["datasource_id"]
            db_config = self._dao.get_one({"id": ds_id})
            if not db_config:
                logger.warning(
                    f"[RECOVERY] Datasource {ds_id} not found, skipping task {task['id']}"
                )
                continue
            logger.info(
                f"[RECOVERY] Resuming task {task['id']} for datasource {ds_id}"
            )
            executor.submit(
                self.learning_service.resume_stale_task,
                task["id"],
                ds_id,
                db_config.db_name,
                db_config.db_type,
            )

    @property
    def dao(
        self,
    ) -> BaseDao[ConnectConfigEntity, DatasourceServeRequest, DatasourceServeResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    @property
    def datasource_manager(self) -> ConnectorManager:
        if not self._system_app:
            raise ValueError("SYSTEM_APP is not set")
        return ConnectorManager.get_instance(self._system_app)

    @property
    def storage_manager(self) -> StorageManager:
        if not self._system_app:
            raise ValueError("SYSTEM_APP is not set")
        return StorageManager.get_instance(self._system_app)

    @property
    def learning_service(self) -> SchemaLearningService:
        if not self._learning_service:
            self._learning_service = SchemaLearningService(
                self.datasource_manager,
                system_app=self._system_app,
            )
        return self._learning_service

    @property
    def spec_service(self) -> DbSpecService:
        if not self._spec_service:
            self._spec_service = DbSpecService()
        return self._spec_service

    @property
    def file_learning(self):
        """Get FileLearningService instance."""
        if not self._file_learning:
            from derisk_serve.datasource.file_learning.service import FileLearningService
            self._file_learning = FileLearningService(self._system_app)
        return self._file_learning

    def create(
        self, request: Union[DatasourceCreateRequest, DatasourceServeRequest]
    ) -> DatasourceQueryResponse:
        """Create a new Datasource entity

        Args:
            request (Union[DatasourceCreateRequest, DatasourceServeRequest]): The
                request to create a new Datasource entity. DatasourceServeRequest is
                deprecated.

        Returns:
            DatasourceQueryResponse: The response
        """
        str_db_type = (
            request.type
            if isinstance(request, DatasourceCreateRequest)
            else request.db_type
        )
        desc = ""
        if isinstance(request, DatasourceCreateRequest):
            connector_params: BaseDatasourceParameters = (
                self.datasource_manager._create_parameters(request)
            )
            persisted_state = connector_params.persisted_state()
            desc = request.description
        else:
            persisted_state = model_to_dict(request)
            desc = request.comment
        if "ext_config" in persisted_state and isinstance(
            persisted_state["ext_config"], dict
        ):
            persisted_state["ext_config"] = json.dumps(
                persisted_state["ext_config"], ensure_ascii=False
            )
        persisted_state["comment"] = desc
        db_name = persisted_state.get("db_name")
        datasource = self._dao.get_by_names(db_name)
        if datasource:
            raise HTTPException(
                status_code=400,
                detail=f"datasource name:{db_name} already exists",
            )
        try:
            db_type = DBType.of_db_type(str_db_type)
            if not db_type:
                raise HTTPException(
                    status_code=400, detail=f"Unsupported Db Type, {str_db_type}"
                )

            res = self._dao.create(persisted_state)

            # Trigger schema learning in background
            datasource_id = res.id if hasattr(res, "id") else res.get("id")
            if datasource_id:
                executor = self._system_app.get_component(
                    ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
                ).create()  # type: ignore
                executor.submit(
                    self.learning_service.learn_database,
                    datasource_id,
                    db_name,
                    str_db_type,
                    "auto_on_create",
                )
        except Exception as e:
            raise ValueError("Add db connect info error!" + str(e))
        return self._to_query_response(res)

    def update(
        self, request: Union[DatasourceCreateRequest, DatasourceServeRequest]
    ) -> DatasourceQueryResponse:
        """Update a Datasource entity"""
        str_db_type = (
            request.type
            if isinstance(request, DatasourceCreateRequest)
            else request.db_type
        )
        desc = ""
        if isinstance(request, DatasourceCreateRequest):
            connector_params: BaseDatasourceParameters = (
                self.datasource_manager._create_parameters(request)
            )
            persisted_state = connector_params.persisted_state()
            desc = request.description
        else:
            persisted_state = model_to_dict(request)
            desc = request.comment
        if "ext_config" in persisted_state and isinstance(
            persisted_state["ext_config"], dict
        ):
            persisted_state["ext_config"] = json.dumps(
                persisted_state["ext_config"], ensure_ascii=False
            )
        persisted_state["comment"] = desc
        db_name = persisted_state.get("db_name")
        if not db_name:
            raise HTTPException(status_code=400, detail="datasource name is required")
        datasources = self._dao.get_by_names(db_name)
        if datasources is None:
            raise HTTPException(
                status_code=400,
                detail=f"there is no datasource name:{db_name} exists",
            )
        res = self._dao.update({"id": datasources.id}, persisted_state)
        return self._to_query_response(res)

    def get(self, datasource_id: str) -> Optional[DatasourceQueryResponse]:
        """Get a Datasource entity"""
        res = self._dao.get_one({"id": datasource_id})
        if not res:
            return None
        return self._to_query_response(res)

    def delete(self, datasource_id: str) -> Optional[DatasourceServeResponse]:
        """Delete a Datasource entity and cascade-delete specs and learning tasks."""
        db_config = self._dao.get_one({"id": datasource_id})
        if db_config:
            # Delete legacy profile
            if self._db_summary_client:
                try:
                    self._db_summary_client.delete_db_profile(db_config.db_name)
                except Exception:
                    pass

            # Cascade delete specs and learning tasks
            ds_id = int(datasource_id)
            self.learning_service.delete_by_datasource_id(ds_id)

            self._dao.delete({"id": datasource_id})
        return db_config

    def get_list(self, db_type: Optional[str] = None) -> List[DatasourceQueryResponse]:
        """List the Datasource entities."""
        query_request = {}
        if db_type:
            query_request["db_type"] = db_type
        query_list = self.dao.get_list(query_request)
        results = []
        for item in query_list:
            results.append(self._to_query_response(item))
        return results

    def _to_query_response(
        self, res: DatasourceServeResponse
    ) -> DatasourceQueryResponse:
        param_cls = self.datasource_manager._get_param_cls(res.db_type)
        param = param_cls.from_persisted_state(model_to_dict(res))
        param_dict = param.to_dict()
        return DatasourceQueryResponse(
            type=res.db_type,
            params=param_dict,
            description=res.comment,
            id=res.id,
            db_name=res.db_name,
            gmt_created=res.gmt_created,
            gmt_modified=res.gmt_modified,
        )

    def datasource_types(self) -> ResourceTypes:
        """List the datasource types."""
        return self.datasource_manager.get_supported_types()

    def upload_db_file(self, file) -> Dict[str, str]:
        """Upload a database file and return the server-side storage path.

        Saves the file to ~/.cache/derisk/datasource/ with a unique name
        to avoid collisions while preserving the original extension.

        Args:
            file: FastAPI UploadFile instance.

        Returns:
            Dict with 'file_path' (absolute server path) and 'file_name'.
        """
        import os
        import uuid
        from pathlib import Path

        storage_dir = str(Path.home() / ".cache" / "derisk" / "datasource")
        os.makedirs(storage_dir, exist_ok=True)

        original_name = file.filename or "uploaded.db"
        # Preserve original extension, add UUID to avoid collision
        name_part, ext = os.path.splitext(original_name)
        if not ext:
            ext = ".db"
        unique_name = f"{name_part}_{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(storage_dir, unique_name)

        with open(file_path, "wb") as f:
            while True:
                chunk = file.file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                f.write(chunk)

        logger.info(f"Database file uploaded: {original_name} -> {file_path}")
        return {"file_path": file_path, "file_name": original_name}

    def test_connection(self, request: DatasourceCreateRequest) -> bool:
        """Test the connection of the datasource."""
        return self.datasource_manager.test_connection(request)

    def refresh(self, datasource_id: str) -> bool:
        """Refresh the datasource by re-learning its schema."""
        db_config = self._dao.get_one({"id": datasource_id})
        if not db_config:
            raise HTTPException(status_code=404, detail="datasource not found")

        # Trigger re-learning in background
        ds_id = int(datasource_id)
        executor = self._system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()  # type: ignore
        executor.submit(
            self.learning_service.learn_database,
            ds_id,
            db_config.db_name,
            db_config.db_type,
            "manual",
        )
        return True

    # ============================================================
    # Spec & Learning service methods (used by API endpoints)
    # ============================================================

    def trigger_learning(
        self,
        datasource_id: str,
        task_type: str = "full_learn",
        table_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger a schema learning task.

        For full_learn: if a task is already running, this node joins as
        a worker to help process remaining subtasks (distributed mode).
        """
        db_config = self._dao.get_one({"id": datasource_id})
        if not db_config:
            raise HTTPException(status_code=404, detail="datasource not found")

        ds_id = int(datasource_id)

        if task_type == "incremental":
            return self.learning_service.learn_incremental(
                ds_id, db_config.db_name, db_config.db_type, "manual"
            )
        elif task_type == "single_table" and table_name:
            result = self.learning_service.learn_single_table(
                ds_id, db_config.db_name, table_name
            )
            # Return a synthetic task response
            return {
                "id": 0,
                "datasource_id": ds_id,
                "task_type": "single_table",
                "status": "completed",
                "progress": 100,
                "total_tables": 1,
                "processed_tables": 1,
                "error_message": None,
                "trigger_type": "manual",
                "gmt_created": None,
                "gmt_modified": None,
            }
        else:
            # Check if a task is already running — join as worker
            existing = self.learning_service.get_learning_status(ds_id)
            if existing and existing.get("status") in ("running", "finalizing"):
                executor = self._system_app.get_component(
                    ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
                ).create()  # type: ignore
                executor.submit(
                    self.learning_service.join_worker,
                    ds_id,
                    db_config.db_name,
                    db_config.db_type,
                )
                return existing
            return self.learning_service.learn_database(
                ds_id, db_config.db_name, db_config.db_type, "manual"
            )

    def cancel_learning(self, datasource_id: str) -> Dict[str, Any]:
        """Cancel a running learning task for the datasource."""
        return self.learning_service.cancel_task(int(datasource_id))

    def pause_learning(self, datasource_id: str) -> Dict[str, Any]:
        """Pause a running learning task for the datasource."""
        return self.learning_service.pause_task(int(datasource_id))

    def resume_learning(self, datasource_id: str) -> Dict[str, Any]:
        """Resume a paused learning task for the datasource."""
        return self.learning_service.resume_task(int(datasource_id))

    def get_learning_status(
        self, datasource_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the latest learning task status."""
        return self.learning_service.get_learning_status(int(datasource_id))

    def get_db_spec(self, datasource_id: str) -> Optional[Dict[str, Any]]:
        """Get the database-level spec."""
        return self.spec_service.get_db_spec(int(datasource_id))

    def get_all_table_specs(self, datasource_id: str) -> List[Dict[str, Any]]:
        """Get all table specs for a datasource."""
        return self.spec_service.get_all_table_specs(int(datasource_id))

    def get_table_spec(
        self, datasource_id: str, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single table spec."""
        return self.spec_service.get_table_spec(int(datasource_id), table_name)

    def get_table_specs_batch(
        self, datasource_id: str, table_names: List[str]
    ) -> List[Dict[str, Any]]:
        """Get multiple table specs."""
        return self.spec_service.get_table_specs(int(datasource_id), table_names)

    def preview_table_data(
        self,
        datasource_id: str,
        table_name: str,
    ) -> Dict[str, Any]:
        """Preview table data: first 5 rows + last 5 rows."""
        db_config = self._dao.get_one({"id": datasource_id})
        if not db_config:
            raise HTTPException(status_code=404, detail="datasource not found")

        connector = self.datasource_manager.get_connector(db_config.db_name)

        # connector.run() returns [column_names_tuple, row1, row2, ...]
        # SQLAlchemy 2.x Row is NOT a tuple subclass, must convert via tuple()

        def _extract_rows(result):
            rows = []
            if result and len(result) > 1:
                for row in result[1:]:
                    row = tuple(row)
                    rows.append([
                        str(v)[:200] if v is not None else None for v in row
                    ])
            return rows

        # Total count
        qt = connector.quote_identifier(table_name)
        total = 0
        try:
            count_result = connector.run(f"SELECT COUNT(*) FROM {qt}")
            if count_result and len(count_result) > 1:
                row_val = tuple(count_result[1])
                if len(row_val) > 0:
                    total = int(row_val[0])
        except Exception:
            pass

        # Columns
        columns_raw = connector.get_columns(table_name)
        columns = [c.get("name", "") for c in columns_raw]

        # First 5 rows + Last 5 rows (no overlap)
        first_rows = []
        last_rows = []
        base_select = f"SELECT * FROM {qt}"
        if total <= 5:
            # Show all rows as first_rows only
            try:
                result = connector.run(connector.limit_sql(base_select, 5))
                first_rows = _extract_rows(result)
            except Exception:
                pass
        elif total <= 10:
            # Split: first N rows + remaining rows, no overlap
            try:
                result = connector.run(connector.limit_sql(base_select, 5))
                first_rows = _extract_rows(result)
            except Exception:
                pass
            try:
                remaining = total - 5
                result = connector.run(
                    connector.limit_sql(base_select, remaining, 5)
                )
                last_rows = _extract_rows(result)
            except Exception:
                pass
        else:
            # total > 10: first 5 + last 5, guaranteed no overlap
            try:
                result = connector.run(connector.limit_sql(base_select, 5))
                first_rows = _extract_rows(result)
            except Exception:
                pass
            try:
                offset = total - 5
                result = connector.run(
                    connector.limit_sql(base_select, 5, offset)
                )
                last_rows = _extract_rows(result)
            except Exception:
                pass

        return {
            "columns": columns,
            "first_rows": first_rows,
            "last_rows": last_rows,
            "total": total,
        }

    def refresh_table_sample_data(
        self,
        datasource_id: str,
        table_name: str,
    ) -> Dict[str, Any]:
        """Refresh sample data for a single table.

        Re-collects sample rows (first 2 + last 2) from the database
        and updates the table spec's sample_data_json field.

        Args:
            datasource_id: The datasource ID
            table_name: The table name to refresh

        Returns:
            Updated table spec dict
        """
        db_config = self._dao.get_one({"id": datasource_id})
        if not db_config:
            raise HTTPException(status_code=404, detail="datasource not found")

        ds_id = int(datasource_id)
        connector = self.datasource_manager.get_connector(db_config.db_name)

        return self.learning_service.refresh_sample_data(
            ds_id, connector, table_name
        )
