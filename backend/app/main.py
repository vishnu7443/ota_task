import logging
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import check_db_health, get_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.modules.iam.router import router as auth_router
from app.modules.orders.router import admin_orders_router, salesman_orders_router
from app.modules.sales.router import router as sales_router

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger("ota.http")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    register_exception_handlers(app)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "HTTP %s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get(f"{settings.API_V1_PREFIX}/health", tags=["System"])
    def health_check(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        db_ok = check_db_health(db)
        return {
            "status": "ok" if db_ok else "degraded",
            "database": "connected" if db_ok else "unreachable",
            "environment": settings.ENVIRONMENT,
        }

    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(sales_router, prefix=settings.API_V1_PREFIX)
    app.include_router(salesman_orders_router, prefix=settings.API_V1_PREFIX)
    app.include_router(admin_orders_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
