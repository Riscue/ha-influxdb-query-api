"""
InfluxDB connection manager with connection pooling and security features.
"""
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from queue import Queue, Empty
from typing import Dict, Any, List

from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError

_LOGGER = logging.getLogger(__name__)


class InfluxDBConnectionManager:
    """
    Thread-safe InfluxDB connection manager with connection pooling.

    Features:
    - Connection pooling
    - Connection timeout management
    - Automatic connection cleanup
    - Error handling and retry logic
    - Thread-safe operations
    """

    def __init__(self, config: Dict[str, Any], pool_size: int = 5, max_retries: int = 3):
        """
        Initialize InfluxDB connection manager.

        Args:
            config: InfluxDB configuration dictionary
            pool_size: Maximum number of connections in pool
            max_retries: Maximum retry attempts for failed operations
        """
        self.config = config
        self.pool_size = pool_size
        self.max_retries = max_retries
        self._connection_pool = Queue(maxsize=pool_size)
        self._active_connections = set()
        self._lock = threading.Lock()
        self._initialized = False

        # Extract configuration
        self.host = config.get("host", "localhost")
        self.port = config.get("port", "8086")
        self.token = config.get("token", "")
        self.organization = config.get("organization", "")
        self.bucket = config.get("bucket", "homeassistant")

        # Connection settings
        self.timeout = config.get("timeout", 10000)  # milliseconds
        self.enable_ssl = config.get("ssl", False)
        self.verify_ssl = config.get("verify_ssl", True)

    def _create_client(self) -> InfluxDBClient:
        """Create a new InfluxDB client with current configuration."""
        protocol = "https" if self.enable_ssl else "http"
        url = f"{protocol}://{self.host}:{self.port}"

        client = InfluxDBClient(
            url=url,
            token=self.token,
            org=self.organization,
            timeout=self.timeout,
            verify_ssl=self.verify_ssl
        )

        _LOGGER.debug(f"Created new InfluxDB client: {self.host}:{self.port}")
        return client

    def _initialize_pool(self):
        """Initialize the connection pool with client instances."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            _LOGGER.info(f"Initializing InfluxDB connection pool with {self.pool_size} connections")

            for i in range(self.pool_size):
                try:
                    client = self._create_client()
                    # Test connection
                    client.ping()
                    self._connection_pool.put(client)
                    _LOGGER.debug(f"Added connection {i + 1}/{self.pool_size} to pool")
                except Exception as e:
                    _LOGGER.error(f"Failed to create connection {i + 1}: {e}")
                    # Continue trying to create other connections

            self._initialized = True
            _LOGGER.info(f"Connection pool initialized with {self._connection_pool.qsize()} active connections")

    @asynccontextmanager
    async def get_client(self):
        """
        Get a client from the connection pool (async context manager).

        Usage:
            async with manager.get_client() as client:
                result = client.query_api().query(query)
        """
        self._initialize_pool()

        client = None
        try:
            # Try to get a client from pool (with timeout)
            try:
                client = self._connection_pool.get(timeout=5)
            except Empty:
                _LOGGER.warning("Connection pool exhausted, creating new client")
                client = self._create_client()

            # Test if connection is still valid
            try:
                client.ping()
            except Exception as e:
                _LOGGER.warning(f"Connection ping failed, creating new client: {e}")
                client = self._create_client()

            with self._lock:
                self._active_connections.add(client)

            yield client

        except Exception as e:
            _LOGGER.error(f"Error in get_client context: {e}")
            # Don't re-raise if connection is being cleaned up
            if "connection" in str(e).lower():
                return
            raise
        finally:
            if client:
                with self._lock:
                    self._active_connections.discard(client)

                # Try to return client to pool
                try:
                    if not self._connection_pool.full():
                        self._connection_pool.put(client, timeout=1)
                    else:
                        # Pool is full, close this connection
                        client.close()
                        _LOGGER.debug("Connection closed (pool full)")
                except Exception as e:
                    _LOGGER.warning(f"Failed to return client to pool: {e}")
                    try:
                        client.close()
                    except:
                        pass

    async def execute_query(self, query: str, retry_count: int = 0) -> List[Dict[str, Any]]:
        """
        Execute a Flux query with retry logic.

        Args:
            query: Flux query string
            retry_count: Current retry attempt (internal use)

        Returns:
            List of data points

        Raises:
            Exception: If query fails after all retries
        """
        last_error = None

        async with self.get_client() as client:
            try:
                _LOGGER.debug(f"Executing query (attempt {retry_count + 1}): {query[:100]}...")

                tables = client.query_api().query(query)
                result = []

                for table in tables:
                    for record in table.records:
                        result.append({
                            "time": record.get_time().isoformat(),
                            "value": record.get_value()
                        })

                _LOGGER.debug(f"Query successful: {len(result)} records returned")
                return result

            except InfluxDBError as e:
                last_error = e
                _LOGGER.warning(f"InfluxDB query error (attempt {retry_count + 1}): {e}")

                # Retry on connection-related errors
                if retry_count < self.max_retries and self._should_retry(e):
                    _LOGGER.info(f"Retrying query ({retry_count + 1}/{self.max_retries})")
                    await asyncio.sleep(0.5 * (retry_count + 1))  # Exponential backoff
                    return await self.execute_query(query, retry_count + 1)

                raise Exception(f"InfluxDB query failed after {retry_count + 1} attempts: {e}")

            except Exception as e:
                last_error = e
                _LOGGER.error(f"Unexpected error during query: {e}")
                raise Exception(f"Query execution failed: {e}")

    def _should_retry(self, error: InfluxDBError) -> bool:
        """Determine if a query should be retried based on error type."""
        error_str = str(error).lower()

        # Retry on connection-related errors
        retryable_errors = [
            "connection",
            "timeout",
            "network",
            "unavailable",
            "temporary",
            "502",
            "503",
            "504"
        ]

        return any(err in error_str for err in retryable_errors)

    def get_pool_status(self) -> Dict[str, Any]:
        """Get current connection pool status."""
        with self._lock:
            return {
                "pool_size": self.pool_size,
                "available_connections": self._connection_pool.qsize(),
                "active_connections": len(self._active_connections),
                "initialized": self._initialized,
                "host": f"{self.host}:{self.port}"
            }

    async def cleanup(self):
        """Cleanup all connections and shutdown the pool."""
        _LOGGER.info("Cleaning up InfluxDB connection pool")

        with self._lock:
            # Close all connections in pool
            while not self._connection_pool.empty():
                try:
                    client = self._connection_pool.get_nowait()
                    client.close()
                except Empty:
                    break
                except Exception as e:
                    _LOGGER.warning(f"Error closing pooled connection: {e}")

            # Close active connections
            for client in list(self._active_connections):
                try:
                    client.close()
                except Exception as e:
                    _LOGGER.warning(f"Error closing active connection: {e}")

            self._active_connections.clear()
            self._initialized = False

        _LOGGER.info("Connection pool cleanup completed")

    def __del__(self):
        """Destructor to ensure cleanup."""
        if hasattr(self, '_initialized') and self._initialized:
            # Note: This is synchronous, so we can't call async cleanup here
            # Users should call cleanup() explicitly before shutdown
            _LOGGER.warning("InfluxDBConnectionManager destroyed without explicit cleanup()")
