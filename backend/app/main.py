"""CustomerIQ AI API entry point. Run with: uvicorn app.main:app --reload"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import error_body, register_error_handlers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    production = settings.app_env == "production"
    app = FastAPI(
        title="CustomerIQ AI API",
        version="0.1.0",
        description="Customer intelligence API for the CustomerIQ AI dashboard.",
        # The interactive docs list every endpoint; hide them on a public deployment.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def reject_other_websites(request: Request, call_next):
        """Browsers send an Origin header on cross-site writes. Refuse any that is not
        one of ours, as a second defence on top of SameSite cookies."""
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/api/v1/email/cod/"):
            origin = request.headers.get("origin")
            if origin and origin not in settings.cors_origins:
                return JSONResponse(
                    status_code=403,
                    content=error_body(
                        "forbidden_origin", "This request came from a website that is not allowed."
                    ),
                )
        return await call_next(request)

    @app.middleware("http")
    async def safe_headers(request: Request, call_next):
        """Headers that close common browser-side holes on every response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"        # never guess a file type
        response.headers["X-Frame-Options"] = "DENY"                  # no one may frame the API
        response.headers["Referrer-Policy"] = "no-referrer"
        # Customer data must never be kept by a shared cache or a proxy.
        response.headers.setdefault("Cache-Control", "no-store")
        if production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
