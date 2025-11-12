"""
Integration tests for the complete system.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import json

from custom_components.influxdb_query_api.influxdb_service import run_flux_query, cleanup_connections
from custom_components.influxdb_query_api.utils import SecurityValidator


class TestIntegration:
    """Integration tests for the complete system."""

    @pytest.fixture
    def full_config(self):
        """Complete configuration."""
        return {
            "host": "localhost",
            "port": "8086",
            "token": "test-token-123",
            "organization": "test-org",
            "bucket": "homeassistant",
            "timeout": 10000,
            "ssl": False,
            "verify_ssl": True,
            "pool_size": 5,
            "max_retries": 3
        }

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_end_to_end_secure_query_execution(self, mock_client_class, full_config):
        """Test complete secure query execution from input to result."""
        # Mock InfluxDB client and response
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        # Mock query response
        mock_record = Mock()
        mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
        mock_record.get_value.return_value = 23.7

        mock_table = Mock()
        mock_table.records = [mock_record]

        mock_query_api = Mock()
        mock_query_api.query.return_value = [mock_table]
        mock_client.query_api.return_value = mock_query_api

        # Execute query
        result = await run_flux_query(
            full_config,
            "sensor.living_room_temperature",
            "-1h",
            "now()"
        )

        # Verify result
        assert len(result) == 1
        assert result[0]["time"] == "2025-01-10T12:00:00Z"
        assert result[0]["value"] == 23.7

        # Verify query was secure (no injection)
        call_args = mock_query_api.query.call_args[0][0]
        assert "from(bucket: \"homeassistant\")" in call_args
        assert "range(start: -1h, stop: now())" in call_args
        assert "r[\"_measurement\"] == \"sensor\"" in call_args
        assert "r[\"entity_id\"] == \"living_room_temperature\"" in call_args

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_security_validation_prevents_injection(self, mock_client_class, full_config):
        """Test that security validation prevents injection attacks."""
        # Mock client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        mock_query_api = Mock()
        mock_client.query_api.return_value = mock_query_api

        # Attempt injection through entity_id
        malicious_inputs = [
            "sensor.temperature'; DROP TABLE measurements; --",
            "sensor.temperature\" OR 1=1 --",
            "sensor.temperature'; exec('rm -rf /'); --",
            "sensor.temperature'; import 'influxdata/influxdb/v1'; --",
            "sensor.temperature'; system('cat /etc/passwd'); --"
        ]

        for malicious_input in malicious_inputs:
            with pytest.raises(ValueError, match="Input validation failed"):
                await run_flux_query(
                    full_config,
                    malicious_input,
                    "-1h",
                    "now()"
                )

        # Verify no queries were executed
        mock_query_api.query.assert_not_called()

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_time_range_injection_prevention(self, mock_client_class, full_config):
        """Test that injection through time range parameters is prevented."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        mock_query_api = Mock()
        mock_client.query_api.return_value = mock_query_api

        # Attempt injection through time range
        malicious_time_ranges = [
            "2025-01-10T00:00:00Z'; DROP TABLE measurements; --",
            "-1h'; import 'influxdata/influxdb/v1'; --",
            "now(); exec('malicious command'); --"
        ]

        for malicious_start in malicious_time_ranges:
            with pytest.raises(ValueError, match="Input validation failed"):
                await run_flux_query(
                    full_config,
                    "sensor.temperature",
                    malicious_start,
                    "now()"
                )

        # Verify no queries were executed
        mock_query_api.query.assert_not_called()

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_connection_pool_management(self, mock_client_class, full_config):
        """Test connection pool management during multiple queries."""
        # Create multiple mock clients
        mock_clients = []
        for i in range(3):
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_clients.append(mock_client)

        mock_client_class.side_effect = mock_clients

        # Mock query response for all clients
        mock_record = Mock()
        mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
        mock_record.get_value.return_value = 25.0

        mock_table = Mock()
        mock_table.records = [mock_record]

        # Execute multiple concurrent queries
        async def execute_query(entity_id):
            mock_query_api = Mock()
            mock_query_api.query.return_value = [mock_table]

            # Mock the query_api for each client
            for mock_client in mock_clients:
                mock_client.query_api.return_value = mock_query_api

            return await run_flux_query(
                full_config,
                entity_id,
                "-1h",
                "now()"
            )

        # Run concurrent queries
        entity_ids = [
            "sensor.temperature",
            "sensor.humidity",
            "binary_sensor.motion"
        ]

        results = await asyncio.gather(*[
            execute_query(entity_id) for entity_id in entity_ids
        ])

        # Verify all queries succeeded
        assert len(results) == 3
        for result in results:
            assert len(result) == 1
            assert result[0]["value"] == 25.0

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, mock_client_class, full_config):
        """Test error handling and recovery mechanisms."""
        # Mock client that initially fails then succeeds
        mock_client = Mock()
        mock_client.ping.side_effect = [
            Exception("Initial connection failed"),
            True  # Second ping succeeds
        ]
        mock_client_class.return_value = mock_client

        # Mock query response
        mock_record = Mock()
        mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
        mock_record.get_value.return_value = 24.0

        mock_table = Mock()
        mock_table.records = [mock_record]

        mock_query_api = Mock()
        mock_query_api.query.side_effect = [
            Exception("Query timeout"),
            [mock_table]  # Second query succeeds
        ]
        mock_client.query_api.return_value = mock_query_api

        # Execute query - should retry and succeed
        result = await run_flux_query(
            full_config,
            "sensor.temperature",
            "-1h",
            "now()"
        )

        # Verify eventual success
        assert len(result) == 1
        assert result[0]["value"] == 24.0
        assert mock_query_api.query.call_count == 2  # Should retry once

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_data_type_handling(self, mock_client_class, full_config):
        """Test handling of different data types in query results."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        # Mock records with different data types
        mock_records = []
        test_values = [25.5, "on", True, False, None, 42, "off", 0, "unknown"]

        for value in test_values:
            mock_record = Mock()
            mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
            mock_record.get_value.return_value = value
            mock_records.append(mock_record)

        mock_table = Mock()
        mock_table.records = mock_records

        mock_query_api = Mock()
        mock_query_api.query.return_value = [mock_table]
        mock_client.query_api.return_value = mock_query_api

        # Execute query
        result = await run_flux_query(
            full_config,
            "sensor.mixed_types",
            "-1h",
            "now()"
        )

        # Verify all data types are handled correctly
        assert len(result) == len(test_values)
        for i, expected_value in enumerate(test_values):
            assert result[i]["value"] == expected_value

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_performance_with_large_datasets(self, mock_client_class, full_config):
        """Test performance with large datasets."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        # Create large dataset
        mock_records = []
        for i in range(1000):  # 1000 records
            mock_record = Mock()
            mock_record.get_time.return_value.isoformat.return_value = f"2025-01-10T12:{i%60:02d}:00Z"
            mock_record.get_value.return_value = 20.0 + (i % 10)  # Values between 20-29
            mock_records.append(mock_record)

        mock_table = Mock()
        mock_table.records = mock_records

        mock_query_api = Mock()
        mock_query_api.query.return_value = [mock_table]
        mock_client.query_api.return_value = mock_query_api

        # Execute query and measure performance
        import time
        start_time = time.time()

        result = await run_flux_query(
            full_config,
            "sensor.high_frequency",
            "-1h",
            "now()"
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify results
        assert len(result) == 1000
        assert execution_time < 5.0  # Should complete within 5 seconds

        # Verify data integrity
        for i, record in enumerate(result):
            expected_value = 20.0 + (i % 10)
            assert record["value"] == expected_value

    @pytest.mark.asyncio
    async def test_cleanup_and_resource_management(self, full_config):
        """Test cleanup and resource management."""
        # This test doesn't mock InfluxDBClient to test actual cleanup

        # We'll use a shorter timeout for testing
        test_config = full_config.copy()
        test_config["timeout"] = 1000  # 1 second timeout

        try:
            # Execute a query to initialize connection manager
            with patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient') as mock_client_class:
                mock_client = Mock()
                mock_client.ping.return_value = True
                mock_client_class.return_value = mock_client

                mock_record = Mock()
                mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
                mock_record.get_value.return_value = 25.0

                mock_table = Mock()
                mock_table.records = [mock_record]

                mock_query_api = Mock()
                mock_query_api.query.return_value = [mock_table]
                mock_client.query_api.return_value = mock_query_api

                result = await run_flux_query(
                    test_config,
                    "sensor.temperature",
                    "-1h",
                    "now()"
                )
                assert len(result) == 1

            # Now test cleanup
            await cleanup_connections()

        except Exception as e:
            # Cleanup should not raise exceptions even if connection fails
            await cleanup_connections()
            pytest.fail(f"Test failed with exception: {e}")

    def test_security_validator_isolation(self):
        """Test that SecurityValidator works independently."""
        # Test entity validation directly
        domain, entity = SecurityValidator.validate_entity_id("sensor.temperature")
        assert domain == "sensor"
        assert entity == "temperature"

        # Test time range validation directly
        start, stop = SecurityValidator.validate_time_range("-1h", "now()")
        assert start == "-1h"
        assert stop == "now()"

        # Test dangerous pattern detection
        dangerous_query = "import 'influxdata/influxdb/v1'"
        assert SecurityValidator.check_for_injection_attempts(dangerous_query)

        # Test safe query
        safe_query = "from(bucket: 'test') |> range(start: -1h)"
        assert not SecurityValidator.check_for_injection_attempts(safe_query)