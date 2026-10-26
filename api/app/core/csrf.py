"""CSRF protection: SameSite=Lax cookies + double-submit token + Origin check.

Every state-changing request under /api must:
  1. carry an X-CSRF-Token header equal to the CSRF cookie, and
  2. if the browser sends Origin (or Referer), match APP_BASE_URL's origin.
"""

from urllib.parse import urlsplit

from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.security import constant_time_equals, new_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HEADER = "x-csrf-token"


def issue_csrf_cookie(response: Response) -> str:
    s = get_settings()
    token = new_token()
    # Readable by JS on our own origin (that's the point of double-submit);
    # an attacker's origin can neither read it nor set the header cross-site.
    response.set_cookie(
        s.csrf_cookie_name,
        token,
        max_age=s.session_absolute_days * 86400,
        httponly=False,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return token


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def _forbidden(msg: str) -> JSONResponse:
    return JSONResponse({"detail": msg}, status_code=403)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in SAFE_METHODS or not request.url.path.startswith("/api/"):
            return await call_next(request)

        s = get_settings()
        allowed = _origin(s.app_base_url)
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        if origin is not None:
            if origin.lower() != allowed:
                return _forbidden("Cross-site request blocked.")
        elif referer and _origin(referer) != allowed:
            return _forbidden("Cross-site request blocked.")

        cookie = request.cookies.get(s.csrf_cookie_name)
        header = request.headers.get(HEADER)
        if not cookie or not header or not constant_time_equals(cookie, header):
            return _forbidden("Security token missing or invalid. Refresh the page and retry.")
        return await call_next(request)
