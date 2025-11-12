"""
InfluxDB query service with security, validation, and connection management.
"""
import asyncio
import logging
from typing import Dict, Any, List

from .influxdb_client import InfluxDBConnectionManager
from .utils import SecurityValidator

_LOGGER = logging.getLogger(__name__)

# Global connection manager instance
_connection_manager: InfluxDBConnectionManager = None


def get_connection_manager(config: Dict[str, Any]) -> InfluxDBConnectionManager:
    """Get or create a connection manager instance."""
    global _connection_manager

    if _connection_manager is None:
        pool_size = config.get("pool_size", 5)
        max_retries = config.get("max_retries", 3)
        _connection_manager = InfluxDBConnectionManager(config, pool_size, max_retries)
        _LOGGER.info(f"Created InfluxDB connection manager with pool_size={pool_size}")

    return _connection_manager


def _build_safe_query(bucket: str, domain: str, entity: str, range_start: str, range_stop: str) -> str:
    """
    Build a secure Flux query using validated and sanitized inputs.

    Args:
        bucket: Validated bucket name
        domain: Sanitized domain name
        entity: Sanitized entity name
        range_start: Validated start time expression
        range_stop: Validated stop time expression

    Returns:
        Secure Flux query string
    """
    # Use SecurityValidator to build safe filter
    safe_filter = SecurityValidator.build_safe_filter(domain, entity)

    query = f'''from(bucket: "{bucket}")
    |> range(start: {range_start}, stop: {range_stop})
    |> filter(fn: (r) => {safe_filter})'''

    # Final safety check
    if SecurityValidator.check_for_injection_attempts(query):
        raise ValueError("Potentially dangerous query detected after construction")

    return query


async def run_flux_query(conf: Dict[str, Any], entity_id: str, range_start: str, range_stop: str) -> List[Dict[str, Any]]:
    """
    Execute a secure Flux query against InfluxDB.

    Args:
        conf: InfluxDB configuration dictionary
        entity_id: Home Assistant entity ID (format: domain.entity)
        range_start: Start time for query (Flux time expression)
        range_stop: End time for query (Flux time expression)

    Returns:
        List of data points with time and value

    Raises:
        ValueError: For invalid input parameters
        Exception: For InfluxDB connection/query errors
    """
    try:
        _LOGGER.debug(f"Starting query execution for entity: {entity_id}")

        # Validate all inputs using SecurityValidator
        params = {
            'entity_id': entity_id,
            'bucket': conf.get("bucket", ""),
            'range_start': range_start,
            'range_stop': range_stop
        }

        validated_params = SecurityValidator.validate_query_parameters(params)

        # Extract validated parameters
        domain = validated_params['domain']
        entity = validated_params['entity']
        bucket = validated_params['bucket']
        validated_start = validated_params['range_start']
        validated_stop = validated_params['range_stop']

        # Get connection manager
        manager = get_connection_manager(conf)

        # Build secure query
        query = _build_safe_query(bucket, domain, entity, validated_start, validated_stop)
        _LOGGER.debug(f"Generated secure query for {entity_id}")

        # Execute query with connection pooling and retry logic
        result = await manager.execute_query(query)

        _LOGGER.info(f"Query successful for {entity_id}: {len(result)} records")
        return result

    except ValueError as e:
        _LOGGER.warning(f"Input validation failed for {entity_id}: {e}")
        raise ValueError(f"Input validation failed: {str(e)}")
    except Exception as e:
        _LOGGER.error(f"Query execution failed for {entity_id}: {e}")
        raise Exception(f"Query execution failed: {str(e)}")


async def cleanup_connections():
    """Cleanup connection manager and all connections."""
    global _connection_manager

    if _connection_manager:
        await _connection_manager.cleanup()
        _connection_manager = None
        _LOGGER.info("InfluxDB connection manager cleaned up")


def get_connection_status() -> Dict[str, Any]:
    """Get current connection pool status for monitoring."""
    global _connection_manager

    if _connection_manager:
        return _connection_manager.get_pool_status()
    return {"status": "Not initialized"}
