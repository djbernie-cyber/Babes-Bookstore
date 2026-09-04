"""Simple in-memory rate limiter middleware for FastAPI.

Limits requests per IP address using a sliding window counter.
Designed for moderate traffic — not suitable for multi-worker deployments
without an external store like Redis. For production with multiple
workers, consider using `slowapi` or a Redis-backed limiter.
"""

import time
import logging
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Default limits: (requests, window_seconds)
DEFAULT_LIMITS = {
    "/api/v1/checkout/": (10, 60),       # 10 checkouts/min
    "/api/v1/auth/": (20, 60),           # 20 auth requests/min
    "/api/v1/admin/": (60, 60),          # 60 admin requests/min
    "/api/v1/": (120, 60),              # 120 API requests/min
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limits=None):
        super().__init__(app)
        self.limits = limits or DEFAULT_LIMITS
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _get_limit(self, path: str) -> tuple[int, int] | None:
        """Match the longest prefix."""
        best = None
        for prefix, limit in self.limits.items():
            if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, limit)
        return best[1] if best else None

    def _cleanup(self):
        """Prune old entries every 60 seconds."""
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        cutoff = now - 120
        stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
        for k in stale:
            del self._hits[k]

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit API routes
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        limit = self._get_limit(path)
        if not limit:
            return await call_next(request)

        max_requests, window = limit
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"
        now = time.time()

        self._cleanup()

        # Remove expired entries
        self._hits[key] = [t for t in self._hits[key] if t > now - window]

        if len(self._hits[key]) >= max_requests:
            retry_after = int(self._hits[key][0] + window - now) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )

        self._hits[key].append(now)
        response = await call_next(request)
        remaining = max(0, max_requests - len(self._hits[key]))
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
