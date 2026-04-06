"""Neo4j Connector."""

from dataclasses import dataclass, field
from typing import Dict, Generator, Iterator, List, Type, cast

from derisk.core.awel.flow import (
    TAGS_ORDER_HIGH,
    ResourceCategory,
    auto_register_resource,
)
from derisk.datasource.base import BaseConnector
from derisk.datasource.parameter import BaseDatasourceParameters
from derisk.util.i18n_utils import _


@auto_register_resource(
    label=_("Neo4j datasource"),
    category=ResourceCategory.DATABASE,
    tags={"order": TAGS_ORDER_HIGH},
    description=_(
        "Neo4j is a highly scalable native graph database, purpose-built to leverage "
        "data relationships."
    ),
)
@dataclass
class Neo4jParameters(BaseDatasourceParameters):
    """Neo4j connection parameters."""

    __type__ = "neo4j"

    host: str = field(metadata={"help": _("Neo4j server host")})
    user: str = field(metadata={"help": _("Neo4j server user")})
    password: str = field(
        default="",
        metadata={
            "help": _(
                "Database password, you can write your password directly, or "
                "use environment variables."
            ),
            "tags": "privacy",
        },
    )
    port: int = field(
        default=7687, metadata={"help": _("Neo4j server port, default 7687")}
    )
    database: str = field(
        default="neo4j", metadata={"help": _("Database name, default 'neo4j'")}
    )

    def create_connector(self) -> "BaseConnector":
        """Create Neo4j connector."""
        return Neo4jConnector.from_parameters(self)

    def db_url(self, ssl=False, charset=None):
        """Get the database URL."""
        raise NotImplementedError("Neo4j does not support db_url")


