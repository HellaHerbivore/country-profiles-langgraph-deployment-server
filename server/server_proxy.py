#!/usr/bin/env python3
"""
Authentication Proxy Server for LangGraph

This server acts as a proxy in front of the standard LangGraph server,
adding authentication while keeping the LangGraph server completely unchanged.

Architecture:
- This proxy server handles authentication and CORS
- Standard LangGraph server runs on a different port (internal)
- All authenticated requests are forwarded to the LangGraph server
- No modifications needed to graph.py or LangGraph configuration

This is the main entry point that assembles all the modular components.
"""

import logging
import asyncio

import uvicorn

# Import centralized configuration
from server.config import init_config

# Import server components
from server import create_proxy_app, LangGraphServerManager

logger = logging.getLogger(__name__)


async def _start_langgraph_in_background(langgraph_manager: LangGraphServerManager) -> None:
    """
    Bring the internal LangGraph server up concurrently with the proxy.

    The proxy must bind to $PORT immediately so Render sees a live listener and
    the frontend's wakeUpServer() retry loop can poll /ok (which returns 503
    while LangGraph is warming). Any failure here is logged loudly but does NOT
    crash the proxy: /ok will simply keep returning 503 until we recover.
    """
    logger.info("Checking if LangGraph server is already running...")
    if await langgraph_manager.is_running():
        logger.info("LangGraph server is already running!")
        return

    logger.info("LangGraph server not detected, starting it...")
    try:
        success = await langgraph_manager.start_server()
        if not success:
            logger.error("LangGraph server failed to start (see child process logs above)")
            return

        if not await langgraph_manager.wait_for_ready():
            logger.error("LangGraph server did not become ready in time")
            return

        logger.info("LangGraph server is ready to accept requests")
    except Exception:
        # Never let a LangGraph startup failure tear down the proxy event loop.
        # Log the traceback so Render captures the root cause.
        logger.exception("Unhandled exception while starting LangGraph server")


async def main():
    """Main function to start the proxy server."""
    logger.info("Starting LangGraph Authentication Proxy...")

    # Initialize configuration first - this will validate all settings.
    # Config errors are fatal: raise so the traceback lands in Render's logs
    # instead of disappearing into a silent exit-0.
    try:
        app_config = init_config()
    except Exception:
        logger.exception("Configuration error. Check your environment variables.")
        raise

    # Build the proxy app up-front so we can bind to $PORT immediately.
    # LangGraph can warm up in the background; /ok (server/health.py) returns
    # 503 until it's ready, and the frontend retries 503s (frontend/web/src/api.js).
    langgraph_manager = LangGraphServerManager(app_config)
    app = create_proxy_app(app_config)

    logger.info(f"Starting proxy server on port {app_config.proxy_port}...")
    uvicorn_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=app_config.proxy_port,
        log_level=app_config.log_level.lower()
    )
    server = uvicorn.Server(uvicorn_config)

    # Kick off LangGraph startup concurrently with uvicorn.serve() so Render
    # sees the $PORT binding within seconds of boot regardless of how long
    # LangGraph takes to initialize.
    langgraph_task = asyncio.create_task(_start_langgraph_in_background(langgraph_manager))

    try:
        await server.serve()
    finally:
        # Ensure the background startup task doesn't outlive the proxy.
        if not langgraph_task.done():
            langgraph_task.cancel()
            try:
                await langgraph_task
            except (asyncio.CancelledError, Exception):
                pass
        # Clean up LangGraph server if we started it
        await langgraph_manager.stop_server()


if __name__ == "__main__":
    asyncio.run(main())
