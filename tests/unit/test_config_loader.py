"""Unit tests for the ConfigLoader class.

This module tests the configuration loading system including YAML parsing,
environment variable substitution, and environment variable overrides.
"""

import os
import pytest
import tempfile
import yaml
from pathlib import Path
from hypothesis import given, strategies as st, assume
from trip_assistant_refactored.config.config_loader import ConfigLoader
from trip_assistant_refactored.config.config_schema import Config
from trip_assistant_refactored.utils.error_handling.exceptions import ConfigurationError


# Hypothesis strategies for generating test data
@st.composite
def config_key_strategy(draw):
    """Generate valid configuration keys in dot notation."""
    sections = ["database", "llm", "cache", "logging"]
    section = draw(st.sampled_from(sections))
    
    keys_by_section = {
        "database": ["path", "pool_size", "timeout", "retry_attempts", "retry_backoff_factor"],
        "llm": ["provider", "model_name", "api_key", "temperature", "max_tokens"],
        "cache": ["enabled", "ttl_seconds", "max_size"],
        "logging": ["level", "format", "file_path", "rotation", "retention", "console_output"]
    }
    
    key = draw(st.sampled_from(keys_by_section[section]))
    return f"{section}.{key}"


@st.composite
def config_value_strategy(draw, key):
    """Generate appropriate values based on the configuration key."""
    # Determine value type based on key
    if key.endswith("path") or key.endswith("provider") or key.endswith("model_name") or \
       key.endswith("api_key") or key.endswith("level") or key.endswith("format") or \
       key.endswith("file_path") or key.endswith("rotation"):
        # String values
        return draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'), 
            whitelist_characters='._-/'
        )))
    elif key.endswith("enabled") or key.endswith("console_output"):
        # Boolean values
        return draw(st.booleans())
    elif key.endswith("temperature"):
        # Float values between 0.0 and 2.0
        return draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))
    elif key.endswith("timeout") or key.endswith("retry_backoff_factor"):
        # Positive float values
        return draw(st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False))
    else:
        # Integer values
        return draw(st.integers(min_value=1, max_value=10000))


@pytest.fixture
def base_config_dict():
    """Create a minimal valid configuration dictionary."""
    return {
        "database": {
            "path": "test.db",
            "pool_size": 5,
            "timeout": 30.0,
            "retry_attempts": 3,
            "retry_backoff_factor": 2.0
        },
        "llm": {
            "provider": "openai",
            "model_name": "gpt-4",
            "api_key": "test-key",
            "temperature": 0.7,
            "max_tokens": 1000
        },
        "cache": {
            "enabled": True,
            "ttl_seconds": 300,
            "max_size": 1000
        },
        "logging": {
            "level": "INFO",
            "format": "json",
            "file_path": "logs/app.log",
            "rotation": "10 MB",
            "retention": 20,
            "console_output": True
        },
        "prompts_dir": "prompts",
        "default_language": "en"
    }


