"""
InterviewAce AI - FastAPI application entry point.

Run from the repository root:

    uvicorn backend.app.main:app --reload --port 8000

Interactive API docs: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai.llm import get_llm

from .config import get_settings
from .database import init_db
from .routers import admin, auth, interviews, meta, reports, resumes, roadmap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("interviewace")

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    llm = get_llm()
    log.info("%s v%s starting", settings.app_name, settings.version)
    log.info("Database: %s", settings.database_url.split("://")[0])
    log.info("LLM: %s (%s)", llm.provider, llm.model or "n/a")
    if settings.is_insecure_secret():
        log.warning("SECRET_KEY is a placeholder. Set a real one in .env before deploying.")
    if not llm.available:
        log.info("No LLM key found - running on the offline question bank and heuristic scorer. "
                 "The whole app still works; answers are just less personalised.")
    yield
    log.info("Shutting down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "AI-powered interview preparation platform: resume parsing, ATS scoring, "
        "generated interview questions, voice mock interviews, rubric-based answer "
        "evaluation, reports and a personalised learning roadmap."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Time every request. Slow AI calls are the thing we most need to see."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms > 1500 or response.status_code >= 500:
        log.warning("%s %s -> %s in %.0fms",
                    request.method, request.url.path, response.status_code, elapsed_ms)
    response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.0f}"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn Pydantic's nested error structure into one readable sentence.

    The frontend shows `detail` directly in a toast, so it has to be a sentence
    a candidate can act on, not a JSON tree of loc/msg/type objects.
    """
    parts = []
    for error in exc.errors():
        field = ".".join(str(item) for item in error.get("loc", []) if item not in ("body", "query"))
        parts.append(f"{field}: {error.get('msg', 'invalid')}" if field else error.get("msg", "invalid"))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(parts) or "Invalid request."},
    )


# Routes are mounted at the root so the paths match the project guide's REST
# API table exactly: POST /register, POST /upload-resume, GET /report, ...
app.include_router(auth.router)
app.include_router(resumes.router)
app.include_router(interviews.router)
app.include_router(reports.router)
app.include_router(roadmap.router)
app.include_router(meta.router)
app.include_router(admin.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/health",
    }
