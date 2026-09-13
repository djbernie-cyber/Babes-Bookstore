"""Rate limiting and security-header middleware.

Rate limiting is Redis-backed so limits hold across the multi-process,
multi-machine Fly deployment. If the broker is unreachable we fail open to a
per-process in-memory counter (same limits) rather than blocking real traffic.
"""

import time
import os
import logging
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

try:
    from .config import settings as _settings
except Exception:  # pragma: no cover - import-time guard
    _settings = None

logger = logging.getLogger(__name__)

# Default limits: (requests, window_seconds)
DEFAULT_LIMITS = {
    "/api/v1/checkout/": (10, 60),       # 10 payment attempts/min
    "/api/v1/auth/": (20, 60),           # 20 auth requests/min (login/register)
    "/api/v1/admin/": (60, 60),          # 60 admin requests/min
    "/api/v1/": (120, 60),              # 120 API requests/min
}

_REDIS_CLIENT = None
_REDIS_TRIED = False


def _get_redis():
    global _REDIS_CLIENT, _REDIS_TRIED
    if _REDIS_TRIED:
        return _REDIS_CLIENT
    _REDIS_TRIED = True
    url = getattr(_settings, "REDIS_URL", None)
    if not url:
        return None
    try:
        import redis
        _REDIS_CLIENT = redis.Redis.from_url(
            url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            decode_responses=True,
        )
        _REDIS_CLIENT.ping()
    except Exception as e:  # pragma: no cover - broker may be down at boot
        logger.warning("Redis unavailable for rate limiting: %s", e)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _client_ip(request: Request) -> str:
    """Return the real client IP, honouring the Fly proxy's X-Forwarded-For.

    uvicorn rewrites request.client.host from the proxy header too, but the
    header-based read is explicit and survives non-proxied test runs.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply defense-in-depth response headers to every response."""

    _HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-XSS-Protection": "0",
        "Permissions-Policy": (
            "camera=(), microphone=(), geolocation=(), payment=(), "
            "usb=(), magnetometer=(), gyroscope=(), accelerometer=(), "
            "browsing-topics=(), interest-cohort=()"
        ),
    }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in self._HEADERS.items():
            if name.lower() not in response.headers:
                response.headers[name] = value
        # HSTS only ever sent when the request arrived over HTTPS.
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limits=None):
        super().__init__(app)
        self.limits = limits or DEFAULT_LIMITS
        self._memhits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _get_limit(self, path: str) -> tuple[int, int] | None:
        """Match the longest prefix."""
        best = None
        for prefix, limit in self.limits.items():
            if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, limit)
        return best[1] if best else None

    def _mem_allow(self, key: str, max_requests: int, window: int) -> tuple[bool, int]:
        """Per-process fallback counter. Returns (allowed, retry_after)."""
        now = time.time()
        if now - self._last_cleanup >= 60:
            self._last_cleanup = now
            cutoff = now - 120
            for k in [k for k, v in self._memhits.items() if not v or v[-1] < cutoff]:
                del self._memhits[k]
        self._memhits[key] = [t for t in self._memhits[key] if t > now - window]
        if len(self._memhits[key]) >= max_requests:
            retry_after = int(self._memhits[key][0] + window - now) + 1
            return False, retry_after
        self._memhits[key].append(now)
        return True, 0

    def _redis_allow(self, key: str, max_requests: int, window: int):
        """Redis fixed-window counter. Returns (allowed, retry_after) or None on error."""
        import time as _t
        now = int(_t.time())
        ry = None
        try:
            client = _get_redis()
            if client is None:
                return None
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            count, _ = pipe.execute()
            if int(count) > max_requests:
                ttl = client.ttl(key)
                ry = int(ttl) if ttl and int(ttl) > 0 else 1
                return False, ry
            return True, 0
        except Exception as e:  # pragma: no cover - tolerate broker hiccups
            logger.warning("Redis rate-limit error (falling back to memory): %s", e)
            return None

    async def dispatch(self, request: Request, call_next):
        # Tokenless CI/test runs saturate in-memory limits; skip when disabled.
        if os.environ.get("DISABLE_RATE_LIMITING") == "1":
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        limit = self._get_limit(path)
        if not limit:
            return await call_next(request)

        max_requests, window = limit
        ip = _client_ip(request)
        key = f"rl:{ip}:{path}"

        result = self._redis_allow(key, max_requests, window)
        if result is None:
            allowed, retry_after = self._mem_allow(key, max_requests, window)
        else:
            allowed, retry_after = result
            if not allowed:
                # Sync the in-memory fallback so a broker flap can't double credits
                self._mem_allow(key, max_requests, window)

        response = None
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )
        else:
            response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(max_requests)
        try:
            hits = self._memhits.get(key, [])
            remaining = max(0, max_requests - len(hits))
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        except Exception:
            pass
        return response