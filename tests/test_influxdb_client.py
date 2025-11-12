"""
Tests for InfluxDBConnectionManager class.
"""
import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from queue import Empty
import threading

from custom_components.influxdb_query_api.influxdb_client import InfluxDBConnectionManager
from influxdb_client.client.exceptions import InfluxDBError


class TestInfluxDBConnectionManager:
    """Test cases for InfluxDBConnectionManager."""

    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            "host": "localhost",
            "port": "8086",
            "token": "test-token",
            "organization": "test-org",
            "bucket": "test-bucket",
            "timeout": 5000,
            "ssl": False,
            "verify_ssl": True
        }

    @pytest.fixture
    def manager(self, config):
        """Create connection manager instance."""
        return InfluxDBConnectionManager(config, pool_size=3, max_retries=2)

    def test_manager_initialization(self, config):
        """Test manager initialization."""
        manager = InfluxDBConnectionManager(config, pool_size=5, max_retries=3)

        assert manager.pool_size == 5
        assert manager.max_retries == 3
        assert manager.host == "localhost"
        assert manager.port == "8086"
        assert manager.token == "test-token"
        assert manager.organization == "test-org"
        assert manager.bucket == "test-bucket"
        assert manager.timeout == 5000
        assert manager.enable_ssl is False
        assert manager.verify_ssl is True
        assert not manager._initialized

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    def test_create_client(self, mock_client_class, manager):
        """Test client creation."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        client = manager._create_client()

        mock_client_class.assert_called_once_with(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            timeout=5000,
            verify_ssl=True
        )
        assert client == mock_client

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    def test_initialize_pool_success(self, mock_client_class, manager):
        """Test successful pool initialization."""
        mock_clients = []
        for i in range(3):
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_clients.append(mock_client)
            mock_client_class.side_effect = mock_clients

        manager._initialize_pool()

        assert manager._initialized
        assert manager._connection_pool.qsize() == 3
        assert mock_client_class.call_count == 3

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    def test_initialize_pool_with_failures(self, mock_client_class, manager):
        """Test pool initialization with some failures."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.side_effect = [
            Exception("Connection failed"),  # First fails
            mock_client,                     # Second succeeds
            Exception("Connection failed"),  # Third fails
        ]

        manager._initialize_pool()

        assert manager._initialized
        # Should have 1 successful connection
        assert manager._connection_pool.qsize() == 1

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_get_client_from_pool(self, mock_client_class, manager):
        """Test getting client from pool."""
        # Initialize pool
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client
        manager._initialize_pool()

        # Get client
        async with manager.get_client() as client:
            assert client == mock_client
            # Client should be in active connections
            assert client in manager._active_connections

        # After context, client should be returned to pool
        assert client not in manager._active_connections
        assert manager._connection_pool.qsize() == 3  # All 3 original connections should be back

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_get_client_pool_exhausted(self, mock_client_class, manager):
        """Test getting client when pool is exhausted."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        # Don't initialize pool to force creation of new client
        async with manager.get_client() as client:
            assert client == mock_client

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_get_client_with_ping_failure(self, mock_client_class, manager):
        """Test client creation when ping fails."""
        # First client fails ping, second succeeds
        old_client = Mock()
        old_client.ping.side_effect = Exception("Ping failed")

        new_client = Mock()
        new_client.ping.return_value = True

        mock_client_class.side_effect = [old_client, new_client]

        # Initialize pool with failing client
        manager._initialize_pool()
        manager._connection_pool.get_nowait()  # Get the failing client

        # Get client should create new one
        async with manager.get_client() as client:
            assert client == new_client

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_execute_query_success(self, mock_client_class, manager):
        """Test successful query execution."""
        # Mock client and query result
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        mock_record = Mock()
        mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
        mock_record.get_value.return_value = 25.5

        mock_table = Mock()
        mock_table.records = [mock_record]

        mock_query_api = Mock()
        mock_query_api.query.return_value = [mock_table]
        mock_client.query_api.return_value = mock_query_api

        result = await manager.execute_query("test query")

        assert len(result) == 1
        assert result[0]["time"] == "2025-01-10T12:00:00Z"
        assert result[0]["value"] == 25.5

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_execute_query_with_retry(self, mock_client_class, manager):
        """Test query execution with retry on connection errors."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        # First attempt fails with connection error, second succeeds
        mock_record = Mock()
        mock_record.get_time.return_value.isoformat.return_value = "2025-01-10T12:00:00Z"
        mock_record.get_value.return_value = 25.5

        mock_table = Mock()
        mock_table.records = [mock_record]

        mock_query_api = Mock()
        mock_query_api.query.side_effect = [
            InfluxDBError("Connection timeout"),
            [mock_table]
        ]
        mock_client.query_api.return_value = mock_query_api

        result = await manager.execute_query("test query")

        assert len(result) == 1
        assert mock_query_api.query.call_count == 2  # Should retry once

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_execute_query_max_retries_exceeded(self, mock_client_class, manager):
        """Test query execution when max retries exceeded."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        mock_query_api = Mock()
        mock_query_api.query.side_effect = InfluxDBError("Persistent connection error")
        mock_client.query_api.return_value = mock_query_api

        with pytest.raises(Exception, match="InfluxDB query failed after"):
            await manager.execute_query("test query")

        # Should attempt initial + max_retries
        assert mock_query_api.query.call_count == 3  # 1 initial + 2 retries

    def test_should_retry_connection_errors(self, manager):
        """Test retry logic for connection errors."""
        retryable_errors = [
            InfluxDBError("connection timeout"),
            InfluxDBError("network unreachable"),
            InfluxDBError("temporary failure"),
            InfluxDBError("502 Bad Gateway"),
            InfluxDBError("503 Service Unavailable"),
        ]

        for error in retryable_errors:
            assert manager._should_retry(error), f"Should retry for: {error}"

    def test_should_not_retry_other_errors(self, manager):
        """Test retry logic for non-retryable errors."""
        non_retryable_errors = [
            InfluxDBError("invalid query syntax"),
            InfluxDBError("authentication failed"),
            InfluxDBError("bucket not found"),
        ]

        for error in non_retryable_errors:
            assert not manager._should_retry(error), f"Should not retry for: {error}"

    def test_get_pool_status(self, manager):
        """Test pool status reporting."""
        status = manager.get_pool_status()

        assert status["pool_size"] == 3
        assert status["available_connections"] == 0
        assert status["active_connections"] == 0
        assert status["initialized"] is False
        assert status["host"] == "localhost:8086"

    @patch('custom_components.influxdb_query_api.influxdb_client.InfluxDBClient')
    @pytest.mark.asyncio
    async def test_cleanup(self, mock_client_class, manager):
        """Test connection cleanup."""
        mock_clients = []
        for i in range(3):
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_clients.append(mock_client)
            mock_client_class.return_value = mock_client

        # Initialize pool
        manager._initialize_pool()

        # Add some active connections
        manager._active_connections.add(mock_clients[0])

        await manager.cleanup()

        # All clients should be closed
        for mock_client in mock_clients:
            mock_client.close.assert_called()

        assert manager._connection_pool.empty()
        assert len(manager._active_connections) == 0
        assert not manager._initialized

    def test_thread_safety(self, manager):
        """Test thread safety of connection manager."""
        results = []
        errors = []

        def worker():
            try:
                # Simulate concurrent access
                with manager._lock:
                    manager._active_connections.add("test_connection")
                results.append("success")
                with manager._lock:
                    manager._active_connections.discard("test_connection")
            except Exception as e:
                errors.append(str(e))

        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=worker)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check results
        assert len(results) == 10
        assert len(errors) == 0
        assert len(manager._active_connections) == 0