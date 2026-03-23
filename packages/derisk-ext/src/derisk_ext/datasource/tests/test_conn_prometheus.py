"""Tests for PrometheusConnector."""

import json
from unittest.mock import MagicMock, patch

import pytest

from derisk_ext.datasource.conn_prometheus import (
    PrometheusConnector,
    PrometheusParameters,
)


class TestPrometheusParameters:
    """Tests for PrometheusParameters."""

    def test_default_values(self):
        params = PrometheusParameters()
        assert params.host == "localhost"
        assert params.port == 9090
        assert params.scheme == "http"
        assert params.username is None
        assert params.password is None
        assert params.timeout == 30
        assert params.verify_ssl is True

    def test_base_url(self):
        params = PrometheusParameters(host="prom.example.com", port=9090)
        assert params.base_url == "http://prom.example.com:9090"

    def test_api_url(self):
        params = PrometheusParameters(
            host="prom.example.com", port=9090, scheme="https"
        )
        assert params.api_url == "https://prom.example.com:9090/api/v1"


class TestPrometheusConnector:
    """Tests for PrometheusConnector."""

    def setup_method(self):
        self.connector = PrometheusConnector(
            host="localhost", port=9090, scheme="http"
        )

    def test_from_parameters(self):
        params = PrometheusParameters(
            host="prom.example.com", port=9090, scheme="https"
        )
        connector = PrometheusConnector.from_parameters(params)
        assert connector._params.host == "prom.example.com"
        assert connector._params.scheme == "https"

    def test_db_type(self):
        assert self.connector.db_type == "prometheus"

    def test_repr(self):
        result = repr(self.connector)
        assert "PrometheusConnector" in result
        assert "localhost" in result

    @patch("derisk_ext.datasource.conn_prometheus.requests.Session")
    def test_instant_query(self, mock_session_cls):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "prometheus"},
                        "value": [1700000000, "1"],
                    }
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        connector = PrometheusConnector(host="localhost", port=9090)
        results = connector.instant_query("up")
        assert len(results) == 1
        assert results[0]["metric"]["__name__"] == "up"

    @patch("derisk_ext.datasource.conn_prometheus.requests.Session")
    def test_range_query(self, mock_session_cls):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "prometheus"},
                        "values": [
                            [1700000000, "1"],
                            [1700000060, "1"],
                        ],
                    }
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        connector = PrometheusConnector(host="localhost", port=9090)
        results = connector.range_query(
            "up", start="1700000000", end="1700000120", step="60s"
        )
        assert len(results) == 1
        assert len(results[0]["values"]) == 2

    @patch("derisk_ext.datasource.conn_prometheus.requests.Session")
    def test_run_interface(self, mock_session_cls):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "prometheus"},
                        "value": [1700000000, "1"],
                    }
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        connector = PrometheusConnector(host="localhost", port=9090)
        results = connector.run("up")
        assert len(results) == 1
        assert results[0]["metric"] == "up"
        assert results[0]["value"] == "1"

    @patch("derisk_ext.datasource.conn_prometheus.requests.Session")
    def test_check_health_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        connector = PrometheusConnector(host="localhost", port=9090)
        assert connector.check_health() is True

    @patch("derisk_ext.datasource.conn_prometheus.requests.Session")
    def test_query_error_handling(self, mock_session_cls):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "errorType": "bad_data",
            "error": "invalid expression",
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        connector = PrometheusConnector(host="localhost", port=9090)
        with pytest.raises(ValueError, match="invalid expression"):
            connector.instant_query("invalid{")

    def test_format_results_instant(self):
        raw_results = [
            {
                "metric": {"__name__": "cpu_usage", "instance": "host1:9090"},
                "value": [1700000000, "0.85"],
            }
        ]
        formatted = PrometheusConnector._format_results(raw_results)
        assert len(formatted) == 1
        assert formatted[0]["metric"] == "cpu_usage"
        assert formatted[0]["value"] == "0.85"
        assert "timestamp" in formatted[0]
        assert formatted[0]["labels"]["instance"] == "host1:9090"

    def test_format_results_range(self):
        raw_results = [
            {
                "metric": {"__name__": "cpu_usage"},
                "values": [
                    [1700000000, "0.80"],
                    [1700000060, "0.85"],
                    [1700000120, "0.90"],
                ],
            }
        ]
        formatted = PrometheusConnector._format_results(raw_results)
        assert len(formatted) == 3
        assert formatted[0]["value"] == "0.80"
        assert formatted[2]["value"] == "0.90"

    def test_close(self):
        self.connector.close()
