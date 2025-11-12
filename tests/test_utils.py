"""
Tests for SecurityValidator utility class.
"""
import pytest
from custom_components.influxdb_query_api.utils import SecurityValidator


class TestSecurityValidator:
    """Test cases for SecurityValidator class."""

    def test_sanitize_identifier_valid_inputs(self):
        """Test sanitization of valid identifiers."""
        # Normal cases
        assert SecurityValidator.sanitize_identifier("sensor") == "sensor"
        assert SecurityValidator.sanitize_identifier("temp_sensor_01") == "temp_sensor_01"
        assert SecurityValidator.sanitize_identifier("  sensor  ") == "sensor"

    def test_sanitize_identifier_dangerous_chars(self):
        """Test removal of dangerous characters."""
        assert SecurityValidator.sanitize_identifier('sensor"name') == "sensorname"
        assert SecurityValidator.sanitize_identifier("sensor'sensor") == "sensorsensor"
        assert SecurityValidator.sanitize_identifier("sensor`command") == "sensorcommand"
        assert SecurityValidator.sanitize_identifier("sensor\\path") == "sensorpath"
        assert SecurityValidator.sanitize_identifier("sensor;drop") == "sensordrop"
        assert SecurityValidator.sanitize_identifier("sensor|pipe") == "sensorpipe"
        assert SecurityValidator.sanitize_identifier("sensor>redirect") == "sensorredirect"

    def test_sanitize_identifier_invalid_inputs(self):
        """Test sanitization rejects invalid inputs."""
        with pytest.raises(ValueError, match="Value must be a string"):
            SecurityValidator.sanitize_identifier(123)

        with pytest.raises(ValueError, match="Value cannot be empty"):
            SecurityValidator.sanitize_identifier("")

        with pytest.raises(ValueError, match="Value cannot be empty"):
            SecurityValidator.sanitize_identifier("   ")

        # After removing dangerous chars, becomes empty
        with pytest.raises(ValueError, match="Value became empty after sanitization"):
            SecurityValidator.sanitize_identifier(";|<>'\"")

        # Too long
        long_string = "a" * 101
        with pytest.raises(ValueError, match="Value too long"):
            SecurityValidator.sanitize_identifier(long_string)

    def test_validate_entity_id_valid_cases(self):
        """Test validation of valid entity IDs."""
        # Normal cases
        domain, entity = SecurityValidator.validate_entity_id("sensor.temperature")
        assert domain == "sensor"
        assert entity == "temperature"

        domain, entity = SecurityValidator.validate_entity_id("binary_sensor.front_door")
        assert domain == "binary_sensor"
        assert entity == "front_door"

        domain, entity = SecurityValidator.validate_entity_id("light.living_room_main_01")
        assert domain == "light"
        assert entity == "living_room_main_01"

    def test_validate_entity_id_invalid_cases(self):
        """Test validation rejects invalid entity IDs."""
        # Missing dot
        with pytest.raises(ValueError, match="must contain '.' separator"):
            SecurityValidator.validate_entity_id("sensortemperature")

        # Empty parts
        with pytest.raises(ValueError, match="Invalid domain"):
            SecurityValidator.validate_entity_id(".temperature")

        with pytest.raises(ValueError, match="Invalid entity"):
            SecurityValidator.validate_entity_id("sensor.")

        # Invalid characters
        with pytest.raises(ValueError, match="Invalid domain"):
            SecurityValidator.validate_entity_id("sensor-temp.temperature")

        with pytest.raises(ValueError, match="Invalid entity"):
            SecurityValidator.validate_entity_id("sensor.temp-sensor")

        # Non-string input
        with pytest.raises(ValueError, match="must be a non-empty string"):
            SecurityValidator.validate_entity_id(123)

        # Empty string
        with pytest.raises(ValueError, match="must be a non-empty string"):
            SecurityValidator.validate_entity_id("")

        # Too long
        long_domain = "a" * 51
        with pytest.raises(ValueError, match="Domain too long"):
            SecurityValidator.validate_entity_id(f"{long_domain}.entity")

        long_entity = "a" * 101
        with pytest.raises(ValueError, match="Entity too long"):
            SecurityValidator.validate_entity_id(f"sensor.{long_entity}")

    def test_validate_bucket_name_valid_cases(self):
        """Test validation of valid bucket names."""
        assert SecurityValidator.validate_bucket_name("homeassistant") == "homeassistant"
        assert SecurityValidator.validate_bucket_name("bucket_01") == "bucket_01"
        assert SecurityValidator.validate_bucket_name("my-bucket") == "my-bucket"
        assert SecurityValidator.validate_bucket_name("Bucket_Name_123") == "Bucket_Name_123"

    def test_validate_bucket_name_invalid_cases(self):
        """Test validation rejects invalid bucket names."""
        # Empty
        with pytest.raises(ValueError, match="must be a non-empty string"):
            SecurityValidator.validate_bucket_name("")

        # Non-string
        with pytest.raises(ValueError, match="must be a non-empty string"):
            SecurityValidator.validate_bucket_name(123)

        # Invalid characters
        with pytest.raises(ValueError, match="Invalid bucket name"):
            SecurityValidator.validate_bucket_name("bucket.name")

        with pytest.raises(ValueError, match="Invalid bucket name"):
            SecurityValidator.validate_bucket_name("bucket name")

        # Too long
        with pytest.raises(ValueError, match="Bucket name too long"):
            SecurityValidator.validate_bucket_name("a" * 101)

    def test_validate_time_range_valid_cases(self):
        """Test validation of valid time ranges."""
        # Valid Flux time expressions
        start, stop = SecurityValidator.validate_time_range("-1h", "now()")
        assert start == "-1h"
        assert stop == "now()"

        start, stop = SecurityValidator.validate_time_range("2025-01-10T00:00:00Z", "2025-01-10T23:59:59Z")
        assert start == "2025-01-10T00:00:00Z"
        assert stop == "2025-01-10T23:59:59Z"

    def test_validate_time_range_invalid_cases(self):
        """Test validation rejects dangerous time ranges."""
        # Empty values
        with pytest.raises(ValueError, match="cannot be empty"):
            SecurityValidator.validate_time_range("", "now()")

        with pytest.raises(ValueError, match="cannot be empty"):
            SecurityValidator.validate_time_range("-1h", "")

        # Non-string values
        with pytest.raises(ValueError, match="must be strings"):
            SecurityValidator.validate_time_range(123, "now()")

        # Dangerous patterns
        dangerous_inputs = [
            "import('influxdata/influxdb/v1')",
            "from(bucket: 'test')",
            "buckets()",
            "drop()",
            "delete()",
            "org()",
            "token()",
            "exec('rm -rf /')",
            "eval('malicious code')",
            "system('hack')"
        ]

        for dangerous_input in dangerous_inputs:
            with pytest.raises(ValueError, match="Potentially dangerous pattern"):
                SecurityValidator.validate_time_range(dangerous_input, "now()")

    def test_validate_query_parameters_valid_cases(self):
        """Test validation of complete parameter sets."""
        params = {
            'entity_id': 'sensor.temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()'
        }

        validated = SecurityValidator.validate_query_parameters(params)

        assert validated['domain'] == 'sensor'
        assert validated['entity'] == 'temperature'
        assert validated['bucket'] == 'homeassistant'
        assert validated['range_start'] == '-1h'
        assert validated['range_stop'] == 'now()'

    def test_validate_query_parameters_with_extra_params(self):
        """Test validation preserves safe extra parameters."""
        params = {
            'entity_id': 'sensor.temperature',
            'bucket': 'homeassistant',
            'range_start': '-1h',
            'range_stop': 'now()',
            'limit': 100,
            'aggregation': 'mean'
        }

        validated = SecurityValidator.validate_query_parameters(params)

        assert validated['limit'] == 100
        assert validated['aggregation'] == 'mean'

    def test_build_safe_filter(self):
        """Test building of safe filter expressions."""
        filter_expr = SecurityValidator.build_safe_filter("sensor", "temperature")

        expected = 'r["_measurement"] == "sensor" and r["entity_id"] == "temperature" and r["_field"] == "value"'
        assert filter_expr == expected

        # Custom field
        filter_expr = SecurityValidator.build_safe_filter("sensor", "temperature", "state")
        expected = 'r["_measurement"] == "sensor" and r["entity_id"] == "temperature" and r["_field"] == "state"'
        assert filter_expr == expected

    def test_check_for_injection_attempts_safe_cases(self):
        """Test detection of injection attempts on safe queries."""
        safe_queries = [
            'from(bucket: "test") |> range(start: -1h)',
            'r["_measurement"] == "sensor" and r["entity_id"] == "test"',
            'from(bucket: "homeassistant") |> filter(fn: (r) => r._value > 0)'
        ]

        for query in safe_queries:
            assert not SecurityValidator.check_for_injection_attempts(query)

    def test_check_for_injection_attempts_dangerous_cases(self):
        """Test detection of injection attempts on dangerous queries."""
        dangerous_queries = [
            'import "influxdata/influxdb/v1"',
            'from(bucket: "test") |> drop()',
            'exec("rm -rf /")',
            'eval("malicious")',
            'drop table users',
            'delete from measurements',
            'union select * from passwords',
            '<script>alert("xss")</script>',
            'javascript:alert("xss")',
            'data:text/html,<script>alert("xss")</script>'
        ]

        for query in dangerous_queries:
            assert SecurityValidator.check_for_injection_attempts(query)