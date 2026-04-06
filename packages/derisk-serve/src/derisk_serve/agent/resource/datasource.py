import dataclasses
import logging
from typing import Any, List, Optional, Tuple, Type, Union, cast

from derisk._private.config import Config
from derisk.agent.resource.database import (
    _DEFAULT_PROMPT_TEMPLATE,
    _DEFAULT_PROMPT_TEMPLATE_ZH,
    DBParameters,
    RDBMSConnectorResource,
)
from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    FunctionDynamicOptions,
    OptionValue,
    Parameter,
    ResourceCategory,
    register_resource,
)
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _

CFG = Config()

logger = logging.getLogger(__name__)


def _load_datasource() -> List[OptionValue]:
    dbs = CFG.local_db_manager.get_db_list()
    results = [
        OptionValue(
            label="[" + db["db_type"] + "]" + db["db_name"],
            name=db["db_name"],
            value=db["db_name"],
        )
        for db in dbs
    ]
    return results


@dataclasses.dataclass
class DatasourceDBParameters(DBParameters):
    """The DB parameters for the datasource."""

    db_name: str = dataclasses.field(metadata={"help": "DB name"})

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["DatasourceDBParameters"],
        version: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Convert the parameters to configurations."""
        conf: List[ParameterDescription] = cast(
            List[ParameterDescription],
            super().to_configurations(
                parameters,
                **kwargs,
            ),
        )
        version = version or cls._resource_version()
        if version != "v1":
            return conf
        # Compatible with old version
        for param in conf:
            if param.param_name == "db_name":
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "DatasourceDBParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        if "db_name" not in copied_data and "value" in copied_data:
            copied_data["db_name"] = copied_data.pop("value")
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


@register_resource(
    _("Datasource Resource"),
    "datasource",
    category=ResourceCategory.DATABASE,
    description=_(
        "Connect to a datasource(retrieve table schemas and execute SQL to fetch data)."
    ),
    tags={"order": TAGS_ORDER_HIGH},
    parameters=[
        Parameter.build_from(
            _("Datasource Name"),
            "name",
            str,
            optional=True,
            default="datasource",
            description=_("The name of the datasource, default is 'datasource'."),
        ),
        Parameter.build_from(
            _("DB Name"),
            "db_name",
            str,
            description=_("The name of the database."),
            options=FunctionDynamicOptions(func=_load_datasource),
        ),
        Parameter.build_from(
            _("Prompt Template"),
            "prompt_template",
            str,
            optional=True,
            default=(
                _DEFAULT_PROMPT_TEMPLATE_ZH
                if CFG.LANGUAGE == "zh"
                else _DEFAULT_PROMPT_TEMPLATE
            ),
            description=_("The prompt template to build a database prompt."),
        ),
    ],
)
class DatasourceResource(RDBMSConnectorResource):
    def __init__(self, name: str, db_name: Optional[str] = None, **kwargs):
        conn = CFG.local_db_manager.get_connector(db_name)
        self._spec_service = None
        self._schema_link_service = None
        self._datasource_id = None
        super().__init__(name, connector=conn, db_name=db_name, **kwargs)

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[DatasourceDBParameters]:
        dbs = CFG.local_db_manager.get_db_list(user_id=kwargs.get("user_id", None))
        results = [
            {
                "label": "[" + db["db_type"] + "]" + db["db_name"],
                "key": db["db_name"],
                "description": db["comment"],
            }
            for db in dbs
        ]

        @dataclasses.dataclass
        class _DynDBParameters(DatasourceDBParameters):
            db_name: str = dataclasses.field(
                metadata={"help": "DB name", "valid_values": results}
            )

        return _DynDBParameters

    @property
    def spec_service(self):
        """Lazy-load the spec service."""
        if self._spec_service is None:
            try:
                from derisk_serve.datasource.service.spec_service import (
                    DbSpecService,
                )

                self._spec_service = DbSpecService()
            except ImportError:
                logger.debug("DbSpecService not available, using fallback")
                self._spec_service = None
        return self._spec_service

    def _resolve_datasource_id(self) -> Optional[int]:
        """Resolve the datasource ID from the db_name."""
        if self._datasource_id is not None:
            return self._datasource_id
        try:
            from derisk_serve.datasource.manages.connect_config_db import (
                ConnectConfigDao,
            )

            dao = ConnectConfigDao()
            entity = dao.get_by_names(self._db_name)
            if entity:
                self._datasource_id = entity.id
                return self._datasource_id
        except Exception:
            pass
        return None

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: Optional[str] = None,
        resource_name: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, Optional[list]]:
        """Get the prompt using spec-based progressive loading.

        Stage 1: Returns the database-level spec (table index) if available.
        Falls back to live schema introspection if no spec exists.
        """
        datasource_id = self._resolve_datasource_id()
        if datasource_id and self.spec_service:
            try:
                if self.spec_service.has_spec(datasource_id):
                    db_spec_prompt = (
                        self.spec_service.format_db_spec_for_prompt(datasource_id)
                    )
                    if db_spec_prompt:
                        return (
                            self._prompt_template.format(
                                db_type=self._db_type, schemas=db_spec_prompt
                            ),
                            None,
                        )
            except Exception as e:
                logger.warning(f"Error loading spec for prompt: {e}")

        # Fallback to live schema introspection
        return await super().get_prompt(
            lang=lang,
            prompt_type=prompt_type,
            question=question,
            resource_name=resource_name,
            **kwargs,
        )

    async def get_table_context(
        self, table_names: List[str]
    ) -> str:
        """Stage 2: Get detailed specs for specific tables.

        Called by the GetTableSpec agent tool when the agent needs
        detailed schema information for specific tables.
        """
        datasource_id = self._resolve_datasource_id()
        if datasource_id and self.spec_service:
            try:
                return self.spec_service.format_table_specs_for_prompt(
                    datasource_id, table_names
                )
            except Exception as e:
                logger.warning(f"Error loading table specs: {e}")

        # Fallback to live introspection
        return self.connector.get_table_info(table_names)

    @property
    def schema_link_service(self):
        """Lazy-load the Schema Link service."""
        if self._schema_link_service is None:
            try:
                from derisk_serve.datasource.service.schema_link_service import (
                    SchemaLinkService,
                )

                self._schema_link_service = SchemaLinkService()
            except ImportError:
                logger.debug("SchemaLinkService not available")
                self._schema_link_service = None
        return self._schema_link_service

    def get_schema_link(
        self, db: str, question: Optional[str] = None
    ) -> Union[str, List[str]]:
        """Return the schema link of the database.

        Uses Schema Linking with Spec when a question is provided.
        Falls back to Spec overview, then live introspection.
        """
        datasource_id = self._resolve_datasource_id()
        if datasource_id and self.spec_service:
            try:
                if self.spec_service.has_spec(datasource_id):
                    # With question: use Schema Linking to highlight relevant tables
                    if question and self.schema_link_service:
                        try:
                            recommendations = (
                                self.schema_link_service.suggest_tables(
                                    datasource_id, question
                                )
                            )
                            if recommendations:
                                highlighted = [
                                    r.table_name for r in recommendations
                                ]
                                return (
                                    self.spec_service
                                    .format_db_spec_for_prompt(datasource_id)
                                    + "\n\nRecommended tables for this question: "
                                    + ", ".join(highlighted)
                                )
                        except Exception as e:
                            logger.debug(f"Schema linking failed: {e}")

                    return self.spec_service.format_db_spec_for_prompt(
                        datasource_id
                    )
            except Exception:
                pass

        # Fallback
        conn = CFG.local_db_manager.get_connector(db)
        return conn.table_simple_info()