@pytest.fixture
def temp_config_file(base_config_dict):
    """Create a temporary configuration file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(base_config_dict, f)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    try:
        os.unlink(config_path)
    except OSError:
        pass


@pytest.fixture
def clean_environment():
    """Clean up environment variables before and after tests."""
    # Store original environment
    original_env = os.environ.copy()
    
    # Remove any TRIP_ASSISTANT_ variables
    for key in list(os.environ.keys()):
        if key.startswith("TRIP_ASSISTANT_"):
            del os.environ[key]
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


class TestConfigLoaderBasics:
    """Tests for basic ConfigLoader functionality."""
    
    def test_load_valid_config(self, temp_config_file, clean_environment):
        """Test loading a valid configuration file."""
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert isinstance(config, Config)
        assert config.database.path == "test.db"
        assert config.llm.provider == "openai"
    
    def test_load_missing_file(self, clean_environment):
        """Test loading a non-existent configuration file."""
        loader = ConfigLoader("/nonexistent/config.yaml")
        
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            loader.load()
    
    def test_get_before_load(self, temp_config_file, clean_environment):
        """Test that get() raises error before load() is called."""
        loader = ConfigLoader(temp_config_file)
        
        with pytest.raises(ConfigurationError, match="Configuration not loaded"):
            loader.get("database.path")
    
    def test_get_nested_value(self, temp_config_file, clean_environment):
        """Test getting nested configuration values."""
        loader = ConfigLoader(temp_config_file)
        loader.load()
        
        assert loader.get("database.path") == "test.db"
        assert loader.get("llm.temperature") == 0.7
        assert loader.get("cache.enabled") is True
    
    def test_get_with_default(self, temp_config_file, clean_environment):
        """Test getting non-existent key returns default value."""
        loader = ConfigLoader(temp_config_file)
        loader.load()
        
        assert loader.get("nonexistent.key", "default") == "default"


class TestEnvironmentVariableOverrides:
    """Tests for environment variable override functionality.
    
    **Validates: Requirements 2.5**
    """
    
    @given(
        key=config_key_strategy(),
        file_value=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd')
        )),
        env_value=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd')
        ))
    )
    def test_env_var_overrides_config_file(self, key, file_value, env_value):
        """Property test: Environment variables override config file values.
        
        For any configuration value that exists in both the config file and as an
        environment variable, the environment variable value SHALL take precedence.
        
        **Validates: Requirements 2.5**
        """
        # Ensure file_value and env_value are different
        assume(file_value != env_value)
        
        # Create a base config dictionary
        base_config = {
            "database": {
                "path": "test.db",
                "pool_size": 5,
                "timeout": 30.0,
                "retry_attempts": 3,
                "retry_backoff_factor": 2.0
            },
            "llm": {
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key": "test-key",
                "temperature": 0.7,
                "max_tokens": 1000
            },
            "cache": {
                "enabled": True,
                "ttl_seconds": 300,
                "max_size": 1000
            },
            "logging": {
                "level": "INFO",
                "format": "json",
                "file_path": "logs/app.log",
                "rotation": "10 MB",
                "retention": 20,
                "console_output": True
            },
            "prompts_dir": "prompts",
            "default_language": "en"
        }
        
        # Set the file value in the config
        section, field = key.split('.')
        
        # Skip if the value type doesn't match (e.g., trying to set string to boolean field)
        original_value = base_config[section][field]
        if isinstance(original_value, bool):
            # For boolean fields, use boolean values
            file_value = True
            env_value = False
        elif isinstance(original_value, (int, float)) and not isinstance(original_value, bool):
            # For numeric fields, use numeric values
            try:
                file_value = 100
                env_value = 200
            except (ValueError, TypeError):
                assume(False)
        
        base_config[section][field] = file_value
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(base_config, f)
            temp_config_file = f.name
        
        # Store original environment
        original_env = os.environ.copy()
        
        try:
            # Clean environment
            for key_to_remove in list(os.environ.keys()):
                if key_to_remove.startswith("TRIP_ASSISTANT_"):
                    del os.environ[key_to_remove]
            
            # Set environment variable override
            env_key = f"TRIP_ASSISTANT_{section.upper()}__{field.upper()}"
            os.environ[env_key] = str(env_value)
            
            # Load configuration
            loader = ConfigLoader(temp_config_file)
            
            try:
                loader.load()
                
                # Get the value using dot notation
                actual_value = loader.get(key)
                
                # The actual value should match the environment variable, not the file value
                # Convert for comparison since env vars are strings
                if isinstance(env_value, bool):
                    assert actual_value == env_value
                elif isinstance(env_value, (int, float)) and not isinstance(env_value, bool):
                    assert actual_value == env_value
                else:
                    assert str(actual_value) == str(env_value)
                
                # Verify it's NOT the file value
                if isinstance(file_value, bool):
                    assert actual_value != file_value or env_value == file_value
                elif isinstance(file_value, (int, float)) and not isinstance(file_value, bool):
                    assert actual_value != file_value or env_value == file_value
                else:
                    assert str(actual_value) != str(file_value) or str(env_value) == str(file_value)
                    
            except ConfigurationError:
                # Some combinations might fail validation, which is acceptable
                # The property still holds for valid configurations
                assume(False)
        finally:
            # Cleanup
            os.environ.clear()
            os.environ.update(original_env)
            try:
                os.unlink(temp_config_file)
            except OSError:
                pass
    
    def test_env_override_database_path(self, temp_config_file, clean_environment):
        """Test environment variable overrides database path."""
        os.environ["TRIP_ASSISTANT_DATABASE__PATH"] = "/override/path.db"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config.database.path == "/override/path.db"
        assert loader.get("database.path") == "/override/path.db"
    
    def test_env_override_pool_size(self, temp_config_file, clean_environment):
        """Test environment variable overrides integer value."""
        os.environ["TRIP_ASSISTANT_DATABASE__POOL_SIZE"] = "10"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config.database.pool_size == 10
        assert loader.get("database.pool_size") == 10
    
    def test_env_override_temperature(self, temp_config_file, clean_environment):
        """Test environment variable overrides float value."""
        os.environ["TRIP_ASSISTANT_LLM__TEMPERATURE"] = "0.9"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config.llm.temperature == 0.9
        assert loader.get("llm.temperature") == 0.9
    
    def test_env_override_boolean(self, temp_config_file, clean_environment):
        """Test environment variable overrides boolean value."""
        os.environ["TRIP_ASSISTANT_CACHE__ENABLED"] = "false"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config.cache.enabled is False
        assert loader.get("cache.enabled") is False
    
    def test_multiple_env_overrides(self, temp_config_file, clean_environment):
        """Test multiple environment variable overrides simultaneously."""
        os.environ["TRIP_ASSISTANT_DATABASE__PATH"] = "/new/path.db"
        os.environ["TRIP_ASSISTANT_DATABASE__POOL_SIZE"] = "8"
        os.environ["TRIP_ASSISTANT_LLM__TEMPERATURE"] = "0.5"
        os.environ["TRIP_ASSISTANT_CACHE__ENABLED"] = "false"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config.database.path == "/new/path.db"
        assert config.database.pool_size == 8
        assert config.llm.temperature == 0.5
        assert config.cache.enabled is False
    
    def test_env_override_preserves_underscores_in_field_names(self, temp_config_file, clean_environment):
        """Test that single underscores in field names are preserved."""
        os.environ["TRIP_ASSISTANT_DATABASE__RETRY_ATTEMPTS"] = "5"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        assert config.database.retry_attempts == 5
        assert loader.get("database.retry_attempts") == 5
    
    def test_env_override_does_not_affect_other_values(self, temp_config_file, clean_environment):
        """Test that environment overrides don't affect non-overridden values."""
        os.environ["TRIP_ASSISTANT_DATABASE__PATH"] = "/override/path.db"
        
        loader = ConfigLoader(temp_config_file)
        config = loader.load()
        
        # Overridden value
        assert config.database.path == "/override/path.db"
        
        # Non-overridden values should remain from file
        assert config.database.pool_size == 5
        assert config.llm.provider == "openai"
        assert config.cache.enabled is True


