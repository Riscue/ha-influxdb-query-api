"""
Tests for InfluxDB query service.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

from custom_components.influxdb_query_api.influxdb_service import (
    run_flux_query, get_connection_manager, cleanup_connections,
    get_connection_status, _build_safe_query
)
from custom_components.influxdb_query_api.utils import SecurityValidator


class TestInfluxDBService:
    """Test cases for InfluxDB query service."""

    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            "host": "localhost",
            "port": "8086",
            "token": "test-token",
            "organization": "test-org",
            "bucket": "homeassistant"
        }

    @pytest.fixture
    def mock_manager(self):
        """Mock connection manager."""
        manager = Mock()
        manager.execute_query = AsyncMock(return_value=[
            {"time": "2025-01-10T12:00:00Z", "value": 25.5},
            {"time": "2025-01-10T12:05:00Z", "value": 26.0}
        ])
        return manager

    def test_get_connection_manager_creates_instance(self, config):
        """Test connection manager creation."""
        # Clear global variable
        import custom_components.influxdb_query_api.influxdb_service as service
        service._connection_manager = None

        manager = get_connection_manager(config)

        assert manager is not None
        assert service._connection_manager == manager

    def test_get_connection_manager_returns_existing(self, config):
        """Test connection manager returns existing instance."""
        # Set global variable
        import custom_components.influxdb_query_api.influxdb_service as service
        existing_manager = Mock()
        service._connection_manager = existing_manager

        manager = get_connection_manager(config)

        assert manager == existing_manager

    def test_get_connection_status_not_initialized(self):
        """Test connection status when not initialized."""
        import custom_components.influxdb_query_api.influxdb_service as service
        service._connection_manager = None

        status = get_connection_status()
        assert status == {"status": "Not initialized"}

    def test_get_connection_status_initialized(self):
        """Test connection status when initialized."""
        import custom_components.influxdb_query_api.influxdb_service as service
        mock_manager = Mock()
        mock_manager.get_pool_status.return_value = {"status": "active", "connections": 3}
        service._connection_manager = mock_manager

        status = get_connection_status()
        assert status == {"status": "active", "connections": 3}

    @patch('custom_components.influxdb_query_api.influxdb_service.get_connection_manager')
    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_run_flux_query_success(self, mock_validator, mock_get_manager, config, mock_manager):
        """Test successful query execution."""
        # Setup mocks
        mock_get_manager.return_value = mock_manager

        mock_validator.validate_query_parameters.return_value = {
            'domain': 'sensor',
            'entity': 'temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        }

        result = await run_flux_query(config, 'sensor.temperature', '-1h', 'now()')

        # Verify validation was called
        mock_validator.validate_query_parameters.assert_called_once_with({
            'entity_id': 'sensor.temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        })

        # Verify manager was used
        mock_manager.execute_query.assert_called_once()

        # Verify result
        assert len(result) == 2
        assert result[0]["time"] == "2025-01-10T12:00:00Z"
        assert result[0]["value"] == 25.5

    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_run_flux_query_validation_error(self, mock_validator, config):
        """Test query execution with validation error."""
        mock_validator.validate_query_parameters.side_effect = ValueError("Invalid entity ID")

        with pytest.raises(ValueError, match="Input validation failed: Invalid entity ID"):
            await run_flux_query(config, 'invalid_entity', '-1h', 'now()')

    @patch('custom_components.influxdb_query_api.influxdb_service.get_connection_manager')
    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_run_flux_query_database_error(self, mock_validator, mock_get_manager, config, mock_manager):
        """Test query execution with database error."""
        # Setup mocks
        mock_get_manager.return_value = mock_manager

        mock_validator.validate_query_parameters.return_value = {
            'domain': 'sensor',
            'entity': 'temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        }

        mock_manager.execute_query.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Query execution failed: Connection failed"):
            await run_flux_query(config, 'sensor.temperature', '-1h', 'now()')

    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_run_flux_query_injection_detected(self, mock_validator, config):
        """Test query execution when injection is detected after validation."""
        mock_validator.validate_query_parameters.return_value = {
            'domain': 'sensor',
            'entity': 'temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        }

        # Mock check_for_injection_attempts to return True
        mock_validator.check_for_injection_attempts.return_value = True

        with pytest.raises(ValueError, match="Potentially dangerous query detected"):
            await run_flux_query(config, 'sensor.temperature', '-1h', 'now()')

    def test_build_safe_query(self):
        """Test safe query building."""
        query = _build_safe_query("homeassistant", "sensor", "temperature", "-1h", "now()")

        expected = '''from(bucket: "homeassistant")
    |> range(start: -1h, stop: now())
    |> filter(fn: (r) => r["_measurement"] == "sensor" and r["entity_id"] == "temperature" and r["_field"] == "value")'''

        assert query == expected

    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    def test_build_safe_query_injection_detected(self, mock_validator):
        """Test safe query building detects injection."""
        mock_validator.build_safe_filter.return_value = 'r["_measurement"] == "sensor"'
        mock_validator.check_for_injection_attempts.return_value = True

        with pytest.raises(ValueError, match="Potentially dangerous query detected"):
            _build_safe_query("homeassistant", "sensor", "temperature", "-1h", "now()")

    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_cleanup_connections(self, mock_validator):
        """Test connection cleanup."""
        # Setup mock manager
        mock_manager = Mock()
        mock_manager.cleanup = AsyncMock()

        import custom_components.influxdb_query_api.influxdb_service as service
        service._connection_manager = mock_manager

        await cleanup_connections()

        mock_manager.cleanup.assert_called_once()
        assert service._connection_manager is None

    @pytest.mark.asyncio
    async def test_cleanup_connections_no_manager(self):
        """Test connection cleanup when no manager exists."""
        import custom_components.influxdb_query_api.influxdb_service as service
        service._connection_manager = None

        # Should not raise error
        await cleanup_connections()
        assert service._connection_manager is None

    @patch('custom_components.influxdb_query_api.influxdb_service.get_connection_manager')
    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_query_with_different_field_types(self, mock_validator, mock_get_manager, config, mock_manager):
        """Test query execution with different field value types."""
        # Setup mocks
        mock_get_manager.return_value = mock_manager

        mock_validator.validate_query_parameters.return_value = {
            'domain': 'sensor',
            'entity': 'temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        }

        # Mock different value types
        mock_manager.execute_query.return_value = [
            {"time": "2025-01-10T12:00:00Z", "value": 25.5},      # float
            {"time": "2025-01-10T12:05:00Z", "value": "on"},      # string
            {"time": "2025-01-10T12:10:00Z", "value": True},      # boolean
            {"time": "2025-01-10T12:15:00Z", "value": 42},        # integer
        ]

        result = await run_flux_query(config, 'sensor.temperature', '-1h', 'now()')

        assert len(result) == 4
        assert result[0]["value"] == 25.5
        assert result[1]["value"] == "on"
        assert result[2]["value"] is True
        assert result[3]["value"] == 42

    @patch('custom_components.influxdb_query_api.influxdb_service.get_connection_manager')
    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_query_empty_result(self, mock_validator, mock_get_manager, config, mock_manager):
        """Test query execution with empty result."""
        # Setup mocks
        mock_get_manager.return_value = mock_manager

        mock_validator.validate_query_parameters.return_value = {
            'domain': 'sensor',
            'entity': 'nonexistent',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        }

        # Mock empty result
        mock_manager.execute_query.return_value = []

        result = await run_flux_query(config, 'sensor.nonexistent', '-1h', 'now()')

        assert result == []

    @patch('custom_components.influxdb_query_api.influxdb_service.get_connection_manager')
    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    @pytest.mark.asyncio
    async def test_query_complex_time_ranges(self, mock_validator, mock_get_manager, config, mock_manager):
        """Test query execution with complex time range expressions."""
        # Setup mocks
        mock_get_manager.return_value = mock_manager

        mock_validator.validate_query_parameters.return_value = {
            'domain': 'sensor',
            'entity': 'temperature',
            'bucket': 'homeassistant',
            'range_start': '2025-01-10T00:00:00Z',
            'range_stop': '2025-01-10T23:59:59Z'
        }

        mock_manager.execute_query.return_value = [{"time": "2025-01-10T12:00:00Z", "value": 25.5}]

        result = await run_flux_query(
            config,
            'sensor.temperature',
            '2025-01-10T00:00:00Z',
            '2025-01-10T23:59:59Z'
        )

        # Verify time ranges were validated and used
        mock_validator.validate_query_parameters.assert_called_once_with({
            'entity_id': 'sensor.temperature',
            'bucket': 'homeassistant',
            'range_start': '2025-01-10T00:00:00Z',
            'range_stop': '2025-01-10T23:59:59Z'
        })

        assert len(result) == 1

    @patch('custom_components.influxdb_query_api.influxdb_service.SecurityValidator')
    def test_build_safe_query_with_special_chars(self, mock_validator):
        """Test safe query building with special characters in identifiers."""
        mock_validator.build_safe_filter.return_value = 'r["_measurement"] == "sensor" and r["entity_id"] == "temp_01"'
        mock_validator.check_for_injection_attempts.return_value = False

        query = _build_safe_query("bucket", "sensor", "temp_01", "-1h", "now()")

        assert "from(bucket: \"bucket\")" in query
        assert "range(start: -1h, stop: now())" in query
        assert "filter(fn: (r) => r[\"_measurement\"] == \"sensor\" and r[\"entity_id\"] == \"temp_01\" and r[\"_field\"] == \"value\")" in query