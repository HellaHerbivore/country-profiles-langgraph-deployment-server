"""
Clerk JWT Authentication Middleware for LangGraph Server

Verifies Clerk session tokens (JWTs) using Clerk's JWKS endpoint.
No Clerk SDK needed — uses PyJWT + httpx.
"""

import base64
import logging
from typing import Optional

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from starlette.requests import Request

from server.config import ServerConfig

logger = logging.getLogger(__name__)


class ClerkAuthMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, config: ServerConfig) -> None:
        super().__init__(app)
        self.clerk_publishable_key = config.clerk_publishable_key

        # Build the JWKS URL from the publishable key
        self.jwks_url = self._build_jwks_url()
        self.jwks_client = PyJWKClient(self.jwks_url, cache_keys=True)

        logger.info(f"Clerk JWT auth middleware initialized. JWKS URL: {self.jwks_url}")

    def _build_jwks_url(self) -> str:
        """
        Clerk publishable keys look like: pk_test_abc123...
        The third part is a base64-encoded domain name.
        We decode it to build the URL where Clerk publishes its public keys.
        """
        if not self.clerk_publishable_key:
            raise ValueError("CLERK_PUBLISHABLE_KEY is required when AUTH_TYPE=clerk")
        parts = self.clerk_publishable_key.split("_")
        encoded_domain = parts[2]
        # Pad base64 if needed
        padding = 4 - len(encoded_domain) % 4
        if padding != 4:
            encoded_domain += "=" * padding
        domain = base64.b64decode(encoded_domain).decode("utf-8").rstrip("$")
        return f"https://{domain}/.well-known/jwks.json"

    async def dispatch(self, request: Request, call_next) -> Response:

        # Skip auth for OPTIONS requests (preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Handle root path with health check
        if request.url.path == "/":
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "service": "LangGraph Server with Clerk Auth",
                    "message": "Server is running"
                }
            )

        # Handle favicon
        if request.url.path == "/favicon.ico":
            return Response(status_code=204)

        # Skip auth for internal paths (health checks etc.)
        if self._is_internal_path(request.url.path):
            return await call_next(request)

        # Extract Bearer token from the Authorization header
        token = self._extract_bearer_token(request)
        if not token:
            logger.warning(f"No Bearer token for {request.method} {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"}
            )

        # Verify the JWT against Clerk's public keys
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )

            # Attach user info to request state
            request.state.user_id = payload.get("sub")
            logger.debug(f"Clerk auth successful for user {request.state.user_id}")

        except jwt.ExpiredSignatureError:
            logger.warning("Clerk token expired")
            return JSONResponse(status_code=401, content={"detail": "Token expired"})
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid Clerk token: {e}")
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})
        except Exception as e:
            logger.error(f"Clerk auth error: {e}")
            return JSONResponse(status_code=401, content={"detail": "Authentication failed"})

        return await call_next(request)

    def _is_internal_path(self, path: str) -> bool:
        """Paths that don't need authentication."""
        internal_paths = [
            "/ok", "/health", "/metrics", "/docs", "/openapi.json",
            "/health-detailed",
            "/__health__", "/ready", "/startup", "/shutdown"
        ]
        internal_prefixes = [
            "/_internal/",
            "/api/v1/health",
            "/api/admin",
            "/api/feedback/export",
            "/api/query-logs/export",
        ]
        return (path in internal_paths or
                any(path.startswith(prefix) for prefix in internal_prefixes))


    def _extract_bearer_token(self, request: Request) -> Optional[str]:
        """Pull the token out of 'Authorization: Bearer <token>'."""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None
