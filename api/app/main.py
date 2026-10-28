from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.budgets.router import router as budgets_router
from app.categorise.router import ledger_router as by_category_router
from app.categorise.router import router as categories_router
from app.core.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.logging import configure_logging, get_logger
from app.db.session import get_engine
from app.finance.accounts import router as accounts_router
from app.finance.summary import router as summary_router
from app.finance.transactions import router as transactions_router
from app.ingestion.router import router as imports_router
from app.reports.router import router as reports_router
from app.users.data import router as me_data_router
from app.users.router import router as me_router

log = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if get_settings().cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def create_app() -> FastAPI:
    s = get_settings()
    s.validate_for_production()
    configure_logging(s.log_level)
    docs = s.app_env != "production"
    app = FastAPI(
        title=f"{s.app_name} API",
        version="0.1.0",
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted values back (they may contain passwords or tokens).
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ())[1:]), "message": e.get("msg")}
            for e in exc.errors()
        ]
        return JSONResponse(
            {"detail": "Please check the highlighted fields.", "errors": errors}, status_code=422
        )

    @app.get("/api/health", tags=["system"])
    def health() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            log.error("health.db_unreachable")
            db_ok = False
        return JSONResponse(
            {
                "status": "ok" if db_ok else "degraded",
                "database": "ok" if db_ok else "down",
                "app": s.app_name,
            },
            status_code=200 if db_ok else 503,
        )

    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(me_data_router)
    app.include_router(accounts_router)
    app.include_router(transactions_router)
    app.include_router(summary_router)
    app.include_router(imports_router)
    app.include_router(categories_router)
    app.include_router(by_category_router)
    app.include_router(reports_router)
    app.include_router(budgets_router)
    app.include_router(admin_router)
    return app


app = create_app()
