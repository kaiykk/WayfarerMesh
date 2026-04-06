"""Configuration data models for the trip assistant application.

This module defines the configuration schema using dataclasses with type annotations
and default values. The configuration is organized into logical sections:
- DatabaseConfig: Database connection and retry settings
- LLMConfig: Language model provider and parameters
- CacheConfig: Caching behavior and limits
- LoggingConfig: Logging output and formatting
- Config: Top-level configuration container
"""

from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database configuration settings.
    
    Attributes:
        path: Path to the SQLite database file
        pool_size: Maximum number of database connections in the pool
        timeout: Connection timeout in seconds
        retry_attempts: Number of retry attempts for failed operations
        retry_backoff_factor: Exponential backoff multiplier for retries
    """
    path: str
    pool_size: int = 5
    timeout: float = 30.0
    retry_attempts: int = 3
    retry_backoff_factor: float = 2.0


@dataclass
class LLMConfig:
    """Language model configuration settings.
    
    Attributes:
        provider: LLM provider name (e.g., "openai", "anthropic")
        model_name: Specific model identifier
        api_key: API authentication key
        temperature: Sampling temperature for response generation (0.0-1.0)
        max_tokens: Maximum number of tokens in generated responses
    """
    provider: str
    model_name: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 1000


@dataclass
class CacheConfig:
    """Cache configuration settings.
    
    Attributes:
        enabled: Whether caching is enabled
        ttl_seconds: Time-to-live for cached entries in seconds
        max_size: Maximum number of entries in the cache
    """
    enabled: bool = True
    ttl_seconds: int = 300
    max_size: int = 1000


@dataclass
class LoggingConfig:
    """Logging configuration settings.
    
    Attributes:
        level: Logging level (e.g., "DEBUG", "INFO", "WARNING", "ERROR")
        format: Log output format (e.g., "json", "text")
        file_path: Path to the log file
        rotation: Log file rotation size threshold
        retention: Number of rotated log files to retain
        console_output: Whether to output logs to console
    """
    level: str = "INFO"
    format: str = "json"
    file_path: str = "logs/app.log"
    rotation: str = "10 MB"
    retention: int = 20
    console_output: bool = True


@dataclass
class Config:
    """Top-level application configuration.
    
    Attributes:
        database: Database configuration
        llm: Language model configuration
        cache: Cache configuration
        logging: Logging configuration
        prompts_dir: Directory containing prompt templates
        default_language: Default language code for prompts (e.g., "en", "zh")
    """
    database: DatabaseConfig
    llm: LLMConfig
    cache: CacheConfig
    logging: LoggingConfig
    prompts_dir: str = "prompts"
    default_language: str = "en"
