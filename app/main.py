from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import alarms, auth, commands, devices, health, stats
from app.config.settings import get_settings
from app.middleware.logging import RequestContextMiddleware, configure_logging
from app.middleware.rate_limit import limiter
from app.mqtt.publisher import mqtt_publisher

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger("iot-platform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", environment=settings.environment)
    try:
        await mqtt_publisher.start()
    except Exception:  # noqa: BLE001 - API should still serve read endpoints if the broker is down
        logger.warning("mqtt_publisher_start_failed", detail="command endpoints will 503 until the broker is reachable")
    yield
    await mqtt_publisher.stop()
    logger.info("shutdown")


app = FastAPI(
    title="IoT Time-Series Platform",
    description="Enterprise-grade IoT ingestion, storage, and query API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


# CORS: wide open by default for local/demo use. Lock this down to your real
# frontend origin(s) before any production deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SlowAPIMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(commands.router)
app.include_router(alarms.router)
app.include_router(stats.router)