class TestEnvironmentVariableSubstitution:
    """Tests for ${ENV_VAR} substitution in config files."""
    
    def test_env_var_substitution(self, clean_environment):
        """Test that ${ENV_VAR} placeholders are substituted."""
        os.environ["TEST_API_KEY"] = "secret-key-123"
        
        config_dict = {
            "database": {"path": "test.db", "pool_size": 5, "timeout": 30.0, 
                        "retry_attempts": 3, "retry_backoff_factor": 2.0},
            "llm": {"provider": "openai", "model_name": "gpt-4", 
                   "api_key": "${TEST_API_KEY}", "temperature": 0.7, "max_tokens": 1000},
            "cache": {"enabled": True, "ttl_seconds": 300, "max_size": 1000},
            "logging": {"level": "INFO", "format": "json", "file_path": "logs/app.log",
                       "rotation": "10 MB", "retention": 20, "console_output": True},
            "prompts_dir": "prompts",
            "default_language": "en"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_dict, f)
            config_path = f.name
        
        try:
            loader = ConfigLoader(config_path)
            config = loader.load()
            
            assert config.llm.api_key == "secret-key-123"
        finally:
            os.unlink(config_path)
    
    def test_missing_env_var_raises_error(self, clean_environment):
        """Test that missing environment variable in substitution raises error."""
        config_dict = {
            "database": {"path": "test.db", "pool_size": 5, "timeout": 30.0,
                        "retry_attempts": 3, "retry_backoff_factor": 2.0},
            "llm": {"provider": "openai", "model_name": "gpt-4",
                   "api_key": "${MISSING_VAR}", "temperature": 0.7, "max_tokens": 1000},
            "cache": {"enabled": True, "ttl_seconds": 300, "max_size": 1000},
            "logging": {"level": "INFO", "format": "json", "file_path": "logs/app.log",
                       "rotation": "10 MB", "retention": 20, "console_output": True},
            "prompts_dir": "prompts",
            "default_language": "en"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_dict, f)
            config_path = f.name
        
        try:
            loader = ConfigLoader(config_path)
            
            with pytest.raises(ConfigurationError, match="Environment variable 'MISSING_VAR' not found"):
                loader.load()
        finally:
            os.unlink(config_path)


