"""
Production Configuration Management for LangGraph Server with Auth

This module provides centralized configuration management with validation,
type conversion, and clear error messages for missing or invalid environment variables.

Best practices implemented:
- Fail fast: Validate all config at startup
- Type safety: Automatic type conversion with validation
- Clear documentation: Each setting is documented
- Environment-specific defaults: Different defaults for dev/prod
- Security: Sensitive values are not logged

This configuration module is designed to be agent-agnostic and can be used
by any agent or component in the src/ directory.
"""

import os
import logging
from typing import Optional, List
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Server configuration settings."""
    
    # Port Configuration
    proxy_port: int = field(default=8000)
    langgraph_internal_port: int = field(default=8123)
    
    # Authentication
    api_key: Optional[str] = field(default=None)
    api_key_required: bool = field(default=False)

    # Authentication type: "api_key" or "clerk"
    auth_type: str = field(default="api_key")
    clerk_secret_key: Optional[str] = field(default=None)
    clerk_publishable_key: Optional[str] = field(default=None)

    
    # CORS Configuration
    cors_allowed_origins: List[str] = field(default_factory=list)
    
    # Database
    database_uri: Optional[str] = field(default=None)
    
    # Testing/feedback database
    testing_db_path: str = field(default="sqlite:///testing_data.db")

    
    # LangSmith Integration
    langsmith_api_key: Optional[str] = field(default=None)
    langsmith_tracing: bool = field(default=False)
    
    # Logging
    log_level: str = field(default="INFO")
    
    # Environment
    environment: str = field(default="development")
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_ports()
        self._validate_environment()
        self._setup_logging()
    
    def _validate_ports(self):
        """Validate port configuration."""
        if self.proxy_port == self.langgraph_internal_port:
            raise ValueError(
                f"Port conflict: Proxy and LangGraph cannot use the same port {self.proxy_port}. "
                f"Set LANGGRAPH_INTERNAL_PORT to a different value."
            )
        
        if not (1024 <= self.proxy_port <= 65535):
            raise ValueError(f"Invalid proxy port {self.proxy_port}. Must be between 1024-65535.")
        
        if not (1024 <= self.langgraph_internal_port <= 65535):
            raise ValueError(f"Invalid LangGraph port {self.langgraph_internal_port}. Must be between 1024-65535.")
    
    def _validate_environment(self):
        """Validate environment-specific settings."""
        valid_environments = {"development", "staging", "production"}
        if self.environment not in valid_environments:
            raise ValueError(f"Invalid environment '{self.environment}'. Must be one of: {valid_environments}")
        
        # Production-specific validations
        if self.environment == "production":
            if not self.api_key:
                logger.warning("No API key set in production environment. Authentication will be disabled.")
            
            if not self.database_uri:
                logger.warning("No database URI set in production environment.")
    
    def _setup_logging(self):
        """Configure logging based on settings."""
        numeric_level = getattr(logging, self.log_level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f'Invalid log level: {self.log_level}')
        
        logging.basicConfig(
            level=numeric_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    @property
    def langgraph_url(self) -> str:
        """Get the internal LangGraph server URL."""
        return f"http://localhost:{self.langgraph_internal_port}"
    
    def log_config_summary(self):
        """Log a summary of the configuration (without sensitive data)."""
        logger.info("=== Server Configuration ===")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Proxy Port: {self.proxy_port}")
        logger.info(f"LangGraph Internal Port: {self.langgraph_internal_port}")
        logger.info(f"API Key Required: {self.api_key_required}")
        logger.info(f"CORS Origins: {self.cors_allowed_origins}")
        logger.info(f"LangSmith Tracing: {self.langsmith_tracing}")
        logger.info(f"Log Level: {self.log_level}")
        
        # Log presence of sensitive values without exposing them
        logger.info(f"Database URI: {'✓ Set' if self.database_uri else '✗ Not Set'}")
        logger.info(f"API Key: {'✓ Set' if self.api_key else '✗ Not Set'}")
        logger.info(f"LangSmith API Key: {'✓ Set' if self.langsmith_api_key else '✗ Not Set'}")
        logger.info("============================")


def load_config() -> ServerConfig:
    """
    Load and validate configuration from environment variables.
    
    This function should be called once at application startup.
    It will raise an exception if required configuration is missing or invalid.
    
    Returns:
        ServerConfig: Validated configuration object
        
    Raises:
        ValueError: If configuration is invalid
        EnvironmentError: If required environment variables are missing
    """
    logger.info("Loading configuration from environment variables...")
    
    try:
        # Load environment variables with type conversion and validation
        config = ServerConfig(
            # Port Configuration
            proxy_port=_get_int_env("PORT", 8000),
            langgraph_internal_port=_get_int_env("LANGGRAPH_INTERNAL_PORT", 8123),
            
            # Authentication
            api_key=_get_str_env("ROCKET_API_KEY"),
            auth_type=_get_str_env_required("AUTH_TYPE", "api_key"),
            clerk_secret_key=_get_str_env("CLERK_SECRET_KEY"),
            clerk_publishable_key=_get_str_env("CLERK_PUBLISHABLE_KEY"),

            # CORS Configuration  
            cors_allowed_origins=_get_list_env("CORS_ALLOWED_ORIGINS"),
            
            # Database
            database_uri=_get_str_env("DATABASE_URI"),
            testing_db_path=_get_str_env_required("TESTING_DB_PATH", "sqlite:///testing_data.db"),

            
            # LangSmith Integration
            langsmith_api_key=_get_str_env("LANGSMITH_API_KEY"),
            langsmith_tracing=_get_bool_env("LANGSMITH_TRACING", False),
            
            # Logging
            log_level=_get_str_env_required("LOG_LEVEL", "INFO"),
            
            # Environment
            environment=_get_str_env_required("ENVIRONMENT", "development"),
        )
        
        # Set derived properties
        config.api_key_required = bool(config.api_key and config.api_key.strip())
        
        # Log configuration summary
        config.log_config_summary()
        
        logger.info("Configuration loaded successfully")
        return config
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


def _get_str_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get string environment variable."""
    value = os.getenv(key, default)
    return value.strip() if value else default


def _get_str_env_required(key: str, default: str) -> str:
    """Get string environment variable with a guaranteed non-None return."""
    value = os.getenv(key, default)
    return value.strip() if value else default


def _get_int_env(key: str, default: int) -> int:
    """Get integer environment variable with validation."""
    value = os.getenv(key)
    if value is None:
        return default
    
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {key}='{value}' is not a valid integer")


def _get_bool_env(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    
    return value.lower() in ("true", "1", "yes", "on")


def _get_list_env(key: str, separator: str = ",") -> List[str]:
    """Get list environment variable (comma-separated by default)."""
    value = os.getenv(key, "")
    if not value.strip():
        return []
    
    return [item.strip() for item in value.split(separator) if item.strip()]


# Global configuration instance
# This will be set when load_config() is called
config: Optional[ServerConfig] = None


def get_config() -> ServerConfig:
    """
    Get the global configuration instance.
    
    Returns:
        ServerConfig: The loaded configuration
        
    Raises:
        RuntimeError: If configuration hasn't been loaded yet
    """
    if config is None:
        raise RuntimeError(
            "Configuration not loaded. Call load_config() first, typically in your main() function."
        )
    return config


def init_config() -> ServerConfig:
    """
    Initialize the global configuration.
    
    This should be called once at application startup.
    
    Returns:
        ServerConfig: The loaded and validated configuration
    """
    global config
    config = load_config()
    return config
