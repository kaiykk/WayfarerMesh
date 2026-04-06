"""Custom exception classes for the Travel AI Assistant System.

This module defines a hierarchy of custom exceptions used throughout the application
to provide clear error handling and meaningful error messages.
"""


class TravelAssistantError(Exception):
    """Base exception class for all Travel AI Assistant errors.
    
    All custom exceptions in the system inherit from this base class,
    allowing for catch-all error handling when needed.
    """
    pass


class ConfigurationError(TravelAssistantError):
    """Raised when configuration is invalid or missing.
    
    This exception is raised when:
    - Required configuration fields are missing
    - Configuration values have invalid types
    - Configuration file cannot be loaded
    - Environment variables are missing when required
    """
    pass


class DatabaseError(TravelAssistantError):
    """Raised when database operations fail.
    
    This exception is raised when:
    - Database connection cannot be established
    - Query execution fails
    - Transaction rollback is required
    - Database integrity constraints are violated
    """
    pass


class CacheError(TravelAssistantError):
    """Raised when cache operations fail.
    
    This exception is raised when:
    - Cache initialization fails
    - Cache read/write operations fail
    - Cache invalidation fails
    """
    pass


class TemplateError(TravelAssistantError):
    """Raised when template operations fail.
    
    This exception is raised when:
    - Template file cannot be found
    - Template rendering fails
    - Template syntax is invalid
    """
    pass


class ValidationError(TravelAssistantError):
    """Raised when data validation fails.
    
    This exception is raised when:
    - Input data does not match expected schema
    - Required fields are missing from input
    - Data type validation fails
    """
    pass


class ToolExecutionError(TravelAssistantError):
    """Raised when tool execution fails.
    
    This exception is raised when:
    - Tool function encounters an error
    - Tool parameters are invalid
    - External API calls fail
    - Tool timeout occurs
    """
    pass
