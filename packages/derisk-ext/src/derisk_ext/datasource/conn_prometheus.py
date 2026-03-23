"""Prometheus datasource connector.

Provides a connector for querying Prometheus HTTP API, enabling
OpenDerisk agents to access real-time metrics data for diagnostics
and root cause analysis.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import requests

from derisk.datasource.base import BaseConnector

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_STEP = "60s"


@dataclass
class PrometheusParameters:
    """Connection parameters for Prometheus HTTP API."""

    host: str = field(
        default="localhost",
        metadata={"help": "Prometheus server hostname or IP address."},
    )
    port: int = field(
        default=9090,
        metadata={"help": "Prometheus server port."},
    )
    scheme: str = field(
        default="http",
        metadata={"help": "Connection scheme, 'http' or 'https'."},
    )
    username: Optional[str] = field(
        default=None,
        metadata={"help": "Username for basic authentication."},
    )
    password: Optional[str] = field(
        default=None,
        metadata={"help": "Password for basic authentication."},
    )
    timeout: int = field(
        default=_DEFAULT_TIMEOUT_SECONDS,
        metadata={"help": "Request timeout in seconds."},
    )
    verify_ssl: bool = field(
        default=True,
        metadata={"help": "Whether to verify SSL certificates."},
    )
    custom_headers: Optional[Dict[str, str]] = field(
        default=None,
        metadata={"help": "Custom HTTP headers for requests."},
    )

    @property
    def base_url(self) -> str:
        """Return the Prometheus API base URL."""
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def api_url(self) -> str:
        """Return the Prometheus API v1 URL."""
        return f"{self.base_url}/api/v1"


class PrometheusConnector(BaseConnector):
    """Connector for Prometheus time-series database.

    Supports instant queries, range queries, series discovery, label
    enumeration, and target/rule inspection via the Prometheus HTTP API.
    """

    db_type: str = "prometheus"
    driver: str = "prometheus_http"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9090,
        scheme: str = "http",
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
        verify_ssl: bool = True,
        custom_headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize PrometheusConnector.

        Args:
            host: Prometheus server hostname or IP address.
            port: Prometheus server port.
            scheme: Connection scheme, 'http' or 'https'.
            username: Username for basic authentication.
            password: Password for basic authentication.
            timeout: Request timeout in seconds.
            verify_ssl: Whether to verify SSL certificates.
            custom_headers: Custom HTTP headers for requests.
        """
        self._params = PrometheusParameters(
            host=host,
            port=port,
            scheme=scheme,
            username=username,
            password=password,
            timeout=timeout,
            verify_ssl=verify_ssl,
            custom_headers=custom_headers,
        )
        self._session = requests.Session()
        if username and password:
            self._session.auth = (username, password)
        if custom_headers:
            self._session.headers.update(custom_headers)

    @classmethod
    def param_class(cls) -> Type[PrometheusParameters]:
        """Return the parameter class."""
        return PrometheusParameters

    @classmethod
    def from_parameters(cls, parameters: PrometheusParameters) -> "PrometheusConnector":
        """Create a connector from parameters."""
        return cls(
            host=parameters.host,
            port=parameters.port,
            scheme=parameters.scheme,
            username=parameters.username,
            password=parameters.password,
            timeout=parameters.timeout,
            verify_ssl=parameters.verify_ssl,
            custom_headers=parameters.custom_headers,
        )

    def _request(
        self, method: str, endpoint: str, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send an HTTP request to the Prometheus API.

        Args:
            method: HTTP method ('GET' or 'POST').
            endpoint: API endpoint path (e.g., '/query').
            params: Query parameters or POST data.

        Returns:
            Parsed JSON response data.

        Raises:
            ConnectionError: If the request fails.
            ValueError: If the API returns an error status.
        """
        url = f"{self._params.api_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self._params.timeout,
                    verify=self._params.verify_ssl,
                )
            else:
                response = self._session.post(
                    url,
                    data=params,
                    timeout=self._params.timeout,
                    verify=self._params.verify_ssl,
                )
            response.raise_for_status()
        except requests.exceptions.ConnectionError as error:
            raise ConnectionError(
                f"Failed to connect to Prometheus at {url}: {error}"
            ) from error
        except requests.exceptions.Timeout as error:
            raise ConnectionError(
                f"Request to Prometheus timed out after "
                f"{self._params.timeout}s: {error}"
            ) from error
        except requests.exceptions.HTTPError as error:
            raise ValueError(
                f"Prometheus API returned HTTP error: {error}"
            ) from error

        result = response.json()
        if result.get("status") != "success":
            error_type = result.get("errorType", "unknown")
            error_message = result.get("error", "Unknown error")
            raise ValueError(
                f"Prometheus query failed [{error_type}]: {error_message}"
            )
        return result.get("data", {})

    def instant_query(
        self,
        query: str,
        time: Optional[str] = None,
        timeout: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute an instant query against Prometheus.

        Args:
            query: PromQL expression to evaluate.
            time: Evaluation timestamp (RFC3339 or Unix timestamp).
                  Defaults to current server time.
            timeout: Evaluation timeout. Overrides the global -query.timeout.

        Returns:
            List of result dictionaries, each containing 'metric' labels
            and 'value' (timestamp, value) pair.
        """
        params: Dict[str, str] = {"query": query}
        if time:
            params["time"] = time
        if timeout:
            params["timeout"] = timeout

        data = self._request("GET", "/query", params)
        return data.get("result", [])

    def range_query(
        self,
        query: str,
        start: str,
        end: str,
        step: str = _DEFAULT_STEP,
        timeout: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a range query against Prometheus.

        Args:
            query: PromQL expression to evaluate.
            start: Start timestamp (RFC3339 or Unix timestamp).
            end: End timestamp (RFC3339 or Unix timestamp).
            step: Query resolution step width (e.g., '15s', '1m', '5m').
            timeout: Evaluation timeout.

        Returns:
            List of result dictionaries, each containing 'metric' labels
            and 'values' (list of [timestamp, value] pairs).
        """
        params: Dict[str, str] = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }
        if timeout:
            params["timeout"] = timeout

        data = self._request("GET", "/query_range", params)
        return data.get("result", [])

    def get_series(
        self,
        match: Union[str, List[str]],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Find time series matching label selectors.

        Args:
            match: One or more series selectors (e.g., 'up',
                   '{job="prometheus"}').
            start: Start timestamp for the lookup window.
            end: End timestamp for the lookup window.

        Returns:
            List of label sets for matching series.
        """
        if isinstance(match, str):
            match = [match]
        params: Dict[str, Any] = {"match[]": match}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        return self._request("GET", "/series", params)

    def get_label_names(
        self,
        match: Optional[Union[str, List[str]]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[str]:
        """Return a list of all label names.

        Args:
            match: Optional series selectors to filter labels.
            start: Start timestamp.
            end: End timestamp.

        Returns:
            Sorted list of label names.
        """
        params: Dict[str, Any] = {}
        if match:
            if isinstance(match, str):
                match = [match]
            params["match[]"] = match
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        return self._request("GET", "/labels", params)

    def get_label_values(
        self,
        label_name: str,
        match: Optional[Union[str, List[str]]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[str]:
        """Return a list of values for a given label name.

        Args:
            label_name: The label name to query values for.
            match: Optional series selectors to filter results.
            start: Start timestamp.
            end: End timestamp.

        Returns:
            List of label values.
        """
        params: Dict[str, Any] = {}
        if match:
            if isinstance(match, str):
                match = [match]
            params["match[]"] = match
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        return self._request("GET", f"/label/{label_name}/values", params)

    def get_targets(self, state: Optional[str] = None) -> Dict[str, Any]:
        """Return an overview of the current state of scrape targets.

        Args:
            state: Filter targets by state ('active', 'dropped', 'any').

        Returns:
            Dictionary with 'activeTargets' and 'droppedTargets' lists.
        """
        params: Dict[str, str] = {}
        if state:
            params["state"] = state
        return self._request("GET", "/targets", params)

    def get_rules(self, rule_type: Optional[str] = None) -> Dict[str, Any]:
        """Return a list of alerting and recording rules.

        Args:
            rule_type: Filter by rule type ('alert' or 'record').

        Returns:
            Dictionary with 'groups' containing rule definitions.
        """
        params: Dict[str, str] = {}
        if rule_type:
            params["type"] = rule_type
        return self._request("GET", "/rules", params)

    def get_alerts(self) -> List[Dict[str, Any]]:
        """Return a list of all active alerts.

        Returns:
            List of active alert dictionaries.
        """
        data = self._request("GET", "/alerts")
        return data.get("alerts", [])

    def check_health(self) -> bool:
        """Check if the Prometheus server is healthy.

        Returns:
            True if the server is healthy, False otherwise.
        """
        try:
            url = f"{self._params.base_url}/-/healthy"
            response = self._session.get(
                url,
                timeout=self._params.timeout,
                verify=self._params.verify_ssl,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def get_metadata(
        self, metric: Optional[str] = None, limit: Optional[int] = None
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return metadata about metrics currently scraped.

        Args:
            metric: Filter metadata for a specific metric name.
            limit: Maximum number of metrics to return.

        Returns:
            Dictionary mapping metric names to lists of metadata entries,
            each containing 'type', 'help', and 'unit'.
        """
        params: Dict[str, Any] = {}
        if metric:
            params["metric"] = metric
        if limit is not None:
            params["limit"] = str(limit)
        return self._request("GET", "/metadata", params)

    def run(self, command: str, fetch: str = "all") -> List:
        """Execute a PromQL query (implements BaseConnector interface).

        This method provides compatibility with the BaseConnector interface.
        The 'command' parameter is treated as a PromQL expression for an
        instant query.

        Args:
            command: PromQL expression to evaluate.
            fetch: Unused, kept for interface compatibility.

        Returns:
            List of query results.
        """
        results = self.instant_query(command)
        return self._format_results(results)

    @staticmethod
    def _format_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format Prometheus query results into a flat list.

        Args:
            results: Raw Prometheus API result list.

        Returns:
            List of formatted result dictionaries with 'metric', 'timestamp',
            and 'value' keys.
        """
        formatted = []
        for result in results:
            metric_labels = result.get("metric", {})
            metric_name = metric_labels.get("__name__", "unknown")

            if "value" in result:
                timestamp, value = result["value"]
                formatted.append({
                    "metric": metric_name,
                    "labels": metric_labels,
                    "timestamp": datetime.fromtimestamp(
                        timestamp, tz=timezone.utc
                    ).isoformat(),
                    "value": value,
                })
            elif "values" in result:
                for timestamp, value in result["values"]:
                    formatted.append({
                        "metric": metric_name,
                        "labels": metric_labels,
                        "timestamp": datetime.fromtimestamp(
                            timestamp, tz=timezone.utc
                        ).isoformat(),
                        "value": value,
                    })
        return formatted

    @classmethod
    def is_normal_type(cls) -> bool:
        """Return whether the connector is a normal type."""
        return True

    def close(self):
        """Close the HTTP session."""
        if self._session:
            self._session.close()

    def __repr__(self) -> str:
        """Return a string representation of the connector."""
        return (
            f"PrometheusConnector("
            f"host={self._params.host!r}, "
            f"port={self._params.port}, "
            f"scheme={self._params.scheme!r})"
        )
