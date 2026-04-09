"""
LangGraph Server Management

This module handles starting, stopping, and monitoring the internal
LangGraph server process.
"""

import os
import logging
import asyncio
from typing import Optional

import httpx

from server.config import ServerConfig

logger = logging.getLogger(__name__)


class LangGraphServerManager:
    """
    Manages the lifecycle of the internal LangGraph server process.
    """
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self.grpc_process: Optional[asyncio.subprocess.Process] = None

    async def start_server(self) -> bool:
        """
        Start the internal LangGraph server.

        Starts the gRPC sidecar (core-api-grpc) first, then the uvicorn server.
        The base image's entrypoint normally handles this, but since we use a
        custom entrypoint (server_proxy.py), we must start it ourselves.

        Returns:
            bool: True if server started successfully, False otherwise
        """
        logger.info(f"Starting internal LangGraph server on port {self.config.langgraph_internal_port}...")

        # Set up environment for LangGraph API server
        env = os.environ.copy()
        env["PORT"] = str(self.config.langgraph_internal_port)
        env["HOST"] = "127.0.0.1"  # Only bind to localhost for security

        # Start the gRPC sidecar first (required by LangGraph API server)
        try:
            logger.info("Starting core-api-grpc sidecar...")
            self.grpc_process = await asyncio.create_subprocess_exec(
                "core-api-grpc", "-service", "core-api",
                env=env,
                stdout=None,
                stderr=None
            )
            logger.info(f"core-api-grpc started with PID {self.grpc_process.pid}")
            # Give gRPC server a moment to initialize
            await asyncio.sleep(2)
        except FileNotFoundError:
            logger.warning("core-api-grpc not found, skipping gRPC sidecar")
        except Exception as e:
            logger.warning(f"Failed to start core-api-grpc: {e}")

        # Use the correct command for LangGraph API server
        cmd = [
            "uvicorn",
            "langgraph_api.server:app",
            "--host", "127.0.0.1",
            "--port", str(self.config.langgraph_internal_port)
        ]

        try:
            logger.info(f"Starting LangGraph server: {' '.join(cmd)}")
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=None,
                stderr=None
            )

            # Give it a moment to start
            await asyncio.sleep(2)

            # Check if process is still running
            if self.process.returncode is None:
                logger.info(f"LangGraph server started successfully with PID {self.process.pid} on port {self.config.langgraph_internal_port}")
                return True
            else:
                logger.error(f"LangGraph server failed to start with return code {self.process.returncode}")
                return False

        except FileNotFoundError as e:
            logger.error(f"uvicorn command not found: {e}")
            logger.error("Make sure uvicorn is installed and available in PATH")
            return False
        except Exception as e:
            logger.error(f"Failed to start LangGraph server: {e}")
            return False
    
    async def wait_for_ready(self, max_wait: int = 180) -> bool:
        """
        Wait for the LangGraph server to be ready to accept requests.
        
        Args:
            max_wait: Maximum time to wait in seconds (default: 90)
            
        Returns:
            bool: True if server is ready, False if timeout
        """
        logger.info("Waiting for LangGraph server to be ready...")
        
        for attempt in range(max_wait):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(f"{self.config.langgraph_url}/ok")
                    if response.status_code == 200:
                        logger.info(f"LangGraph server is ready! (took {attempt + 1} seconds)")
                        return True
            except Exception:
                pass
            
            await asyncio.sleep(1)
        
        logger.error(f"LangGraph server did not become ready within {max_wait} seconds")
        return False
    
    async def is_running(self) -> bool:
        """
        Check if the LangGraph server is currently running and responding.
        
        Returns:
            bool: True if server is running and responding
        """
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.config.langgraph_url}/ok")
                return response.status_code == 200
        except Exception:
            return False
    
    async def stop_server(self) -> None:
        """Stop the LangGraph server and gRPC sidecar if started by this manager."""
        if self.process:
            logger.info("Shutting down LangGraph server...")
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=10.0)
                logger.info("LangGraph server shut down successfully")
            except asyncio.TimeoutError:
                logger.warning("LangGraph server did not shut down gracefully, killing...")
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                logger.warning(f"Error shutting down LangGraph server: {e}")
            finally:
                self.process = None

        if self.grpc_process:
            logger.info("Shutting down core-api-grpc sidecar...")
            try:
                self.grpc_process.terminate()
                await asyncio.wait_for(self.grpc_process.wait(), timeout=5.0)
                logger.info("core-api-grpc shut down successfully")
            except asyncio.TimeoutError:
                self.grpc_process.kill()
                await self.grpc_process.wait()
            except Exception as e:
                logger.warning(f"Error shutting down core-api-grpc: {e}")
            finally:
                self.grpc_process = None
    
    def get_status(self) -> dict:
        """
        Get the current status of the LangGraph server.
        
        Returns:
            dict: Status information
        """
        if not self.process:
            return {
                "managed": False,
                "process_id": None,
                "status": "not_started"
            }
        
        return {
            "managed": True,
            "process_id": self.process.pid,
            "status": "running" if self.process.returncode is None else "stopped",
            "return_code": self.process.returncode
        }