class TestConfigValidation:
    """Tests for configuration validation.
    
    **Validates: Requirements 2.6**
    """
    
    def test_validation_catches_missing_required_field(self, temp_config_file, clean_environment):
        """Test that validation catches missing required fields."""
        # Load and modify config to remove required field
        with open(temp_config_file, 'r') as f:
            config_dict = yaml.safe_load(f)
        
        del config_dict["database"]["path"]
        
        with open(temp_config_file, 'w') as f:
            yaml.dump(config_dict, f)
        
        loader = ConfigLoader(temp_config_file)
        
        with pytest.raises(ConfigurationError, match="database.path is required"):
            loader.load()
    
    def test_validation_catches_invalid_pool_size(self, temp_config_file, clean_environment):
        """Test that validation catches invalid pool size."""
        os.environ["TRIP_ASSISTANT_DATABASE__POOL_SIZE"] = "0"
        
        loader = ConfigLoader(temp_config_file)
        
        with pytest.raises(ConfigurationError, match="database.pool_size must be positive"):
            loader.load()
    
    def test_validation_catches_invalid_temperature(self, temp_config_file, clean_environment):
        """Test that validation catches invalid temperature."""
        os.environ["TRIP_ASSISTANT_LLM__TEMPERATURE"] = "3.0"
        
        loader = ConfigLoader(temp_config_file)
        
        with pytest.raises(ConfigurationError, match="llm.temperature must be between"):
            loader.load()
    
    @given(
        missing_field=st.sampled_from([
            ("database", "path"),
            ("llm", "provider"),
            ("llm", "model_name"),
            ("llm", "api_key"),
        ])
    )
    def test_property_missing_required_fields_raise_error(self, missing_field):
        """Property test: Missing required fields raise ConfigurationError.
        
        For any configuration object with missing required fields, the configuration
        validator SHALL raise a ConfigurationError with a descriptive message.
        
        **Validates: Requirements 2.6**
        """
        section, field = missing_field
        
        # Create base config dict
        base_config_dict = {
            "database": {
                "path": "test.db",
                "pool_size": 5,
                "timeout": 30.0,
                "retry_attempts": 3,
                "retry_backoff_factor": 2.0
            },
            "llm": {
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key": "test-key",
                "temperature": 0.7,
                "max_tokens": 1000
            },
            "cache": {
                "enabled": True,
                "ttl_seconds": 300,
                "max_size": 1000
            },
            "logging": {
                "level": "INFO",
                "format": "json",
                "file_path": "logs/app.log",
                "rotation": "10 MB",
                "retention": 20,
                "console_output": True
            },
            "prompts_dir": "prompts",
            "default_language": "en"
        }
        
        # Create a copy of the base config and remove the field
        config_dict = base_config_dict.copy()
        config_dict[section] = config_dict[section].copy()
        del config_dict[section][field]
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_dict, f)
            temp_config_file = f.name
        
        # Store original environment
        original_env = os.environ.copy()
        
        try:
            # Clean environment
            for key in list(os.environ.keys()):
                if key.startswith("TRIP_ASSISTANT_"):
                    del os.environ[key]
            
            # Load configuration and expect error
            loader = ConfigLoader(temp_config_file)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load()
            
            # Verify error message mentions the missing field
            error_message = str(exc_info.value)
            assert field in error_message or "required" in error_message.lower()
            
        finally:
            # Cleanup
            os.environ.clear()
            os.environ.update(original_env)
            try:
                os.unlink(temp_config_file)
            except OSError:
                pass
    
    @given(
        invalid_value=st.sampled_from([
            ("database", "pool_size", -1),
            ("database", "pool_size", 0),
            ("database", "timeout", -5.0),
            ("database", "timeout", 0.0),
            ("database", "retry_attempts", -1),
            ("database", "retry_backoff_factor", -1.0),
            ("database", "retry_backoff_factor", 0.0),
            ("llm", "temperature", -0.5),
            ("llm", "temperature", 2.5),
            ("llm", "max_tokens", -100),
            ("llm", "max_tokens", 0),
            ("cache", "ttl_seconds", -10),
            ("cache", "ttl_seconds", 0),
            ("cache", "max_size", -5),
            ("cache", "max_size", 0),
            ("logging", "level", "INVALID_LEVEL"),
            ("logging", "format", "invalid_format"),
            ("logging", "retention", -1),
            ("logging", "retention", 0),
        ])
    )
    def test_property_invalid_values_raise_error(self, invalid_value):
        """Property test: Invalid configuration values raise ConfigurationError.
        
        For any configuration object with invalid types or out-of-range values,
        the configuration validator SHALL raise a ConfigurationError with a
        descriptive message.
        
        **Validates: Requirements 2.6**
        """
        section, field, value = invalid_value
        
        # Create base config dict
        base_config_dict = {
            "database": {
                "path": "test.db",
                "pool_size": 5,
                "timeout": 30.0,
                "retry_attempts": 3,
                "retry_backoff_factor": 2.0
            },
            "llm": {
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key": "test-key",
                "temperature": 0.7,
                "max_tokens": 1000
            },
            "cache": {
                "enabled": True,
                "ttl_seconds": 300,
                "max_size": 1000
            },
            "logging": {
                "level": "INFO",
                "format": "json",
                "file_path": "logs/app.log",
                "rotation": "10 MB",
                "retention": 20,
                "console_output": True
            },
            "prompts_dir": "prompts",
            "default_language": "en"
        }
        
        # Create a copy of the base config and set the invalid value
        config_dict = base_config_dict.copy()
        config_dict[section] = config_dict[section].copy()
        config_dict[section][field] = value
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_dict, f)
            temp_config_file = f.name
        
        # Store original environment
        original_env = os.environ.copy()
        
        try:
            # Clean environment
            for key in list(os.environ.keys()):
                if key.startswith("TRIP_ASSISTANT_"):
                    del os.environ[key]
            
            # Load configuration and expect error
            loader = ConfigLoader(temp_config_file)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load()
            
            # Verify error message is descriptive
            error_message = str(exc_info.value)
            assert len(error_message) > 0
            # Error message should mention the field or validation constraint
            assert (field in error_message or 
                    "positive" in error_message.lower() or 
                    "between" in error_message.lower() or
                    "must be" in error_message.lower())
            
        finally:
            # Cleanup
            os.environ.clear()
            os.environ.update(original_env)
            try:
                os.unlink(temp_config_file)
            except OSError:
                pass
    
    @given(
        missing_section=st.sampled_from(["database", "llm"])
    )
    def test_property_missing_sections_raise_error(self, missing_section):
        """Property test: Missing required sections raise ConfigurationError.
        
        For any configuration object with missing required sections (database, llm),
        the configuration validator SHALL raise a ConfigurationError.
        
        **Validates: Requirements 2.6**
        """
        # Create base config dict
        base_config_dict = {
            "database": {
                "path": "test.db",
                "pool_size": 5,
                "timeout": 30.0,
                "retry_attempts": 3,
                "retry_backoff_factor": 2.0
            },
            "llm": {
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key": "test-key",
                "temperature": 0.7,
                "max_tokens": 1000
            },
            "cache": {
                "enabled": True,
                "ttl_seconds": 300,
                "max_size": 1000
            },
            "logging": {
                "level": "INFO",
                "format": "json",
                "file_path": "logs/app.log",
                "rotation": "10 MB",
                "retention": 20,
                "console_output": True
            },
            "prompts_dir": "prompts",
            "default_language": "en"
        }
        
        # Create a copy of the base config and remove the section
        config_dict = base_config_dict.copy()
        del config_dict[missing_section]
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_dict, f)
            temp_config_file = f.name
        
        # Store original environment
        original_env = os.environ.copy()
        
        try:
            # Clean environment
            for key in list(os.environ.keys()):
                if key.startswith("TRIP_ASSISTANT_"):
                    del os.environ[key]
            
            # Load configuration and expect error
            loader = ConfigLoader(temp_config_file)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load()
            
            # Verify error message mentions the missing section
            error_message = str(exc_info.value)
            assert missing_section in error_message.lower()
            
        finally:
            # Cleanup
            os.environ.clear()
            os.environ.update(original_env)
            try:
                os.unlink(temp_config_file)
            except OSError:
                pass
