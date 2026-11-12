import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.config import get_settings
from app.core.errors import AppError
from app.core.http import close_client
from app.llm.registry import available_models

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("durbar")


@asynccontextmanager
async def lifespan(_: FastAPI):
    names = ", ".join(m.id for m in available_models()) or "none"
    logger.info("Durbar AI %s started. Models: %s", __version__, names)
    if not settings.firebase_database_url:
        logger.warning("FIREBASE_DATABASE_URL is not set; app data tools will fail")
    yield
    await close_client()


app = FastAPI(
    title="Durbar AI",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(exc.payload(), status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse({"error": "Invalid request body"}, status_code=400)


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"error": "Something went wrong. Please try again."}, status_code=500)


app.include_router(router)