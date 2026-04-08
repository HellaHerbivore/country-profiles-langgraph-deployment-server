"""
Application Factory for LangGraph Server with Auth

This module provides the main application factory function that assembles
all middleware components into a complete server application.
"""

import logging
from starlette.applications import Starlette

from server.config import ServerConfig
from server.middleware.auth import APIKeyAuthMiddleware
from server.middleware.clerk_auth import ClerkAuthMiddleware
from server.middleware.cors import add_cors_middleware
from server.proxy import LangGraphProxyMiddleware
from server.models import create_tables, get_session_factory
from server.feedback_routes import feedback_routes

logger = logging.getLogger(__name__)


def create_proxy_app(config: ServerConfig) -> Starlette:
    """
    Create the proxy application with all middleware configured.
    """
    logger.info("Creating proxy application...")

    # Initialize the testing database
    db_path = getattr(config, "testing_db_path", None) or "sqlite:///testing_data.db"
    create_tables(db_path)
    db_session_factory = get_session_factory(db_path)

    # Create the base app with feedback/admin routes
    app = Starlette(routes=feedback_routes)

    # Add middleware in reverse order (last added runs first)
    # Order: Request -> CORS -> Auth -> Proxy -> LangGraph Server

    # 1. Add proxy middleware first (runs last - forwards to LangGraph)
    app.add_middleware(
        LangGraphProxyMiddleware,
        langgraph_url=config.langgraph_url,
        db_session_factory=db_session_factory,
    )
    logger.info(f"Added LangGraph proxy middleware for {config.langgraph_url}")

    # 2. Add authentication middleware second (runs second - validates API keys)
    if config.auth_type == "clerk":
        app.add_middleware(ClerkAuthMiddleware, config=config)
        logger.info("Added Clerk JWT authentication middleware")
    else:
        app.add_middleware(APIKeyAuthMiddleware, config=config)
        logger.info(f"Added API key authentication middleware (required: {config.api_key_required})")

    # 3. Add CORS middleware last (runs first - handles preflight requests)
    add_cors_middleware(app, config)

    logger.info("Proxy application created successfully")
    return app


def get_middleware_info(config: ServerConfig) -> dict:
    """Get information about the middleware configuration."""
    return {
        "middleware_stack": [
            {
                "name": "CORS",
                "enabled": bool(config.cors_allowed_origins),
                "config": {
                    "allowed_origins": config.cors_allowed_origins
                }
            },
            {
                "name": "Authentication",
                "enabled": config.api_key_required,
                "config": {
                    "api_key_required": config.api_key_required
                }
            },
            {
                "name": "LangGraph Proxy",
                "enabled": True,
                "config": {
                    "target_url": config.langgraph_url,
                    "internal_port": config.langgraph_internal_port
                }
            }
        ]
    }
