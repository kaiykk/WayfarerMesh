# Configuration Module

This module provides configuration management for the Travel AI Assistant System.

## Overview

The configuration system supports:
- YAML-based configuration files
- Environment variable substitution using `${VAR_NAME}` syntax
- Environment variable overrides for all configuration values
- Automatic validation of required fields and types
- Dot-notation access to nested configuration values

## Usage

### Basic Usage

```python
from trip_assistant_refactored.config import ConfigLoader

# Load configuration
loader = ConfigLoader("config/config.yaml")
config = loader.load()

# Access configuration values
print(config.database.path)
print(config.llm.model_name)
print(config.cache.enabled)
```

### Dot-Notation Access

```python
# Get values using dot notation
db_path = loader.get("database.path")
temperature = loader.get("llm.temperature")

# Provide default values
custom_setting = loader.get("custom.setting", default="default_value")
```

### Environment Variable Substitution

In your `config.yaml`:

```yaml
llm:
  api_key: "${OPENAI_API_KEY}"
```

The `${OPENAI_API_KEY}` will be replaced with the value of the environment variable.

### Environment Variable Overrides

You can override any configuration value using environment variables with the format:
`TRIP_ASSISTANT_<SECTION>__<KEY>`

Examples:
- `TRIP_ASSISTANT_DATABASE__PATH` overrides `database.path`
- `TRIP_ASSISTANT_LLM__TEMPERATURE` overrides `llm.temperature`
- `TRIP_ASSISTANT_DATABASE__POOL_SIZE` overrides `database.pool_size`

**Note:** Use double underscores `__` to separate nested keys. Single underscores within a key name are preserved (e.g., `pool_size`).

```bash
# Override database path
export TRIP_ASSISTANT_DATABASE__PATH="/custom/path/to/db.sqlite"

# Override LLM temperature
export TRIP_ASSISTANT_LLM__TEMPERATURE="0.9"

# Override pool size
export TRIP_ASSISTANT_DATABASE__POOL_SIZE="10"
```

## Configuration Schema

### DatabaseConfig

- `path` (str, required): Path to the SQLite database file
- `pool_size` (int, default=5): Maximum number of database connections in the pool
- `timeout` (float, default=30.0): Connection timeout in seconds
- `retry_attempts` (int, default=3): Number of retry attempts for failed operations
- `retry_backoff_factor` (float, default=2.0): Exponential backoff multiplier for retries

### LLMConfig

- `provider` (str, required): LLM provider name (e.g., "openai", "anthropic")
- `model_name` (str, required): Specific model identifier
- `api_key` (str, required): API authentication key
- `temperature` (float, default=0.7): Sampling temperature (0.0-2.0)
- `max_tokens` (int, default=1000): Maximum tokens in generated responses

### CacheConfig

- `enabled` (bool, default=True): Whether caching is enabled
- `ttl_seconds` (int, default=300): Time-to-live for cached entries in seconds
- `max_size` (int, default=1000): Maximum number of entries in the cache

### LoggingConfig

- `level` (str, default="INFO"): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `format` (str, default="json"): Log output format ("json" or "text")
- `file_path` (str, default="logs/app.log"): Path to the log file
- `rotation` (str, default="10 MB"): Log file rotation size threshold
- `retention` (int, default=20): Number of rotated log files to retain
- `console_output` (bool, default=True): Whether to output logs to console

### Config (Top-level)

- `database` (DatabaseConfig, required): Database configuration
- `llm` (LLMConfig, required): Language model configuration
- `cache` (CacheConfig, required): Cache configuration
- `logging` (LoggingConfig, required): Logging configuration
- `prompts_dir` (str, default="prompts"): Directory containing prompt templates
- `default_language` (str, default="en"): Default language code for prompts

## Error Handling

The ConfigLoader raises `ConfigurationError` in the following cases:

- Configuration file not found
- Invalid YAML syntax
- Missing required fields
- Invalid field types or values
- Missing environment variables referenced with `${VAR_NAME}`
- Attempting to use `get()` before calling `load()`

## Example Configuration File

See `config.yaml` for a complete example with comments explaining each setting.
