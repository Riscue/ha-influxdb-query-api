"""
Shared pytest fixtures.
"""
import pytest

import custom_components.influxdb_query_api.influxdb_service as service


@pytest.fixture(autouse=True)
def reset_connection_manager():
    """Reset the global connection manager so mocked clients don't leak between tests."""
    service._connection_manager = None
    yield
    service._connection_manager = None
