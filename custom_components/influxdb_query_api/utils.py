"""
Security utilities for input validation, sanitization, and escaping.
"""
import re
from typing import Dict, Any, List, Optional, Tuple


class SecurityValidator:
    """
    Security utility class for input validation and sanitization.

    This class provides methods to safely handle user inputs and prevent
    injection attacks in Flux queries.
    """

    # Regex patterns for validation
    ENTITY_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$')
    DOMAIN_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')
    ENTITY_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')
    BUCKET_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

    # Dangerous patterns that should never appear in user input
    DANGEROUS_PATTERNS = [
        r'import\s+\w+',
        r'from\s*\(',
        r'buckets?\s*\(',
        r'drop\s*\(',
        r'delete\s*\(',
        r'org\s*\(',
        r'token\s*\(',
        r'exec\s*\(',
        r'eval\s*\(',
        r'system\s*\(',
        r'shell\s*\(',
        r'__system',
        r'_measurement\s*=\s*["\'][^"\']*["\'].*or',
        r'_field\s*=\s*["\'][^"\']*["\'].*or',
        r'entity_id\s*=\s*["\'][^"\']*["\'].*or',
    ]

    # Characters that should be removed from identifiers
    DANGEROUS_CHARS = ['"', "'", '`', '\\', ';', '|', '>', '<', '&', '$', '(', ')', '[', ']', '{', '}', '\n', '\r', '\t']

    # Characters that should be escaped in values
    ESCAPE_CHARS = {
        '"': '\\"',
        "'": "\\'",
        '\\': '\\\\',
        '\n': '\\n',
        '\r': '\\r',
        '\t': '\\t',
    }

    @classmethod
    def sanitize_identifier(cls, value: str) -> str:
        """
        Sanitize string values used as identifiers in Flux queries.

        Args:
            value: Input string to sanitize

        Returns:
            Sanitized string safe for use as identifier

        Raises:
            ValueError: If the value is invalid or too restrictive after sanitization
        """
        if not isinstance(value, str):
            raise ValueError("Value must be a string")

        if not value.strip():
            raise ValueError("Value cannot be empty")

        # Remove dangerous characters
        sanitized = value.strip()
        for char in cls.DANGEROUS_CHARS:
            sanitized = sanitized.replace(char, '')

        # Additional validation
        if not sanitized:
            raise ValueError("Value became empty after sanitization")

        # Check length limits
        if len(sanitized) > 100:
            raise ValueError("Value too long after sanitization (max 100 characters)")

        return sanitized

    @classmethod
    def escape_value(cls, value: str) -> str:
        """
        Escape string values for safe inclusion in Flux queries.

        Args:
            value: Input string to escape

        Returns:
            Properly escaped string
        """
        if not isinstance(value, str):
            return str(value)

        escaped = value
        for char, replacement in cls.ESCAPE_CHARS.items():
            escaped = escaped.replace(char, replacement)

        return escaped

    @classmethod
    def validate_entity_id(cls, entity_id: str) -> Tuple[str, str]:
        """
        Validate and parse entity_id into domain and entity parts.

        Args:
            entity_id: Home Assistant entity ID (format: domain.entity)

        Returns:
            Tuple of (domain, entity)

        Raises:
            ValueError: If entity_id format is invalid
        """
        if not entity_id or not isinstance(entity_id, str):
            raise ValueError("Invalid entity_id: must be a non-empty string")

        # Basic format check (domain.entity)
        if '.' not in entity_id:
            raise ValueError("Invalid entity_id: must contain '.' separator (format: domain.entity)")

        domain, entity = entity_id.split('.', 1)

        # Validate domain part
        if not domain or not cls.DOMAIN_PATTERN.match(domain):
            raise ValueError(f"Invalid domain in entity_id: '{domain}'. Only alphanumeric characters and underscores allowed")

        # Validate entity part
        if not entity or not cls.ENTITY_PATTERN.match(entity):
            raise ValueError(f"Invalid entity in entity_id: '{entity}'. Only alphanumeric characters and underscores allowed")

        # Additional checks
        if len(domain) > 50:
            raise ValueError("Domain too long (max 50 characters)")

        if len(entity) > 100:
            raise ValueError("Entity too long (max 100 characters)")

        return domain, entity

    @classmethod
    def validate_bucket_name(cls, bucket: str) -> str:
        """
        Validate bucket name.

        Args:
            bucket: Bucket name to validate

        Returns:
            Validated bucket name

        Raises:
            ValueError: If bucket name is invalid
        """
        if not bucket or not isinstance(bucket, str):
            raise ValueError("Bucket name must be a non-empty string")

        if not cls.BUCKET_PATTERN.match(bucket):
            raise ValueError(f"Invalid bucket name: '{bucket}'. Only alphanumeric characters, underscores, and hyphens allowed")

        if len(bucket) > 100:
            raise ValueError("Bucket name too long (max 100 characters)")

        return bucket

    @classmethod
    def validate_time_range(cls, range_start: str, range_stop: str) -> Tuple[str, str]:
        """
        Validate time range parameters for Flux queries.

        Args:
            range_start: Start time expression
            range_stop: Stop time expression

        Returns:
            Tuple of (validated_start, validated_stop)

        Raises:
            ValueError: If time range contains dangerous patterns
        """
        if not range_start or not range_stop:
            raise ValueError("Time range parameters cannot be empty")

        if not isinstance(range_start, str) or not isinstance(range_stop, str):
            raise ValueError("Time range parameters must be strings")

        # Check for dangerous patterns
        for param in [range_start, range_stop]:
            param_lower = param.lower()

            # Check for obvious injection attempts
            dangerous_keywords = [
                'import', 'from(', 'buckets(', 'drop(', 'delete(',
                'org(', 'token(', 'exec(', 'eval(', 'system(',
                'javascript:', 'data:', 'vbscript:', 'file:', 'ftp:', 'http:', 'https:'
            ]

            for keyword in dangerous_keywords:
                if keyword in param_lower:
                    raise ValueError(f"Potentially dangerous pattern detected in time range: {keyword}")

        return range_start, range_stop

    @classmethod
    def validate_query_parameters(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate all query parameters at once.

        Args:
            params: Dictionary of query parameters

        Returns:
            Validated parameters dictionary

        Raises:
            ValueError: If any parameter is invalid
        """
        validated = {}

        # Validate entity_id
        if 'entity_id' in params:
            domain, entity = cls.validate_entity_id(params['entity_id'])
            validated['domain'] = cls.sanitize_identifier(domain)
            validated['entity'] = cls.sanitize_identifier(entity)

        # Validate bucket
        if 'bucket' in params:
            validated['bucket'] = cls.validate_bucket_name(params['bucket'])

        # Validate time range
        if 'range_start' in params and 'range_stop' in params:
            start, stop = cls.validate_time_range(params['range_start'], params['range_stop'])
            validated['range_start'] = start
            validated['range_stop'] = stop

        # Copy safe parameters
        for key, value in params.items():
            if key not in validated and key not in ['entity_id', 'range_start', 'range_stop']:
                if isinstance(value, str):
                    validated[key] = cls.escape_value(value)
                else:
                    validated[key] = value

        return validated

    @classmethod
    def build_safe_filter(cls, domain: str, entity: str, field: str = "value") -> str:
        """
        Build a safe filter expression for Flux queries.

        Args:
            domain: Sanitized domain name
            entity: Sanitized entity name
            field: Field name to filter on

        Returns:
            Safe filter expression
        """
        safe_field = cls.sanitize_identifier(field)

        return f'r["_measurement"] == "{domain}" and r["entity_id"] == "{entity}" and r["_field"] == "{safe_field}"'

    @classmethod
    def check_for_injection_attempts(cls, query: str) -> bool:
        """
        Check if a query contains potential injection attempts.

        Args:
            query: Query string to check

        Returns:
            True if injection attempt detected, False otherwise
        """
        query_lower = query.lower()

        # Check for suspicious keywords
        suspicious_keywords = [
            'import ', 'buckets(', 'drop(', 'delete(',
            'org(', 'token(', 'exec(', 'eval(', 'system(',
            'javascript:', 'data:', 'vbscript:', 'file:', 'ftp:',
            'drop table', 'delete from', 'insert into', 'update set',
            'union select', 'script>', '<script'
        ]

        # Special case: from( is dangerous only when not part of from(bucket:...)
        if 'from(' in query_lower and 'from(bucket:' not in query_lower:
            suspicious_keywords.append('from(')

        for keyword in suspicious_keywords:
            if keyword in query_lower:
                return True

        return False