class Neo4jConnector(BaseConnector):
    """Neo4j connector."""

    db_type: str = "neo4j"
    driver: str = "bolt"
    dialect: str = "cypher"

    def __init__(self, driver, database):
        """Initialize the connector with a Neo4j driver."""
        self._driver = driver
        self._database = database
        self._schema = None
        self._is_closed = False
        self._graph = database

    @classmethod
    def param_class(cls) -> Type[Neo4jParameters]:
        """Return the parameter class."""
        return Neo4jParameters

    @classmethod
    def from_parameters(cls, parameters: Neo4jParameters) -> "Neo4jConnector":
        """Create a new Neo4jConnector from parameters."""
        return cls.from_uri_db(
            parameters.host,
            parameters.port,
            parameters.user,
            parameters.password,
            parameters.database,
        )

    @classmethod
    def from_uri_db(
        cls, host: str, port: int, user: str, pwd: str, db_name: str, **kwargs
    ) -> "Neo4jConnector":
        """Create a new Neo4jConnector from host, port, user, pwd, db_name."""
        try:
            from neo4j import GraphDatabase

            db_url = f"{cls.driver}://{host}:{str(port)}"
            driver = GraphDatabase.driver(db_url, auth=(user, pwd))
            driver.verify_connectivity()
            return cast(Neo4jConnector, cls(driver=driver, database=db_name))

        except ImportError as err:
            raise ImportError(
                "neo4j package is not installed, please install it with "
                "`pip install neo4j`"
            ) from err

    def create_graph(self, graph_name: str) -> bool:
        """Create a graph in Neo4j."""
        return True

    def is_exist(self, graph_name: str) -> bool:
        """Check if a database exists in Neo4j."""
        try:
            databases = self.get_database_names()
            return graph_name in databases
        except Exception:
            return True

    def delete_graph(self, graph_name: str) -> None:
        """Delete all data from the current database."""
        with self._driver.session(database=self._database) as session:
            session.run("MATCH ()-[r]->() DELETE r")
            session.run("MATCH (n) DELETE n")

    def get_system_info(self) -> Dict:
        """Get Neo4j system information."""
        system_info = {}
        try:
            with self._driver.session(database="system") as session:
                result = session.run("CALL dbms.components() YIELD versions")
                for record in result:
                    versions = record["versions"]
                    if versions:
                        system_info["neo4j_version"] = versions[0]
                        system_info["lgraph_version"] = versions[0]
        except Exception:
            system_info["neo4j_version"] = "unknown"
            system_info["lgraph_version"] = "5.0.0"

        return system_info

    def get_table_names(self) -> Iterator[str]:
        """Get all table names from Neo4j (node labels and relationship types)."""
        with self._driver.session(database=self._database) as session:
            result = session.run("CALL db.labels()")
            node_labels = [record["label"] + "_node" for record in result]

            result = session.run("CALL db.relationshipTypes()")
            rel_types = [
                record["relationshipType"] + "_relationship" for record in result
            ]

            return iter(node_labels + rel_types)

    def get_columns(self, table_name: str, table_type: str = "node") -> List[Dict]:
        """Retrieve the properties for a specified node label or relationship type."""
        with self._driver.session(database=self._database) as session:
            if table_type == "node":
                label_name = table_name.replace("_node", "")
                check_result = session.run("CALL db.labels()")
                existing_labels = [record["label"] for record in check_result]
                if label_name not in existing_labels:
                    return []

                query = f"""
                MATCH (n:`{label_name}`)
                WITH n LIMIT 100
                UNWIND keys(n) AS key
                RETURN DISTINCT key AS property
                """
            else:
                rel_name = table_name.replace("_relationship", "")
                check_result = session.run("CALL db.relationshipTypes()")
                existing_rels = [record["relationshipType"] for record in check_result]
                if rel_name not in existing_rels:
                    return []

                query = f"""
                MATCH ()-[r:`{rel_name}`]->()
                WITH r LIMIT 100
                UNWIND keys(r) AS key
                RETURN DISTINCT key AS property
                """

            result = session.run(query)
            properties = []
            for record in result:
                prop_dict = {
                    "name": record["property"],
                    "type": "string",
                    "default_expression": "",
                    "is_in_primary_key": False,
                    "comment": record["property"],
                }
                properties.append(prop_dict)
            return properties

    def get_indexes(self, table_name: str, table_type: str = "node") -> List[Dict]:
        """Get indexes for a specified node label."""
        with self._driver.session(database=self._database) as session:
            result = session.run("SHOW INDEXES")
            indexes = []
            for record in result:
                labels_or_types = record.get("labelsOrTypes") or []
                if table_name in labels_or_types:
                    index_dict = {
                        "name": record.get("name", ""),
                        "column_names": record.get("properties") or [],
                    }
                    indexes.append(index_dict)
            return indexes

    def get_grants(self):
        """Get grants."""
        return []

    def get_collation(self):
        """Get collation."""
        return "UTF-8"

    def get_charset(self):
        """Get character_set of current database."""
        return "UTF-8"

    def table_simple_info(self):
        """Get table simple info."""
        return []

    def close(self):
        """Close the Neo4j driver."""
        if self._is_closed:
            return
        self._driver.close()
        self._is_closed = True

    def run(self, query: str, fetch: str = "all", **params) -> List:
        """Run Cypher query."""
        with self._driver.session(database=self._database) as session:
            try:
                result = session.run(query, **params)
                return list(result)
            except Exception as e:
                raise Exception(f"Query execution failed: {e}\nQuery: {query}") from e

    def run_stream(self, query: str) -> Generator:
        """Run Cypher query with streaming results."""
        with self._driver.session(database=self._database) as session:
            result = session.run(query)
            yield from result

    def get_database_names(self) -> List[str]:
        """Get all database names."""
        with self._driver.session(database="system") as session:
            result = session.run("SHOW DATABASES")
            return [record["name"] for record in result]

    @classmethod
    def is_graph_type(cls) -> bool:
        """Return whether the connector is a graph database connector."""
        return True
