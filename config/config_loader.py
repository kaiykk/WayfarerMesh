"""Configuration loader with YAML file support and environment variable overrides.

This module provides the ConfigLoader class for loading and validating application
configuration from YAML files with support for environment variable substitution
and overrides.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .config_schema import (
    Config,
    DatabaseConfig,
    LLMConfig,
    CacheConfig,
    LoggingConfig,
)
from ..utils.error_handling import ConfigurationError


class ConfigLoader:
    """Loads and validates configuration from YAML files and environment variables.
    
    The loader supports:
    - Loading configuration from YAML files
    - Environment variable substitution using ${VAR_NAME} syntax
    - Environment variable overrides (env vars take precedence over file values)
    - Configuration validation against the schema
    - Dot-notation key access for nested configuration values
    
    Example:
        loader = ConfigLoader("config/config.yaml")
        config = loader.load()
        db_path = loader.get("database.path")
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize configuration loader with path to config file.
        
        Args:
            config_path: Path to the YAML configuration file (relative or absolute)
        """
        self.config_path = Path(config_path)
        self._config: Optional[Config] = None
        self._raw_data: Optional[Dict[str, Any]] = None
    
    def load(self) -> Config:
        """Load configuration with environment variable overrides.
        
        This method:
        1. Reads the YAML configuration file
        2. Substitutes ${ENV_VAR} placeholders with environment variable values
        3. Applies environment variable overrides
        4. Validates the configuration
        5. Returns a Config object
        
        Returns:
            Config: Validated configuration object
            
        Raises:
            ConfigurationError: If config file is missing, invalid, or validation fails
        """
        # Load YAML file
        if not self.config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {self.config_path}"
            )
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Failed to parse YAML configuration: {e}"
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to read configuration file: {e}"
            )
        
        if not isinstance(raw_data, dict):
            raise ConfigurationError(
                "Configuration file must contain a YAML dictionary"
            )
        
        # Substitute environment variables in the raw data
        self._raw_data = self._substitute_env_vars(raw_data)
        
        # Apply environment variable overrides
        self._apply_env_overrides()
        
        # Build Config object from raw data
        try:
            config = self._build_config(self._raw_data)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to build configuration object: {e}"
            )
        
        # Validate configuration
        self.validate(config)
        
        self._config = config
        return config
    
    def validate(self, config: Config) -> None:
        """Validate configuration against schema, raise ConfigError if invalid.
        
        Checks:
        - Required fields are present
        - Field types are correct
        - Values are within acceptable ranges
        
        Args:
            config: Configuration object to validate
            
        Raises:
            ConfigurationError: If validation fails
        """
        # Validate DatabaseConfig
        if not config.database.path:
            raise ConfigurationError("database.path is required")
        if config.database.pool_size <= 0:
            raise ConfigurationError("database.pool_size must be positive")
        if config.database.timeout <= 0:
            raise ConfigurationError("database.timeout must be positive")
        if config.database.retry_attempts < 0:
            raise ConfigurationError("database.retry_attempts must be non-negative")
        if config.database.retry_backoff_factor <= 0:
            raise ConfigurationError("database.retry_backoff_factor must be positive")
        
        # Validate LLMConfig
        if not config.llm.provider:
            raise ConfigurationError("llm.provider is required")
        if not config.llm.model_name:
            raise ConfigurationError("llm.model_name is required")
        if not config.llm.api_key:
            raise ConfigurationError("llm.api_key is required")
        if not (0.0 <= config.llm.temperature <= 2.0):
            raise ConfigurationError("llm.temperature must be between 0.0 and 2.0")
        if config.llm.max_tokens <= 0:
            raise ConfigurationError("llm.max_tokens must be positive")
        
        # Validate CacheConfig
        if config.cache.ttl_seconds <= 0:
            raise ConfigurationError("cache.ttl_seconds must be positive")
        if config.cache.max_size <= 0:
            raise ConfigurationError("cache.max_size must be positive")
        
        # Validate LoggingConfig
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if config.logging.level.upper() not in valid_levels:
            raise ConfigurationError(
                f"logging.level must be one of {valid_levels}"
            )
        valid_formats = ["json", "text"]
        if config.logging.format not in valid_formats:
            raise ConfigurationError(
                f"logging.format must be one of {valid_formats}"
            )
        if not config.logging.file_path:
            raise ConfigurationError("logging.file_path is required")
        if config.logging.retention <= 0:
            raise ConfigurationError("logging.retention must be positive")
        
        # Validate top-level Config
        if not config.prompts_dir:
            raise ConfigurationError("prompts_dir is required")
        if not config.default_language:
            raise ConfigurationError("default_language is required")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key.
        
        Supports nested key access using dot notation, e.g.:
        - 'database.path' returns config.database.path
        - 'llm.temperature' returns config.llm.temperature
        
        Args:
            key: Dot-notation key path (e.g., 'database.path')
            default: Default value to return if key is not found
            
        Returns:
            Configuration value at the specified key, or default if not found
            
        Raises:
            ConfigurationError: If configuration has not been loaded yet
        """
        if self._raw_data is None:
            raise ConfigurationError(
                "Configuration not loaded. Call load() first."
            )
        
        # Navigate through nested dictionary using dot notation
        keys = key.split('.')
        value = self._raw_data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def _substitute_env_vars(self, data: Any) -> Any:
        """Recursively substitute ${ENV_VAR} placeholders with environment variable values.
        
        Args:
            data: Data structure to process (dict, list, str, or other)
            
        Returns:
            Data structure with environment variables substituted
        """
        if isinstance(data, dict):
            return {k: self._substitute_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._substitute_env_vars(item) for item in data]
        elif isinstance(data, str):
            # Match ${VAR_NAME} pattern
            pattern = r'\$\{([^}]+)\}'
            
            def replace_env_var(match):
                var_name = match.group(1)
                value = os.getenv(var_name)
                if value is None:
                    raise ConfigurationError(
                        f"Environment variable '{var_name}' not found"
                    )
                return value
            
            return re.sub(pattern, replace_env_var, data)
        else:
            return data
    
    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to configuration.
        
        Environment variables can override configuration values using the format:
        - TRIP_ASSISTANT_DATABASE__PATH overrides database.path
        - TRIP_ASSISTANT_LLM__TEMPERATURE overrides llm.temperature
        
        The prefix 'TRIP_ASSISTANT_' is used to namespace the variables.
        Double underscores '__' are converted to dots for nested keys.
        Single underscores '_' within a key are preserved (e.g., pool_size).
        """
        prefix = "TRIP_ASSISTANT_"
        
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            
            # Remove prefix and convert to lowercase dot notation
            # TRIP_ASSISTANT_DATABASE__PATH -> database.path
            # TRIP_ASSISTANT_DATABASE__POOL_SIZE -> database.pool_size
            config_key = env_key[len(prefix):].lower()
            
            # Replace double underscores with dots for nesting
            config_key = config_key.replace('__', '.')
            
            # Navigate to the nested location and set the value
            keys = config_key.split('.')
            current = self._raw_data
            
            for i, key in enumerate(keys[:-1]):
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Convert string values to appropriate types
            final_key = keys[-1]
            current[final_key] = self._convert_type(env_value)

    
    def _convert_type(self, value: str) -> Any:
        """Convert string value to appropriate Python type.
        
        Args:
            value: String value to convert
            
        Returns:
            Converted value (bool, int, float, or str)
        """
        # Boolean conversion
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        
        # Numeric conversion
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    def _build_config(self, data: Dict[str, Any]) -> Config:
        """Build Config object from raw dictionary data.
        
        Args:
            data: Raw configuration dictionary
            
        Returns:
            Config object
            
        Raises:
            ConfigurationError: If required sections are missing
        """
        # Extract database config
        if 'database' not in data:
            raise ConfigurationError("Missing 'database' section in configuration")
        db_data = data['database']
        database_config = DatabaseConfig(
            path=db_data.get('path', ''),
            pool_size=db_data.get('pool_size', 5),
            timeout=db_data.get('timeout', 30.0),
            retry_attempts=db_data.get('retry_attempts', 3),
            retry_backoff_factor=db_data.get('retry_backoff_factor', 2.0),
        )
        
        # Extract LLM config
        if 'llm' not in data:
            raise ConfigurationError("Missing 'llm' section in configuration")
        llm_data = data['llm']
        llm_config = LLMConfig(
            provider=llm_data.get('provider', ''),
            model_name=llm_data.get('model_name', ''),
            api_key=llm_data.get('api_key', ''),
            temperature=llm_data.get('temperature', 0.7),
            max_tokens=llm_data.get('max_tokens', 1000),
        )
        
        # Extract cache config
        cache_data = data.get('cache', {})
        cache_config = CacheConfig(
            enabled=cache_data.get('enabled', True),
            ttl_seconds=cache_data.get('ttl_seconds', 300),
            max_size=cache_data.get('max_size', 1000),
        )
        
        # Extract logging config
        logging_data = data.get('logging', {})
        logging_config = LoggingConfig(
            level=logging_data.get('level', 'INFO'),
            format=logging_data.get('format', 'json'),
            file_path=logging_data.get('file_path', 'logs/app.log'),
            rotation=logging_data.get('rotation', '10 MB'),
            retention=logging_data.get('retention', 20),
            console_output=logging_data.get('console_output', True),
        )
        
        # Build top-level config
        config = Config(
            database=database_config,
            llm=llm_config,
            cache=cache_config,
            logging=logging_config,
            prompts_dir=data.get('prompts_dir', 'prompts'),
            default_language=data.get('default_language', 'en'),
        )
        
        return config
