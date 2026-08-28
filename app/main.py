import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin_discord import router as admin_discord_router
from app.api.admin_invites import router as admin_invites_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.backtesting import router as backtesting_router
from app.api.data_sources import router as data_sources_router
from app.api.health import router as health_router
from app.api.internal import router as internal_router
from app.api.paper_trades import router as paper_trades_router
from app.api.preferences import router as preferences_router
from app.api.tokens import router as tokens_router
from app.core.config import get_settings
from app.core.error_alerting import alert_on_unhandled_error
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(debug=settings.debug)
logger = logging.getLogger("app.main")

app = FastAPI(
    title=settings.app_name,
    description=(
        "Private, invite-only crypto research and alerting platform. "
        "Research alerts only — not financial advice. No automated trading."
    ),
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    # Only the methods and headers this API actually uses. In production,
    # ALLOWED_ORIGINS must be the exact deployed frontend origin(s) - see
    # DEPLOYMENT.md - never "*", since allow_credentials=True with a
    # wildcard origin is rejected by browsers anyway and would be an
    # open CORS misconfiguration if it weren't.
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Scan-Secret"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_invites_router)
app.include_router(admin_users_router)
app.include_router(admin_discord_router)
app.include_router(tokens_router)
app.include_router(preferences_router)
app.include_router(paper_trades_router)
app.include_router(internal_router)
app.include_router(backtesting_router)
app.include_router(data_sources_router)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_with_discord_alert(request: Request, exc: StarletteHTTPException):
    """
    Every HTTPException with a 4xx status (bad request, unauthorized,
    not found, etc.) passes through exactly as FastAPI's own default
    handler would - delegated to http_exception_handler below, response
    format/headers unchanged. Only a 5xx HTTPException (a deliberately
    raised one, e.g. _run_scanner's own HTTPException(500, ...) in
    app/api/internal.py) additionally triggers a Discord alert before
    passthrough - previously that specific case had NO Discord
    visibility at all despite the scanner already having a Discord
    integration, unlike the per-chain SCANNER_FAILURE path which does.
    """
    if exc.status_code >= 500:
        await alert_on_unhandled_error(method=request.method, path=request.url.path, exc=exc)
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def _unhandled_exception_with_discord_alert(request: Request, exc: Exception):
    """
    Catches genuinely unhandled bugs (a raw KeyError/TypeError/etc. that
    was never wrapped in an HTTPException anywhere) - without this
    handler, FastAPI's default behavior for these is a bare 500 with no
    body (or a traceback page in debug mode), and zero Discord
    visibility. Logged at exception level (full traceback in Render's
    logs, same as before) - only a short, secret-safe summary goes to
    Discord; see error_alerting.py's own docstring for why.
    """
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    await alert_on_unhandled_error(method=request.method, path=request.url.path, exc=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "status": "phase-1-foundation",
        "dry_run": settings.dry_run,
    }
